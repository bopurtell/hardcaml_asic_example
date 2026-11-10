#!/usr/bin/env python3
"""Native controls using retained mapped input and unmodified emitted physical SDC.

Mutations are diagnostic netlist fixtures, never production outputs. Each tool
gets a separate work directory, readonly bundle/PDK mounts and hashed inputs.
"""
import argparse
import json
from pathlib import Path

from commands import ROOT, STORE, native, sha, write_new

MAPPED = ROOT / 'acceptance/timing/synth-scalar-r3/mapped.v'
PDK = ROOT / '_flow_tools/pdk/ihp-sg13cmos5l'
LIBRARIES = {corner: PDK / ('libs.ref/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_' + suffix + '.lib')
             for corner, suffix in (('fast', 'fast_1p32V_m40C'), ('typical', 'typ_1p20V_25C'),
                                    ('slow', 'slow_1p08V_125C'))}
LEFS = [PDK / 'libs.ref/sg13cmos5l_stdcell/lef' / name
        for name in ('sg13cmos5l_tech.lef', 'sg13cmos5l_stdcell.lef')]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'fixture input changed: {old}')
    return text.replace(old, new)


def fixture(case, depth=1, buffer_master='sg13cmos5l_buf_1'):
    text = MAPPED.read_text()
    additions = []

    def chain(root, sink, depth, master='sg13cmos5l_buf_1'):
        for index in range(depth):
            out = sink if index == depth - 1 else f'{sink}_{index}'
            additions.append(f'wire {out};\n{master} diag_{sink}_{index} (.A({root}), .X({out}));')
            root = out

    if case == 'sizing':
        text = text.replace('sg13cmos5l_dfrbpq_1', 'sg13cmos5l_dfrbpq_2')
    elif case.startswith('anchor-'):
        depth = int(case.split('-')[1])
        text = replace_once(text, '.Q(hc_pt7_capture_first)', '.Q(diag_anchor_root)')
        additions.append('wire diag_anchor_root;')
        chain('diag_anchor_root', 'hc_pt7_capture_first', depth)
        # The original retained netlist already declares this sink.
        additions = [a.replace('wire hc_pt7_capture_first;\n', '') for a in additions]
    elif case in ('capture', 'reset', 'clock', 'interstage', 'delay', 'inverting', 'unknown'):
        role = 'interstage' if case in ('delay', 'inverting', 'unknown') else case
        root, target = {'capture': ('ena', '.D(ena)'),
                        'reset': ('rst_n', '.RESET_B(rst_n)'),
                        'clock': ('clk', '.CLK(clk)'),
                        'interstage': ('hc_pt7_capture_first', '.D(hc_pt7_capture_first)')}[role]
        if role in ('clock', 'reset'):
            text = text.replace(target, target.replace(root, 'diag_sink'))
        else:
            text = replace_once(text, target, target.replace(root, 'diag_sink'))
        master = {'delay': 'sg13cmos5l_dlygate4sd1_1', 'inverting': 'sg13cmos5l_inv_1',
                  'unknown': 'sg13cmos5l_and2_1'}.get(case, 'sg13cmos5l_buf_1')
        if case == 'unknown':
            additions.append(f'wire diag_sink;\n{master} diag_unknown (.A({root}), .B(ena), .X(diag_sink));')
        elif case == 'inverting':
            additions.append(f'wire diag_sink;\n{master} diag_inverting (.A({root}), .Y(diag_sink));')
        else:
            chain(root, 'diag_sink', depth, master if case == 'delay' else buffer_master)
    elif case == 'contention':
        additions.append('sg13cmos5l_buf_1 diag_contention (.A(ui_in[1]), .X(ena));')
    elif case == 'extra-register':
        additions.append('wire diag_extra;\nsg13cmos5l_dfrbpq_1 diag_extra_register (.CLK(clk), .D(ena), .Q(diag_extra), .RESET_B(rst_n));')
    elif case != 'baseline':
        raise ValueError(case)
    return replace_once(text, 'endmodule', '\n'.join(additions) + '\nendmodule')


