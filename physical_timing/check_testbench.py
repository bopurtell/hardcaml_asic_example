#!/usr/bin/env python3
"""Qualify deterministic replay against retained mapped gates and actual cell RTL."""
import argparse
import json
import os
from pathlib import Path

from commands import ROOT, STORE, command, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--rtl-bundle', type=Path, help='qualify against the exact fresh emitted RTL instead of mapped gates')
    args = parser.parse_args()
    if not args.attempt or Path(args.attempt).name != args.attempt:
        parser.error('attempt must be a single directory name')
    output = STORE / 'evidence' / args.attempt
    output.mkdir(parents=True, exist_ok=False)
    pdk = ROOT / '_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/verilog'
    inputs = [ROOT / 'physical_timing/functional_tb.v',
              ROOT / 'acceptance/timing/synth-scalar-r3/mapped.v',
              pdk / 'sg13cmos5l_stdcell.v', pdk / 'sg13cmos5l_udp.v']
    if args.rtl_bundle:
        bundle = args.rtl_bundle.resolve(strict=True)
        assert bundle.is_relative_to(STORE / 'bundles')
        manifest = json.loads((bundle / 'manifest.json').read_text())
        inputs = [ROOT / 'physical_timing/functional_tb.v',
                  *[bundle / path for path in manifest['synthesis_sources']]]
    cpu = str(min(os.sched_getaffinity(0)))
    executable = output / 'replay.vvp'
    code = command(output / 'compile', ['taskset', '-c', cpu, 'iverilog', '-g2012', '-DFUNCTIONAL', '-DSIM',
                   '-s', 'timing_physical_replay', '-o', executable, *inputs], inputs=inputs)
    if code:
        raise SystemExit(code)
    codes = {}
    for name, arguments in (('positive', []), ('negative', ['+negative'])):
        codes[name] = command(output / name, ['taskset', '-c', cpu, 'vvp', executable, *arguments],
                              inputs=[*inputs, executable], timeout=60)
    assert codes['positive'] == 0 and codes['negative'] != 0, codes
    assert 'checks=512' in (output / 'positive/stdout.log').read_text()
    assert 'functional mismatch check=20' in (output / 'negative/stdout.log').read_text()
    write_new(output / 'summary.json', {'status': 'passed', 'exit_codes': codes,
              'host_cpu_affinity': [int(cpu)], 'native_workers': 1,
              'observations': 512, 'scope': ('testbench qualification on fresh emitted RTL' if args.rtl_bundle
                                           else 'testbench qualification on retained mapped gates'),
              'fresh_physical_acceptance': False, 'metastability_inference': False})


if __name__ == '__main__':
    main()
