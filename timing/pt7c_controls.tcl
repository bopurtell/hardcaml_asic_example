proc collect {label} {
  write_sdc -no_timestamp -digits 12 $label.sdc
  check_setup -verbose > $label-checks.rpt
  foreach mode {min max} {
    report_checks -from [get_ports ena] -to [get_pins _4_/D] -path_delay $mode -format full_clock_expanded -digits 6 > $label-capture-$mode.rpt
    report_checks -from [get_pins _4_/Q] -to [get_pins _3_/D] -path_delay $mode -format full_clock_expanded -digits 6 > $label-downstream-$mode.rpt
  }
  puts "CONTROL_COMPLETE $label"
}
proc main {} {
  read_liberty /old/cells.lib
  read_verilog /old/mapped.v
  link_design tt_um_pt7_timing
  read_sdc /old/top.sdc
  collect baseline
  reset_path -from [get_ports ena] -to [get_pins _4_/D]
  collect capture-removed
  set_false_path -setup -from [get_ports ena] -to [get_pins _4_/D]
  collect capture-setup-only
  reset_path -from [get_ports ena] -to [get_pins _4_/D]
  set_false_path -from [get_ports ena] -to [get_pins {_4_/D _3_/D}]
  collect capture-broad
  reset_path -from [get_ports ena] -to [get_pins {_4_/D _3_/D}]
  set_false_path -from [get_ports ena] -to [get_pins _4_/D]
  set_disable_timing -from CLK -to Q [get_cells _4_]
  collect masking
  puts PT7C_CONTROLS_COMPLETE
}
if {[catch {main} message options]} {
  puts stderr "PROBE_FAILED $message\n[dict get $options -errorinfo]"
  exit 1
}
exit 0
