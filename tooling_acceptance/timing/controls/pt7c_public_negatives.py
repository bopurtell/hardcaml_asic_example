#!/usr/bin/env python3
"""Public source-replay rejection controls, using only NEW restored-run copies."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider', type=Path, required=True)
    p.add_argument('--restored', type=Path, required=True)
    p.add_argument('--attempt', required=True)
    a = p.parse_args()
    provider = str(a.provider.resolve(strict=True))
    original = a.restored.resolve(strict=True)
    output = ROOT / 'acceptance/pt7c' / a.attempt
    output.mkdir(exist_ok=False)
    summary = {}
    for name in ('changed-native-source', 'missing-native-source', 'wrong-run-association'):
        directory = output / name
        shutil.copytree(original, directory)
        analysis = json.loads((directory / 'timing-intent/analysis.json').read_text())
        if name == 'wrong-run-association':
            analysis['run_id'] = 'unrelated-diagnostic-attempt'
            (directory / 'timing-intent/analysis.json').write_text(json.dumps(analysis) + '\n')
            diagnostic = 'companion/run mismatch: run_id'
        else:
            relative = next(row['path'] for row in analysis['sources'] if row['path'].endswith('/native-data.json'))
            path = directory / relative
            if name == 'changed-native-source':
                path.write_bytes(path.read_bytes() + b'\n')
                diagnostic = 'changed source:'
            else:
                path.unlink()
                diagnostic = 'native-data.json'
        commands = {
            'inspect': ([provider, 'timing-intent-inspect', str(directory), '--kind', 'coarse_run', '--json'], (2,)),
            'collect': ([provider, 'collect', str(directory), '--stdout', '--json'], (0,)),
            'report': ([provider, 'report', str(directory), '--json'], (1,)),
            'archive': ([provider, 'archive', str(directory), '--output', str(output / (name + '-archive')), '--json'], (2,)),
        }
        summary[name] = {}
        for label, (argv, expected) in commands.items():
            result = subprocess.run(argv, capture_output=True, timeout=120)
            (output / (name + '-' + label + '.stdout')).write_bytes(result.stdout)
            (output / (name + '-' + label + '.stderr')).write_bytes(result.stderr)
            assert result.returncode in expected, (name, label, result.returncode)
            assert diagnostic in (result.stdout + result.stderr).decode(), (name, label, diagnostic)
            summary[name][label] = {'argv': argv, 'exit_code': result.returncode, 'diagnostic': diagnostic}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
