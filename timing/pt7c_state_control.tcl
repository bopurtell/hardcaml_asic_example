proc main {} {
  if {[file exists /old/cells.lib]} {
    read_liberty /old/cells.lib
  } else {
    foreach library [lsort [glob /old/library-*.lib]] {read_liberty $library}
  }
  read_verilog /old/mapped.v
  link_design tt_um_pt7_timing
  read_sdc /state.sdc
  write_sdc -no_timestamp -digits 12 observed.sdc
  check_setup -verbose > observed-checks.rpt
  foreach mode {min max} {
    report_checks -from [get_ports ena] -to [get_pins _4_/D] -path_delay $mode -format full_clock_expanded -digits 6 > capture-$mode.rpt
    foreach pair {{_4_/Q _3_/D} {_3_/Q _2_/D} {_5_/Q _6_/D}} {
      lassign $pair from to
      report_checks -from [get_pins $from] -to [get_pins $to] -path_delay $mode -format full_clock_expanded -digits 6 >> downstream-$mode.rpt
    }
  }
  if {[file exists /producer.tcl]} {
    source /producer.tcl
    ::hc_pt7_native::write [pwd]
  }
  puts PT7C_STATE_CONTROL_COMPLETE
}
if {[catch {main} message options]} {
  puts stderr "PROBE_FAILED $message\n[dict get $options -errorinfo]"
  exit 1
}
exit 0
