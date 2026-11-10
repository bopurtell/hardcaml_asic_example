#!/usr/bin/env python3
"""Produce bounded real PT.7 artifacts. Timing interpretation belongs to the provider."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from record_command import sha

ROOT = Path(__file__).resolve().parents[3]
PDK_LIB = ROOT / "_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_typ_1p20V_25C.lib"
EVIDENCE = ROOT / "acceptance/timing"
SCRATCH = ROOT / ".dev/asic-pt7"


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def launch(tool, work, attempt, inputs, arguments):
    command = [sys.executable, "-B", str(ROOT / "tooling_acceptance/timing/controls/pt7_tool.py"), "--tool", tool,
               "--work", str(work), "--output", str(attempt), "--timeout", "180"]
    for name in inputs:
        command += ["--input", str(work / name)]
    command += ["--", *arguments]
    result = subprocess.run(command, cwd=ROOT)
    return result.returncode


def synth(label, bundle):
    work = SCRATCH / label
    work.mkdir()
    manifest = json.loads((bundle / "manifest.json").read_text())
    for record in manifest["files"]:
        assert sha(bundle / record["path"]) == record["sha256"], record["path"]
    retained = EVIDENCE / (label + "-bundle")
    shutil.copytree(bundle, retained)
    shutil.copyfile(bundle / manifest["synthesis_sources"][0], work / "emitted.v")
    shutil.copyfile(PDK_LIB, work / "cells.lib")
    script = """read_liberty -lib cells.lib
