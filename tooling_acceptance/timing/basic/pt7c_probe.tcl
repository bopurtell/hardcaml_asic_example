proc main {} {
  puts "VERSION [sta::version]"
  foreach name {check_setup sta::check_timing_cmd sta::endpoints write_sdc} {
    puts "COMMAND $name [info commands $name]"
    if {[llength [info procs $name]]} {puts "BODY $name\n[info body $name]"}
  }
  read_liberty /old/cells.lib
  read_verilog /old/mapped.v
  link_design tt_um_pt7_timing
  read_sdc /old/top.sdc
  write_sdc native.sdc
  check_setup -verbose > check-setup.rpt
  foreach argv {{} {1} {1 1 1 1 1 1 1} {1 1 1 1 1 1 1 1} {0 0 0 0 0 0 0}} {
    set code [catch {sta::check_timing_cmd {*}$argv} result options]
    puts "CHECK_ARGS {$argv} CODE $code RESULT {$result}"
    if {$code} {puts "DETAIL [dict get $options -errorinfo]"}
  }
  set code [catch {sta::endpoints} result options]
  puts "ENDPOINTS CODE $code COUNT [llength $result] RESULT {$result}"
  if {!$code} {
    foreach pin $result {puts "ENDPOINT [get_full_name $pin]"}
  }
}
if {[catch {main} message options]} {
  puts stderr "PROBE_FAILED $message\n[dict get $options -errorinfo]"
  exit 1
}
exit 0
