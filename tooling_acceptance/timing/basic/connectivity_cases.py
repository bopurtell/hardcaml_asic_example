#!/usr/bin/env python3
"""Real mapped-input tracing fixtures against unmodified public SDC.

These are explicitly diagnostic netlist mutations, not new synthesized products.
Positive baseline must complete before a negative can qualify as rejection of
its intended mutation. No local source tracing/resolution is implemented here.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
from real_tools import SCRATCH, EVIDENCE, dump, launch
from record_command import sha


def pin_change(text, cell, pin, value):
    pattern = rf'(  sg13cmos5l_dfrbpq_1 {re.escape(cell)} \(\n)(.*?)(\n  \);)'
    def change(match):
        body, count = re.subn(rf'\.{pin}\([^)]*\)', f'.{pin}({value})', match[2])
        assert count == 1
        return match[1] + body + match[3]
    result, count = re.subn(pattern, change, text, flags=re.S)
    assert count == 1, cell
    return result


def gate(text, name, source, inverted=False):
    master, output = ("inv", "Y") if inverted else ("buf", "X")
    return text.replace("endmodule", f"  wire {name};\n  sg13cmos5l_{master}_1 {name}_cell (.A({source}), .{output}({name}));\nendmodule")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--synthesis", type=Path, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--taps-only", action="store_true")
    a = p.parse_args()
    base = a.audit.resolve()
    sdc = (base / "top.sdc").read_bytes()
    netlist = (base / "mapped.v").read_text()
    inv = json.loads((a.synthesis / "inventory.json").read_text())["stages"]
    first = next(s for s in inv if s["id"] == "capture_first")["cell"]
    second = next(s for s in inv if s["id"] == "capture_second")["cell"]
    manifest = json.loads((base / "manifest.json").read_text())
    port = next(e for e in manifest["timing_intent"]["exceptions"] if e["kind"] == "async_capture")["source"]
    source = port["port"] + (f'[{port["bit"]}]' if port["bit"] is not None else "")
    other = "ena" if source != "ena" else "ui_in[0]"
    cases = [("baseline", netlist, 0, "")]
    # Native positive: all three external source roles through actual CMOS5L buffers.
    buffered = gate(gate(gate(netlist, "buffer_clock", "clk"), "buffer_data", source), "buffer_reset", "rst_n")
    for s in inv:
        buffered = pin_change(buffered, s["cell"], "CLK", "buffer_clock")
        buffered = pin_change(buffered, s["cell"], "RESET_B", "buffer_reset")
    buffered = pin_change(buffered, first, "D", "buffer_data")
    cases.append(("buffered-clock-data-reset", buffered, 0, ""))
    original_output = "assign uo_out = { 6'h00, signal_and_1, signal_and };"
    assert original_output in netlist
    cases.append(("q-output-tap", netlist.replace(original_output,
                  "assign uo_out = { 5'h00, hc_pt7_capture_first, signal_and_1, signal_and };"), 0, ""))
    cases.append(("source-output-tap", netlist.replace(original_output,
                  f"assign uo_out = {{ 5'h00, {source}, signal_and_1, signal_and }};"), 0, ""))
    for role, pin, declared, label in [("clock", "CLK", "clk", "mapped clock for capture_first"),
                                        ("capture", "D", source, "mapped capture source for capture_first"),
                                        ("reset", "RESET_B", "rst_n", "mapped active-low reset source for capture_first")]:
        wrong = source if role == "reset" else other
        if role == "clock" and wrong == "clk":
            wrong = "ena"
        cases.append((role + "-wrong-input", pin_change(netlist, first, pin, wrong), 1, label))
        cases.append((role + "-constant", pin_change(netlist, first, pin, "1'b0"), 1, label))
        cases.append((role + "-disconnected", pin_change(netlist, first, pin, ""), 1, label))
        inverted = gate(netlist, "inverted_source", declared, inverted=True)
        cases.append((role + "-inverted", pin_change(inverted, first, pin, "inverted_source"), 1, label))
    cases.append(("interstage-rewired", pin_change(netlist, second, "D", source), 1,
                  "mapped interstage data differs for capture_second"))
    # Native mapped buffer-depth boundary, independently of implementation algorithm.
    for depth in (8, 9):
        deep = netlist
        previous = source
        for n in range(depth):
            name = f"source_hop_{n}"
            deep = gate(deep, name, previous)
            previous = name
        cases.append((f"capture-{depth}-buffers", pin_change(deep, first, "D", previous),
                      0 if depth == 8 else 1, "" if depth == 8 else "mapped source exceeds eight buffer hops"))
    if a.taps_only:
        cases = [row for row in cases if row[0] in ("baseline", "q-output-tap", "source-output-tap")]
    else:
        cases = [row for row in cases if row[0] not in ("q-output-tap", "source-output-tap")]
    out = EVIDENCE / a.label
    out.mkdir()
    results = []
    baseline_ok = False
    for case, text, expected, diagnostic in cases:
        work = SCRATCH / (a.label + "-" + case)
        work.mkdir()
        (work / "mapped.v").write_text(text)
        (work / "top.sdc").write_bytes(sdc)
        shutil.copyfile(base / "cells.lib", work / "cells.lib")
        driver = """proc main {} {
  read_liberty cells.lib
  read_verilog mapped.v
  link_design tt_um_pt7_timing
  read_sdc top.sdc
"""
        for mode in ("min", "max"):
            for i, s in enumerate(s for s in inv if s["index"]):
                previous = next(p for p in inv if p["chain"] == s["chain"] and p["index"] == s["index"] - 1)
                driver += f'  report_checks -from [get_pins {{{previous["cell"]}/Q}}] -to [get_pins {{{s["cell"]}/D}}] -path_delay {mode} {">" if i == 0 else ">>"} downstream_{mode}.rpt\n'
        driver += """  puts PT7_CONNECTIVITY_COMPLETE
}
if {[catch {main} message options]} {
  puts stderr "PT7_CONNECTIVITY_FAILED: $message"
  exit 1
}
exit 0
"""
        (work / "driver.tcl").write_text(driver)
        record = {"case": case, "expected_exit": expected, "expected_diagnostic": diagnostic,
                  "sdc_sha256": sha(work / "top.sdc"), "netlist_sha256": sha(work / "mapped.v"),
                  "kind": "controlled_mapped_netlist_fixture", "status": "prepared"}
        if not a.prepare_only:
            attempt = out / (case + "-launch")
            code = launch("sta", work, attempt, ["mapped.v", "top.sdc", "cells.lib", "driver.tcl"],
                          ["-no_init", "-exit", "driver.tcl"])
            log = (attempt / "stdout.log").read_text() + (attempt / "stderr.log").read_text()
            record.update(exit_code=code, diagnostic_found=diagnostic in log,
                          validated='"event":"validated"' in log,
                          applied_records=log.count('"event":"applied"'),
                          complete='"event":"complete"' in log,
                          driver_complete="PT7_CONNECTIVITY_COMPLETE" in log)
            if expected == 0:
                passed = code == 0 and record["applied_records"] == 2 and record["complete"] and record["driver_complete"]
                for mode in ("min", "max"):
                    report = work / f"downstream_{mode}.rpt"
                    passed = passed and report.is_file() and report.read_text().count("Startpoint:") == 3
                if case == "baseline":
                    baseline_ok = passed
            else:
                passed = baseline_ok and code == 1 and record["diagnostic_found"] and not record["validated"] and not record["applied_records"] and not record["complete"]
            record["status"] = "pass" if passed else "failed_assertion"
        shutil.copytree(work, out / case)
        dump(out / case / "assertions.json", record)
        results.append(record)
    dump(out / "summary.json", {"cases": results, "status": "prepared" if a.prepare_only else
         ("pass" if all(r["status"] == "pass" for r in results) else "failed_assertions"),
         "unmodified_sdc": True, "baseline_must_pass_for_negative_qualification": True})
    print(json.dumps(results, indent=2))
    if not a.prepare_only:
        assert all(r["status"] == "pass" for r in results), "see preserved case assertions"


if __name__ == "__main__":
    main()
