#!/usr/bin/env python3
"""Disposable native-tool mutations; assertions only, no timing resolver."""
import json
import argparse
import shutil

from real_tools import SCRATCH, EVIDENCE, dump, launch
from record_command import sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="01")
    parser.add_argument("--audit", default="sta-scalar-01")
    args = parser.parse_args()
    original = EVIDENCE / args.audit
    netlist = (original / "mapped.v").read_text()
    sdc = (original / "top.sdc").read_text()
    missing_diagnostic = ("get_nets exact literal hc_pt7_capture_first: expected exactly one object, got 0"
                          if "get_nets -quiet [list $name]" in sdc or "foreach object [$command -quiet [list $name]]" in sdc
                          else "get_nets hc_pt7_capture_first: expected exactly one object, got 0")
    first_flop = """  sg13cmos5l_dfrbpq_1 _4_ (
    .CLK(clk),
    .D(ena),
    .Q(hc_pt7_capture_first),
    .RESET_B(rst_n)
  );"""
    assert first_flop in netlist
    cases = [
        ("missing", netlist.replace("hc_pt7_capture_first", "lost_capture_first"), sdc,
         missing_diagnostic),
        ("ambiguous", netlist.replace("endmodule", """  sg13cmos5l_dfrbpq_1 duplicate (
    .CLK(clk), .D(ena), .Q(hc_pt7_capture_first), .RESET_B(rst_n)
  );
endmodule"""), sdc, "Q driver for capture_first: expected exactly one object, got 2"),
        ("wrong-master", netlist.replace(first_flop, """  sg13cmos5l_buf_1 wrong_role (
    .A(ena), .X(hc_pt7_capture_first)
  );"""), sdc, "unsupported mapped master sg13cmos5l_buf_1 for capture_first"),
        ("wrong-interstage", netlist.replace(".D(hc_pt7_capture_first)", ".D(ena)"), sdc,
         "mapped interstage data differs for capture_second"),
        ("wrong-capture-scope", netlist,
         sdc.replace('[list "external_capture" "async_capture" "ena" [list "capture_first"]]',
                     '[list "external_capture" "async_capture" "ena" [list "capture_second"]]'),
         "capture is not one first stage"),
    ]
    outcomes = []
    for label, mutated_netlist, mutated_sdc, diagnostic in cases:
        work = SCRATCH / ("negative-" + label + "-" + args.attempt)
        work.mkdir()
        (work / "mapped.v").write_text(mutated_netlist)
        (work / "top.sdc").write_text(mutated_sdc)
        shutil.copyfile(original / "cells.lib", work / "cells.lib")
        (work / "driver.tcl").write_text("""proc main {} {
  read_liberty cells.lib
  read_verilog mapped.v
  link_design tt_um_pt7_timing
  read_sdc top.sdc
  puts UNEXPECTED_SUCCESS
}
if {[catch {main} message options]} {
  puts stderr "PT7_EXPECTED_FAILURE: $message"
  exit 1
}
exit 0
""")
        attempt = EVIDENCE / (work.name + "-launch")
        code = launch("sta", work, attempt, ["mapped.v", "top.sdc", "cells.lib", "driver.tcl"],
                      ["-no_init", "-exit", "driver.tcl"])
        shutil.copytree(work, EVIDENCE / work.name)
        log = (attempt / "stdout.log").read_text() + (attempt / "stderr.log").read_text()
        outcome = {"case": label, "exit_code": code, "expected_diagnostic": diagnostic,
                   "diagnostic_found": diagnostic in log,
                   "zero_application_records": '"event":"applied"' not in log,
                   "no_complete": '"event":"complete"' not in log,
                   "sdc_unchanged": sha(work / "top.sdc") == sha(original / "top.sdc"),
                   "input_hashes": {name: sha(work / name) for name in ("mapped.v", "top.sdc", "cells.lib", "driver.tcl")}}
        outcomes.append(outcome)
        dump(EVIDENCE / work.name / "assertions.json", outcome)
        assert code == 1 and outcome["diagnostic_found"] and outcome["zero_application_records"] and outcome["no_complete"], outcome
    work = SCRATCH / ("native-unconstrained-" + args.attempt)
    work.mkdir()
    for name in ("mapped.v", "cells.lib"):
        shutil.copyfile(original / name, work / name)
    (work / "driver.tcl").write_text("""read_liberty cells.lib
read_verilog mapped.v
link_design tt_um_pt7_timing
puts {PT7_DIAGNOSTIC_CONTROL: linked same netlist, intentionally no SDC or clocks}
check_setup -verbose
report_checks -unconstrained -path_delay max
exit 0
""")
    code = launch("sta", work, EVIDENCE / (work.name + "-launch"),
                  ["mapped.v", "cells.lib", "driver.tcl"], ["-no_init", "-exit", "driver.tcl"])
    shutil.copytree(work, EVIDENCE / work.name)
    assert code == 0
    dump(EVIDENCE / ("native-negatives-summary-" + args.attempt + ".json"), {"cases": outcomes,
         "unconstrained_control": work.name + "-launch/stdout.log",
         "scope": "controlled diagnostics, not valid positive audit evidence"})
    print(json.dumps(outcomes, indent=2))


if __name__ == "__main__":
    main()
