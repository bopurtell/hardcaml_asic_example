#!/usr/bin/env python3
"""Public review reproductions on resealed diagnostic copies of REAL v2 evidence.

These are deliberately invalid retained-source assertions, never tool executions
or edits to the successful run. The generic provider owns every interpretation.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from pt7c_probe import ROOT, digest


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, separators=(',', ':')) + '\n')


def reseal(root, corner):
    directory = root / 'timing-intent/corners' / corner
    audit = load(directory / 'audit.json')
    for row in audit['sources']:
        row['sha256'] = digest(directory / row['path'])
    save(directory / 'audit.json', audit)
    runtime = load(root / 'timing-intent/runtime-result.json')
    for row in runtime['audits']:
        row['audit']['sha256'] = digest(root / row['audit']['path'])
    save(root / 'timing-intent/runtime-result.json', runtime)
    companion = load(root / 'timing-intent/analysis.json')
    for row in companion['sources']:
        row['sha256'] = digest(root / row['path'])
    save(root / 'timing-intent/analysis.json', companion)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider', type=Path, required=True)
    p.add_argument('--restored', type=Path, required=True)
    p.add_argument('--attempt', required=True)
    p.add_argument('--case')
    a = p.parse_args()
    original = a.restored.resolve(strict=True)
    output = ROOT / 'acceptance/pt7c' / a.attempt
    output.mkdir(exist_ok=False)
    provider = str(a.provider.resolve(strict=True))
    corner = load(original / 'timing-intent/runtime-result.json')['executed_corners'][0]
    cases = {
        'liberty-executed-list': 'actual native Liberty list differs from retained library associations',
        'wrong-driver-root': 'native process driver differs from retained historical source',
        'wrong-corner-source': 'executed corner script differs from retained source',
        'transport-outcome': 'invalid transport outcome/code',
        'duplicate-cpu': 'transport argv differs from qualified image/resources/executed source paths',
        'failed-success-contradiction': 'transport success contradicts process/cleanup status',
        'native-top': 'native current_design differs from manifest top',
        'continued-comment': 'continued native SDC comment is unsupported',
        'producer-downgrade': "new run's advertised producer declaration is missing",
    }
    summary = {}
    for name, diagnostic in cases.items():
        if a.case and name != a.case:
            continue
        root = output / name
        shutil.copytree(original, root)
        directory = root / 'timing-intent/corners' / corner
        if name == 'liberty-executed-list':
            path = directory / 'native-inputs.json'
            data = load(path)
            data['_CURRENT_CORNER_LIBS'] = '/unrelated/library-0.lib /unrelated/library-1.lib'
            save(path, data)
        elif name == 'wrong-driver-root':
            path = directory / 'process-result.json'
            data = load(path)
            data['argv'][-1] = '/unrelated/driver.tcl'
            save(path, data)
        elif name == 'wrong-corner-source':
            path = directory / 'native-inputs.json'
            data = load(path)
            data['PT7_CORNER_SCRIPT'] = '/unrelated/librelane-corner.tcl'
            save(path, data)
        elif name in ('transport-outcome', 'failed-success-contradiction'):
            path = root / 'timing-intent/transport-result.json'
            data = load(path)
            if name == 'transport-outcome':
                data.update(outcome='timed_out', code=0)
            else:
                data['succeeded'] = False
                companion = load(root / 'timing-intent/analysis.json')
                companion['status'] = 'failed'
                save(root / 'timing-intent/analysis.json', companion)
            save(path, data)
        elif name == 'duplicate-cpu':
            path = root / 'timing-intent/transport.json'
            data = load(path)
            data['argv'].insert(data['argv'].index('--cpus=6') + 1, '--cpus=20')
            save(path, data)
        elif name in ('native-top', 'continued-comment'):
            path = directory / 'native-state.sdc'
            text = path.read_text()
            if name == 'native-top':
                text = text.replace('current_design tt_um_pt7_timing', 'current_design unrelated_top', 1)
            else:
                text = text.replace('set_false_path\\\n', '# reviewed hidden exception\\\nset_false_path\\\n', 1)
            path.write_text(text)
        else:
            path = root / 'project/manifest.json'
            manifest = load(path)
            manifest.pop('timing_native_coverage')
            manifest['files'] = [r for r in manifest['files'] if r['path'] != 'constraints/pt7-native-coverage.tcl']
            save(path, manifest)
            for filename in ('run.json', 'timing-intent/request.json', 'timing-intent/analysis.json'):
                target = root / filename
                data = load(target)
                data['manifest_sha256'] = digest(path)
                if filename == 'run.json':
                    data['bundle'] = '/unavailable-diagnostic-original-bundle'
                save(target, data)
            for filename in ('transport.json', 'transport-result.json'):
                target = root / 'timing-intent' / filename
                data = load(target)
                data['request_sha256'] = digest(root / 'timing-intent/request.json')
                save(target, data)
        reseal(root, corner)
        summary[name] = {}
        commands = (
            ('inspect', ['timing-intent-inspect', str(root), '--kind', 'coarse_run', '--json'], 2),
            ('collect', ['collect', str(root), '--stdout', '--json'], 0),
            ('report', ['report', str(root), '--json'], 1),
            ('archive', ['archive', str(root), '--output', str(output / (name + '-archive')), '--json'], 2),
        )
        for label, arguments, expected in commands:
            argv = [provider, *arguments]
            result = subprocess.run(argv, capture_output=True, timeout=120)
            (output / (name + '-' + label + '.stdout')).write_bytes(result.stdout)
            (output / (name + '-' + label + '.stderr')).write_bytes(result.stderr)
            observed = (result.stdout + result.stderr).decode()
            if name == 'producer-downgrade' and label == 'report':
                expected = 2
                intended = 'bundle manifest payload identity'
            else:
                intended = diagnostic
            summary[name][label] = dict(argv=argv, exit_code=result.returncode, intended_diagnostic=intended)
            save(output / 'summary.json', summary)
            assert result.returncode == expected, (name, label, result.returncode, observed)
            assert intended in observed, (name, label, intended, observed)


if __name__ == '__main__':
    main()
