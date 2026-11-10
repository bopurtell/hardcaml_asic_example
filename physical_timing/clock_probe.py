#!/usr/bin/env python3
"""Probe B's exact propagated-clock/annotation API; no placement or RCX."""
import argparse
from pathlib import Path

from commands import STORE, native, write_new
from native_controls import LIBRARIES, MAPPED


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--tool', choices=('sta', 'openroad'), required=True)
    parser.add_argument('--odb', type=Path)
    args = parser.parse_args()
    if not args.attempt or Path(args.attempt).name != args.attempt:
        parser.error('attempt must be a single directory name')
    work = STORE / 'controls' / args.attempt
    work.mkdir(parents=True, exist_ok=False)
    bundle = args.bundle.resolve(strict=True)
    library = LIBRARIES['typical']
    inputs = [library, bundle / 'constraints/top.sdc']
    mounts = [library.parent, bundle]
    if args.tool == 'openroad':
        if not args.odb:
            parser.error('OpenROAD clock probe requires an existing diagnostic ODB')
        odb = args.odb.resolve(strict=True)
        assert odb.is_relative_to(STORE)
        load = f'read_db {{{odb}}}'
        inputs.append(odb)
        mounts.append(odb.parent)
    else:
        load = f'read_verilog {{{MAPPED}}}\nlink_design tt_um_pt7_timing'
        inputs.append(MAPPED)
        mounts.append(MAPPED.parent)
    script = work / 'clock-probe.tcl'
    script.write_text(f'''proc main {{}} {{
read_liberty {{{library}}}
{load}
source {{{bundle / 'constraints/top.sdc'}}}
puts "PROBE_CHECKED_MAP_SIZE [dict size [::hc_pt7::checked_endpoints]]"
foreach clock [sta::all_clocks] {{
  puts "PROBE_CLOCK_BEFORE [get_full_name $clock] [get_property $clock is_propagated]"
}}
set_propagated_clock [all_clocks]
foreach clock [sta::all_clocks] {{
  puts "PROBE_CLOCK_AFTER [get_full_name $clock] [get_property $clock is_propagated]"
  if {{![get_property $clock is_propagated]}} {{ error "clock did not propagate" }}
}}
report_parasitic_annotation -report_unannotated > parasitic-annotation.rpt
write_sdc -no_timestamp -digits 12 propagated-state.sdc
puts PHYSICAL_CLOCK_PROBE_COMPLETE
}}
if {{[catch {{main}} message options]}} {{
  puts stderr "$message\\n[dict get $options -errorinfo]"
  exit 1
}}
exit 0
''')
    inputs.append(script)
    code = native(work / 'launch', work, args.tool, inputs, mounts, ['-exit', script])
    raw = (work / 'launch/stdout.log').read_text()
    valid = code == 0 and 'PHYSICAL_CLOCK_PROBE_COMPLETE' in raw
    write_new(work / 'summary.json', {'tool': args.tool, 'exit_code': code, 'passed': valid,
              'scope': 'clock object API/SDC serialization and annotation reporting only',
              'extracted_parasitics': False})
    print(f'{work}: passed={valid}')
    raise SystemExit(0 if valid else 1)


if __name__ == '__main__':
    main()
