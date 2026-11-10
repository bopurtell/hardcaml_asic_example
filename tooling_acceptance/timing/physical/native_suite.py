#!/usr/bin/env python3
"""Sequential native controls. Stop on first unexpected result; preserve every log."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from commands import ROOT, STORE, sha, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--corner', choices=('fast', 'typical', 'slow'), default='typical')
    args = parser.parse_args()
    if not args.attempt or Path(args.attempt).name != args.attempt:
        parser.error('attempt must be a single directory name')
    output = STORE / 'evidence' / args.attempt
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    cases = [(case, 1, 'sg13cmos5l_buf_1') for case in
             ('baseline', 'sizing', 'anchor-1', 'anchor-8', 'anchor-9',
              'inverting', 'unknown', 'contention', 'extra-register')]
    for role in ('capture', 'reset', 'clock', 'interstage'):
        cases.extend((role, depth, 'sg13cmos5l_buf_1') for depth in (1, 8, 9))
        cases.extend((role, 1, 'sg13cmos5l_dlygate4sd' + str(i) + '_1') for i in (1, 2, 3))
    for tool in ('sta', 'openroad'):
        for index, (case, depth, master) in enumerate(cases):
            name = f'{args.attempt}-{tool}-{index:02d}-{case}'
            argv = [sys.executable, '-B', str(ROOT / 'tooling_acceptance/timing/physical/native_controls.py'),
                    '--bundle', str(args.bundle.resolve(strict=True)), '--attempt', name,
                    '--tool', tool, '--case', case, '--depth', str(depth), '--buffer-master', master,
                    '--corner', args.corner]
            result = subprocess.run(argv, cwd=ROOT, capture_output=True)
            code = result.returncode
            (output / f'{len(rows) + 1:03d}.stdout').write_bytes(result.stdout)
            (output / f'{len(rows) + 1:03d}.stderr').write_bytes(result.stderr)
            summary = STORE / 'controls' / name / 'summary.json'
            rows.append({'argv': argv, 'exit_code': code, 'summary': str(summary),
                         'summary_sha256': sha(summary) if summary.is_file() else None})
            write_new(output / f'{len(rows):03d}.json', rows[-1])
            if code:
                write_new(output / 'summary.json', {'status': 'failed', 'controls': rows,
                                                   'stopped_at': name})
                raise SystemExit(code)
    write_new(output / 'summary.json', {'status': 'passed', 'controls': rows,
                                       'production_timing_claim': False})
    print(json.dumps({'status': 'passed', 'controls': len(rows), 'output': str(output)}))


if __name__ == '__main__':
    main()
