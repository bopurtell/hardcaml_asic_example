proc dump_checks {label} {
  set names {no_input_delay no_output_delay reg_multiple_clks reg_no_clks unconstrained_endpoints loops generated_clks}
  set result [sta::check_timing_cmd 1 1 1 1 1 1 1]
  puts "DIAGNOSTICS $label COUNT [llength $result] RAW {$result}"
  foreach group $result {
    puts "GROUP COUNT [llength $group] RAW {$group}"
    foreach item $group {puts "ITEM COUNT [llength $item] RAW {$item}"}
  }
  set index 0
  foreach name $names {
    set flags {0 0 0 0 0 0 0}
    lset flags $index 1
    puts "CATEGORY $name RAW {[sta::check_timing_cmd {*}$flags]}"
    incr index
  }
  check_setup -verbose > $label.rpt
}
proc main {} {
  puts "CHECK_SETUP_BODY [info body sta::check_setup_cmd]"
  read_liberty /old/cells.lib
  read_verilog /old/mapped.v
  link_design tt_um_pt7_timing
  dump_checks no-sdc
  read_sdc /old/top.sdc
  dump_checks baseline
  write_sdc -no_timestamp baseline.sdc
  set_false_path -setup -from [get_ports ena] -to [get_pins _3_/D]
  write_sdc -no_timestamp setup-only.sdc
  set_disable_timing -from D -to Q [get_cells _4_]
  write_sdc -no_timestamp masking.sdc
  puts PT7C_PROBE_COMPLETE
}
if {[catch {main} message options]} {
  puts stderr "PROBE_FAILED $message\n[dict get $options -errorinfo]"
  exit 1
}
exit 0
