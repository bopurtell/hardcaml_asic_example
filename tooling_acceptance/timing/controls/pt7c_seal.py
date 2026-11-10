#!/usr/bin/env python3
"""Closeout inventory: exact captured provider, handoffs, C files and evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from pt7c_probe import ROOT, digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', required=True)
    a = p.parse_args()
    out = ROOT / 'acceptance/pt7c' / a.attempt
    out.mkdir(exist_ok=False)
    subprocess.run([sys.executable, '-B', str(ROOT / 'tooling_acceptance/timing/controls/pt7c_preservation.py'), 'verify',
                    '--baseline', str(ROOT / 'acceptance/pt7c/original-history.json'),
                    '--output', str(out / 'preservation.json')], check=True)
    generation = (ROOT / '.dev/asic-pt7c/provider/current').resolve(strict=True)
    records = {'generation': str(generation), 'receipt_sha256': digest(generation / 'receipt.json'),
               'provider': json.loads((generation / 'receipt.json').read_text()),
               'installed_files': {str(path.relative_to(generation)): digest(path)
                   for path in generation.rglob('*') if path.is_file()},
               'build_files': {str(path.relative_to(ROOT)): digest(path)
                   for path in (ROOT / '_build_pt7c/default').rglob('*')
                   if path.is_file() and path.suffix in ('.exe', '.cmx', '.cmxa', '.a')}}
    preliminary = (ROOT / '.dev/asic-pt7c/probe-provider/current').resolve(strict=True)
    assert digest(preliminary / 'receipt.json') == '86868912723ba49f8a23fc7775b2870aaec07c02e82024afd1e173d96efa3456'
    records['preliminary_provider'] = {
        'generation': str(preliminary), 'receipt_sha256': digest(preliminary / 'receipt.json'),
        'installed_files': {str(path.relative_to(preliminary)): digest(path)
                            for path in preliminary.rglob('*') if path.is_file()}}
    (out / 'provider.json').write_text(json.dumps(records, indent=2) + '\n')
    for name in ('pt7c-native-handoff.md', 'pt7c-flow-handoff.md', 'pt7c-native-flow.md',
                 'pt7c-native-review.md', 'pt7c-flow-review.md'):
        source = ROOT.parent / 'hardcaml_asic/docs/development' / name
        (out / name).write_bytes(source.read_bytes())
    (out / 'git-status.txt').write_bytes(subprocess.check_output(['git', 'status', '--short'], cwd=ROOT))
    paths = list((ROOT / 'acceptance/pt7c').rglob('*'))
    paths += list((ROOT / 'tooling_acceptance/timing/controls').glob('pt7c_*.py'))
    paths += list((ROOT / 'tooling_acceptance/timing/basic').glob('pt7c_*'))
    paths += list((ROOT / 'docs').glob('pt7c_*.md'))
    files = {str(path.relative_to(ROOT)): digest(path) for path in sorted(paths) if path.is_file()}
    (out / 'checksums.json').write_text(json.dumps(files, indent=2) + '\n')


if __name__ == '__main__':
    main()
