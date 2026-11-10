#!/usr/bin/env python3
"""Freeze historical evidence before v2 continuation; verify without editing it."""
import argparse
import json
from pathlib import Path

from pt7c_probe import ROOT, digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('snapshot', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--baseline', type=Path)
    a = p.parse_args()
    a.output.mkdir(exist_ok=False)
    if a.operation == 'snapshot':
        paths = []
        for base in (ROOT / 'acceptance/pt7c', ROOT / '.dev/asic-pt7c/runs', ROOT / '.dev/asic-pt7c/probe-runs',
                     ROOT / '.dev/asic-pt7c/provider/generations', ROOT / '.dev/asic-pt7c/probe-provider/generations'):
            paths += [path for path in base.rglob('*') if path.is_file() and not path.is_relative_to(a.output.resolve())
                      and path not in (ROOT / 'acceptance/pt7c/native_reader.ml', ROOT / 'acceptance/pt7c/dune')]
        files = {str(path.relative_to(ROOT)): digest(path) for path in sorted(paths)}
        for base, pattern in (('tooling_acceptance/timing/controls', 'pt7c_*.py'), ('tooling_acceptance/timing/basic', 'pt7c_*'), ('docs', 'pt7c_*.md'), ('acceptance/pt7c', 'native_reader.ml')):
            for path in (ROOT / base).glob(pattern):
                if path.is_file():
                    target = a.output / 'continuation-sources' / path.relative_to(ROOT)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
        (a.output / 'historical-files.json').write_text(json.dumps(files, indent=2) + '\n')
    else:
        files = json.loads((a.baseline / 'historical-files.json').read_text())
        changed = [name for name, value in files.items() if not (ROOT / name).is_file() or digest(ROOT / name) != value]
        (a.output / 'verification.json').write_text(json.dumps({'verified_files': len(files), 'changed': changed}, indent=2) + '\n')
        assert not changed, changed


if __name__ == '__main__':
    main()