def driver(tool, netlist, sdc, expect_pass, library):
    load = '\n'.join(f'read_lef {{{p}}}' for p in LEFS) if tool == 'openroad' else ''
    return f'''proc main {{}} {{
{load}
read_liberty {{{library}}}
read_verilog {{{netlist}}}
link_design tt_um_pt7_timing
set code [catch {{source {{{sdc}}}}} message options]
puts "PHYSICAL_CONTROL_SDC code=$code message=$message"
if {{$code}} {{
  puts "[dict get $options -errorinfo]"
  if {{[llength [info commands ::hc_pt7::checked_endpoints]]}} {{
    if {{![catch {{::hc_pt7::checked_endpoints}}]}} {{ error "failed read exposed endpoint map" }}
  }}
  write_sdc -no_timestamp failed-state.sdc
  if {{{int(expect_pass)}}} {{ error "baseline/positive physical resolver failed" }}
  puts PHYSICAL_CONTROL_EXPECTED_REJECTION
  return
}}
if {{!{int(expect_pass)}}} {{ error "negative physical control unexpectedly accepted" }}
set endpoints [::hc_pt7::checked_endpoints]
if {{[dict size $endpoints] != 5}} {{ error "not exactly five checked stages" }}
if {{[llength [all_registers -cells]] != 5}} {{ error "not exactly five native registers" }}
set f [open checked-map.txt w]
dict for {{id row}} $endpoints {{
  puts $f "$id master=[dict get $row master]"
  foreach key {{cell q data clock reset}} {{ puts $f "  $key=[get_full_name [dict get $row $key]]" }}
}}
puts $f [::hc_pt7::checked_traces]
close $f
set pairs {{{{capture_first capture_second}} {{capture_second capture_third}} {{control_first control_second}}}}
foreach mode {{min max}} {{
  foreach pair $pairs {{
    lassign $pair from to
    report_checks -from [dict get $endpoints $from q] -to [dict get $endpoints $to data] -path_delay $mode -format full_clock_expanded -digits 6 > $from-$to-$mode.rpt
  }}
}}
write_sdc -no_timestamp passed-state.sdc
{'write_db control.odb' if tool == 'openroad' else ''}
puts PHYSICAL_CONTROL_PASS
}}
if {{[catch {{main}} message options]}} {{
  puts stderr "$message\\n[dict get $options -errorinfo]"
  exit 1
}}
exit 0
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--tool', choices=('sta', 'openroad'), required=True)
    parser.add_argument('--corner', choices=tuple(LIBRARIES), default='typical')
    parser.add_argument('--depth', type=int, choices=(1, 8, 9), default=1)
    parser.add_argument('--buffer-master', default='sg13cmos5l_buf_1', choices=(
        'sg13cmos5l_buf_1', 'sg13cmos5l_buf_2', 'sg13cmos5l_buf_4',
        'sg13cmos5l_buf_8', 'sg13cmos5l_buf_16', 'sg13cmos5l_dlygate4sd1_1',
        'sg13cmos5l_dlygate4sd2_1', 'sg13cmos5l_dlygate4sd3_1'))
    parser.add_argument('--case', choices=('baseline', 'sizing', 'anchor-1', 'anchor-8', 'anchor-9',
                        'capture', 'reset', 'clock', 'interstage', 'delay', 'inverting', 'unknown',
                        'contention', 'extra-register'), required=True)
    args = parser.parse_args()
    if not args.attempt or Path(args.attempt).name != args.attempt:
        parser.error('attempt must be a single directory name')
    bundle = args.bundle.resolve(strict=True)
    if not bundle.is_relative_to(STORE / 'bundles'):
        parser.error('controls require newly emitted physical bundle')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    assert manifest['timing_intent']['resolution_policy'] == 'scalar-q-driver-cmos5l-physical-v2'
    for row in manifest['files']:
        assert sha(bundle / row['path']) == row['sha256']
    work = STORE / 'controls' / args.attempt
    work.mkdir(parents=True, exist_ok=False)
    netlist = work / 'fixture.v'
    netlist.write_text(fixture(args.case, args.depth, args.buffer_master))
    sdc = bundle / 'constraints/top.sdc'
    positive = args.case not in ('anchor-9', 'inverting', 'unknown', 'contention', 'extra-register')
    if args.case in ('capture', 'reset', 'clock', 'interstage', 'delay') and args.depth == 9:
        positive = False
    script = work / 'control.tcl'
    library = LIBRARIES[args.corner]
    script.write_text(driver(args.tool, netlist, sdc, positive, library))
    inputs = [MAPPED, library, netlist, script, bundle / 'manifest.json']
    inputs += [bundle / row['path'] for row in manifest['files']]
    if args.tool == 'openroad':
        inputs += LEFS
    code = native(work / 'launch', work, args.tool, inputs,
                  [bundle, PDK, MAPPED.parent], ['-exit', script])
    log = (work / 'launch/stdout.log').read_text()
    token = 'PHYSICAL_CONTROL_PASS' if positive else 'PHYSICAL_CONTROL_EXPECTED_REJECTION'
    valid = code == 0 and token in log
    if valid and positive:
        for mode in ('min', 'max'):
            for report in work.glob('*-' + mode + '.rpt'):
                valid = valid and 'Startpoint:' in report.read_text()
            assert len(list(work.glob('*-' + mode + '.rpt'))) == 3
    if valid and not positive:
        valid = 'set_false_path' not in (work / 'failed-state.sdc').read_text()
    write_new(work / 'summary.json', {'case': args.case, 'tool': args.tool,
              'corner': args.corner, 'library': str(library), 'library_sha256': sha(library),
              'depth': int(args.case.split('-')[1]) if args.case.startswith('anchor-') else args.depth,
              'buffer_master': args.buffer_master,
              'expected': 'pass' if positive else 'reject-before-exceptions',
              'native_exit_code': code, 'control_passed': valid,
              'production_timing_claim': False})
    print(json.dumps({'work': str(work), 'control_passed': valid}))
    raise SystemExit(0 if valid else 1)


if __name__ == '__main__':
    main()
