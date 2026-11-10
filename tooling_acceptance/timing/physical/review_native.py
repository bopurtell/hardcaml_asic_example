#!/usr/bin/env python3
"""Recheck native control receipts, retained paths and readonly input hashes."""
import argparse
import json
from pathlib import Path

from commands import STORE, sha, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(STORE)
    controls = []
    for name in args.suite:
        suite = STORE / 'evidence' / name / 'summary.json'
        data = json.loads(suite.read_text())
        assert data['status'] == 'passed' and len(data['controls']) == 66
        for row in data['controls']:
            summary_path = Path(row['summary'])
            assert summary_path.is_relative_to(STORE)
            assert sha(summary_path) == row['summary_sha256']
            summary = json.loads(summary_path.read_text())
            assert summary['control_passed'] and summary['native_exit_code'] == 0
            work = summary_path.parent
            launch = json.loads((work / 'launch/command.json').read_text())
            assert launch['exit_code'] == 0 and not launch.get('timed_out')
            assert launch['inputs_unchanged'] and launch['inputs_before'] == launch['inputs_after']
            assert launch['owned_container_absent']
            assert launch['container']['cpus'] == launch['container']['tool_threads'] == 1
            assert launch['container']['pids'] == 128 and launch['container']['memory_bytes'] == 4294967296
            for record in launch['inputs_before']:
                assert sha(record['path']) == record['sha256'], record['path']
                assert Path(record['path']).stat().st_size == record['bytes']
            for name, digest in launch['logs'].items():
                assert sha(work / 'launch' / name) == digest
            if summary['expected'] == 'pass':
                for mode in ('min', 'max'):
                    reports = list(work.glob('*-' + mode + '.rpt'))
                    assert len(reports) == 3
                    assert all('Startpoint:' in p.read_text() and 'Endpoint:' in p.read_text() for p in reports)
            else:
                assert 'set_false_path' not in (work / 'failed-state.sdc').read_text()
            controls.append({'summary': str(summary_path), 'sha256': sha(summary_path),
                             'tool': summary['tool'], 'case': summary['case']})
    write_new(output, {'status': 'passed', 'controls': len(controls), 'sources': controls,
                       'scope': 'native interface controls, not physical closure'})
    print(f'PASS: {len(controls)} controls; all min/max reports, inputs, logs and cleanup checked')


if __name__ == '__main__':
    main()