read_verilog emitted.v
hierarchy -check -top tt_um_pt7_timing
synth -top tt_um_pt7_timing
dfflibmap -liberty cells.lib
abc -liberty cells.lib
clean
check
stat -liberty cells.lib
rename -enumerate
write_json mapped.json
write_verilog -noattr -noexpr mapped.v
"""
    (work / "synth.ys").write_text(script)
    code = launch("yosys", work, EVIDENCE / (label + "-launch"),
                  ["emitted.v", "cells.lib", "synth.ys"], ["-T", "-s", "synth.ys"])
    shutil.copytree(work, EVIDENCE / label)
    if code:
        raise SystemExit(code)
    mapped = json.loads((work / "mapped.json").read_text())["modules"]["tt_um_pt7_timing"]
    cells = mapped["cells"]
    inventory = []
    for stage in manifest["timing_intent"]["stages"]:
        bits = mapped["netnames"][stage["anchor"]]["bits"]
        assert len(bits) == 1
        drivers = [(name, cell) for name, cell in cells.items()
                   if cell.get("port_directions", {}).get("Q") == "output"
                   and cell["connections"]["Q"] == bits]
        assert len(drivers) == 1, (stage, drivers)
        name, cell = drivers[0]
        assert cell["type"] in ["sg13cmos5l_dfrbpq_1", "sg13cmos5l_dfrbpq_2",
                                "sg13cmos5l_dfrbp_1", "sg13cmos5l_dfrbp_2"]
        inventory.append(dict(stage, cell=name, master=cell["type"], connections=cell["connections"]))
    assert len({s["cell"] for s in inventory}) == 5
    sequential = [c for c in cells.values() if "dfrbp" in c["type"]]
    assert len(sequential) == 5
    for s in inventory:
        assert s["connections"]["RESET_B"] == mapped["ports"]["rst_n"]["bits"]
        assert s["connections"]["CLK"] == mapped["ports"]["clk"]["bits"]
        if s["index"]:
            previous = next(p for p in inventory if p["chain"] == s["chain"] and p["index"] == s["index"] - 1)
            assert s["connections"]["D"] == previous["connections"]["Q"]
    dump(EVIDENCE / label / "inventory.json", {"assertions": "five distinct mapped stages, exact Q anchors, chain D, CLK and RESET_B connectivity", "stages": inventory})
    print(json.dumps(inventory, indent=2))


def audit(label, synthesis, bundle):
    work = SCRATCH / label
    work.mkdir()
    for name in ("mapped.v", "cells.lib"):
        shutil.copyfile(synthesis / name, work / name)
    shutil.copyfile(bundle / "manifest.json", work / "manifest.json")
    shutil.copyfile(bundle / "constraints/top.sdc", work / "top.sdc")
    shutil.copyfile(EVIDENCE / "preparation/sta-version/stdout.log", work / "producer-version.txt")
    manifest = json.loads((work / "manifest.json").read_text())
    inv = json.loads((synthesis / "inventory.json").read_text())["stages"]
    pairs = [(s, next(p for p in inv if p["chain"] == s["chain"] and p["index"] == s["index"] - 1))
             for s in inv if s["index"]]
    capture = next(e for e in manifest["timing_intent"]["exceptions"] if e["kind"] == "async_capture")
    source = capture["source"]["port"]
    if capture["source"]["bit"] is not None:
        source += f'[{capture["source"]["bit"]}]'
    driver = """proc main {} {
  set f [open receipt.json r]
  set receipt [read $f]
  close $f
  puts "PT7_AUDIT_RECEIPT [string trim $receipt]"
  read_liberty cells.lib
  read_verilog mapped.v
  link_design tt_um_pt7_timing
  read_sdc top.sdc
  if {[llength [info commands report_exceptions]]} {
    report_exceptions > exceptions.rpt
  } else {
    help report_exceptions > exceptions.rpt
  }
  check_setup -verbose > unconstrained.rpt
  report_checks -unconstrained -path_delay max >> unconstrained.rpt
"""
    for mode in ("min", "max"):
        for index, (s, previous) in enumerate(pairs):
            driver += f'  report_checks -from [get_pins {{{previous["cell"]}/Q}}] -to [get_pins {{{s["cell"]}/D}}] -path_delay {mode} -format full_clock_expanded -digits 6 {">" if index == 0 else ">>"} downstream_{mode}.rpt\n'
        driver += f'  report_checks -from [get_ports {{{source}}}] -to [get_pins {{{inv[0]["cell"]}/D}}] -path_delay {mode} > capture_{mode}.rpt\n'
    driver += """  puts PT7_AUDIT_COMPLETE
}
if {[catch {main} message options]} {
  puts stderr "PT7_AUDIT_FAILED: $message"
  puts stderr [dict get $options -errorinfo]
  exit 1
}
exit 0
"""
    (work / "driver.tcl").write_text(driver)
    sources = [{"role": role, "path": name, "sha256": sha(work / name)} for role, name in
               [("manifest", "manifest.json"), ("sdc", "top.sdc"), ("netlist", "mapped.v"),
                ("liberty", "cells.lib"), ("driver", "driver.tcl")]]
    context = {"build_identity": manifest["identity"], "audit_id": label, "stage": "synthesized_netlist",
               "producer": {"tool": "OpenSTA", "version": (work / "producer-version.txt").read_text().strip()},
               "corner": "nom_typ_1p20V_25C"}
    receipt = dict(schema=1, **context, inputs=sources.copy())
    (work / "receipt.json").write_text(json.dumps(receipt, separators=(",", ":")) + "\n")
    attempt = EVIDENCE / (label + "-launch")
    code = launch("sta", work, attempt, [s["path"] for s in sources] + ["receipt.json"],
                  ["-no_init", "-exit", "driver.tcl"])
    # The full log is stdout followed by stderr; preserve both original streams too.
    (work / "tool.log").write_bytes((attempt / "stdout.log").read_bytes() + (attempt / "stderr.log").read_bytes())
    launch_record = json.loads((attempt / "launch.json").read_text())
    dump(work / "process-result.json", {"schema": 1, "receipt_sha256": sha(work / "receipt.json"),
                                       "exit_code": code, "argv": launch_record["argv"]})
    (work / "resolution.log").write_bytes(b"".join(line for line in (work / "tool.log").read_bytes().splitlines(keepends=True)
                                                    if line.startswith(b"HC_ASIC_TIMING_V1\t")))
    if code == 0:
        for role, name in [("receipt", "receipt.json"), ("log", "tool.log"), ("resolution", "resolution.log"),
                           ("exceptions", "exceptions.rpt"), ("unconstrained", "unconstrained.rpt"),
                           ("downstream_min", "downstream_min.rpt"), ("downstream_max", "downstream_max.rpt"),
                           ("process_result", "process-result.json"), ("producer_version", "producer-version.txt")]:
            sources.append({"role": role, "path": name, "sha256": sha(work / name)})
        dump(work / "audit.json", dict(schema=1, kind="hardcaml-asic.timing-intent-audit",
                                      scope="standalone_synthesized_netlist_sta", **context, sources=sources))
    shutil.copytree(work, EVIDENCE / label)
    raise SystemExit(code)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("synth", "audit"))
    p.add_argument("--label", required=True)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--synthesis", type=Path)
    a = p.parse_args()
    if a.phase == "synth":
        synth(a.label, a.bundle.resolve())
    else:
        audit(a.label, a.synthesis.resolve(), a.bundle.resolve())


if __name__ == "__main__":
    main()
