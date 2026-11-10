#!/usr/bin/env python3
"""Native Port/Pin/Term API diagnostic; never used to override emitted SDC."""
import argparse
import shutil
from real_tools import ROOT, SCRATCH, EVIDENCE, launch

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--tool", choices=("sta", "openroad"), default="sta")
p.add_argument("--label", required=True)
a = p.parse_args()
work = SCRATCH / a.label
work.mkdir()
inputs = ["mapped.v", "cells.lib", "top.sdc", "probe.tcl"]
prefix = ""
if a.tool == "openroad":
    for name in ("sg13cmos5l_tech.lef", "sg13cmos5l_stdcell.lef"):
        shutil.copyfile(ROOT / "_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lef" / name, work / name)
        prefix += f"read_lef {name}\n"
        inputs.append(name)
for name in ("mapped.v", "cells.lib", "top.sdc"):
    shutil.copyfile(EVIDENCE / "sta-bit-r2" / name, work / name)
(work / "probe.tcl").write_text(prefix + r'''read_liberty cells.lib
read_verilog mapped.v
link_design tt_um_pt7_timing
proc probe {label script} {
  if {[catch {uplevel 1 $script} value]} { puts "PROBE $label ERROR $value" } else { puts "PROBE $label VALUE $value" }
}
probe adapter_body {info body ::sta::get_port_pin}
probe nets_body {info body get_nets}
probe net_commands {info commands ::sta::*net*}
foreach name [list clk rst_n {ui_in[0]}] {
  set port [lindex [get_ports -quiet [list $name]] 0]
  puts "PORT $name OBJECT $port"
  set pin [::sta::get_port_pin $port]
  puts "PIN $name OBJECT $pin"
  probe pin_name {get_full_name $pin}
  probe pin_net {get_nets -of_objects $pin}
  probe pin_net_method {$pin net}
  probe pin_term {$pin term}
  probe pin_term_net {[$pin term] net}
  probe pin_net_cmd {::sta::get_net_of_pin $pin}
  probe term_net_cmd {::sta::get_net_of_term [$pin term]}
}
probe actual_sdc {read_sdc top.sdc}
exit 0
''')
code = launch(a.tool, work, EVIDENCE / (a.label + "-launch"),
              inputs,
              ["-no_init", "-exit", "probe.tcl"])
shutil.copytree(work, EVIDENCE / a.label)
raise SystemExit(code)
