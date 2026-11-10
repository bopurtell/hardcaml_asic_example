#!/usr/bin/env python3
"""Assert real native fixtures through the generic provider reader, no local parser."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--attempt', required=True)
    p.add_argument('--controls', required=True)
    p.add_argument('--view', type=Path)
    p.add_argument('--top', required=True)
    a = p.parse_args()
    output = ROOT / 'acceptance/pt7c' / a.attempt
    output.mkdir(exist_ok=False)
    rows = []
    if a.view:
        rows = json.loads(a.view.read_text())['corners'][0]['resolved']['exceptions']
    else:
        for line in (ROOT / 'acceptance/timing/sta-scalar-r3/resolution.log').read_text().splitlines():
            row = json.loads(line.split('\t', 1)[1])
            if row['event'] == 'resolved':
                rows.append(row)
    resolution = output / 'resolution.json'
    resolution.write_text(json.dumps(rows, indent=2) + '\n')
    results = {}
    diagnostics = {
        'capture-removed': 'missing exception relations',
        'capture-broad': 'extra exception relations',
        'extra-relation': 'extra exception relations',
        'capture-setup-only': 'restricted/unsupported false-path option',
        'capture-hold-only': 'restricted/unsupported false-path option',
        'capture-rise-only': 'restricted/unsupported false-path option',
        'masking': 'unsupported native SDC command: set_disable_timing',
        'missing-category': 'missing/reordered/duplicate diagnostic categories',
        'incomplete': 'unsupported/incomplete native wire',
        'endpoint-count': 'count mismatch',
        'raw-report-mismatch': 'native check report differs from diagnostic groups',
        'truncated-state': 'truncated native SDC',
    }

    def check(name, directory, expected, diagnostic=None):
        diagnostic = diagnostic or diagnostics.get(name)
        result = subprocess.run([str(a.reader.resolve()), str(resolution), str(directory), a.top], capture_output=True)
        (output / (name + '.stdout')).write_bytes(result.stdout)
        (output / (name + '.stderr')).write_bytes(result.stderr)
        assert result.returncode == expected, (name, result.returncode, result.stderr.decode())
        if diagnostic:
            assert diagnostic in result.stderr.decode(), (name, result.stderr.decode())
        results[name] = {'exit_code': result.returncode, 'diagnostic': diagnostic}
        if expected == 0:
            return json.loads(result.stdout)

    for name in ('baseline', 'no-input-delay', 'no-output-delay', 'no-clock'):
        directory = ROOT / 'acceptance/pt7c' / (a.controls + '-' + name)
        check(name, directory, 0)
        data = json.loads((directory / 'native-data.json').read_text())
        assert len(data['categories']) == 7 and data['endpoint_count'] == 12
        groups = {c['name']: c['groups'] for c in data['categories']}
        if name == 'baseline':
            assert all(not group for group in groups.values())
        if name == 'no-input-delay':
            assert len(groups['no_input_delay'][0]['details']) == 18
        if name == 'no-output-delay':
            assert len(groups['no_output_delay'][0]['details']) == 2
        if name == 'no-clock':
            assert len(groups['no_clock'][0]['details']) == 5
            assert len(groups['unconstrained_endpoints'][0]['details']) == 7
    for name in ('capture-removed', 'capture-broad', 'capture-setup-only', 'capture-hold-only',
                 'capture-rise-only', 'extra-relation', 'masking'):
        check(name, ROOT / 'acceptance/pt7c' / (a.controls + '-' + name), 2)

    baseline = ROOT / 'acceptance/pt7c' / (a.controls + '-baseline')
    # Coherent and incoherent wire negatives: all preserved in new directories.
    for name in ('missing-category', 'incomplete', 'endpoint-count', 'raw-report-mismatch', 'truncated-state'):
        directory = output / name
        shutil.copytree(baseline, directory)
        data = json.loads((directory / 'native-data.json').read_text())
        if name == 'missing-category':
            data['categories'].pop()
        elif name == 'incomplete':
            data['complete'] = False
        elif name == 'endpoint-count':
            data['endpoint_count'] += 1
        elif name == 'raw-report-mismatch':
            (directory / 'native-checks.rpt').write_text('HC_ASIC_NATIVE_CHECKS_COMPLETE\nextra\n')
        elif name == 'truncated-state':
            (directory / 'native-state.sdc').write_text('set_false_path -from [get_ports {ena}] -to [')
        (directory / 'native-data.json').write_text(json.dumps(data) + '\n')
        check(name, directory, 2)
    (output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
