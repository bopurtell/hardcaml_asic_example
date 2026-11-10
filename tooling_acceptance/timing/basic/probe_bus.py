#!/usr/bin/env python3
"""Native lookup reproducer for A; does not resolve timing intent locally."""
import shutil
from real_tools import SCRATCH, EVIDENCE, launch

work = SCRATCH / "bus-probe-01"
work.mkdir()
for name in ("mapped.v", "cells.lib"):
    shutil.copyfile(EVIDENCE / "synth-01" / name, work / name)
(work / "probe.tcl").write_text(r'''read_liberty cells.lib
read_verilog mapped.v
link_design tt_um_pt7_timing
foreach pattern [list {ui_in[0]} {ui_in\[0\]} {ui_in*} {ui_in[[]0[]]}] {
  puts "PATTERN [list $pattern]"
  foreach p [get_ports -quiet $pattern] { puts "PORT [get_full_name $p]" }
}
exit 0
''')
code = launch("sta", work, EVIDENCE / "bus-probe-01-launch",
              ["mapped.v", "cells.lib", "probe.tcl"], ["-no_init", "-exit", "probe.tcl"])
shutil.copytree(work, EVIDENCE / "bus-probe-01")
raise SystemExit(code)
