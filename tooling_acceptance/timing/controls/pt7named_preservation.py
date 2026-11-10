#!/usr/bin/env python3
"""Seal pre-existing example inputs and PT7 histories without altering them."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot():
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    paths = {ROOT / name for name in names if name}
    for directory in ('acceptance/timing', 'acceptance/pt7c', 'acceptance/resource-inspector',
                      'acceptance/resource-measurements', 'tooling_acceptance/timing', 'scripts', 'docs'):
        paths.update(p for p in (ROOT / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts
                     and not p.name.startswith('pt7named'))
    for base in (ROOT / '.dev').iterdir():
        if base.name == 'asic-pt7named':
            continue
        for name in ('provider/current', 'provider/active.json', 'provider-inputs.json'):
            path = base / name
            if path.exists() or path.is_symlink():
                paths.add(path)
    return {'files': {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths) if p.is_file()},
            'symlinks': {str(p.relative_to(ROOT)): str(p.readlink())
                         for p in sorted(paths) if p.is_symlink()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('snapshot', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    if args.operation == 'snapshot':
        result = snapshot()
    else:
        baseline = json.loads(args.baseline.read_text())
        failures = [name for name, digest in baseline['files'].items()
                    if not (ROOT / name).is_file() or sha(ROOT / name) != digest]
        failures.extend(name for name, target in baseline['symlinks'].items()
                        if not (ROOT / name).is_symlink() or str((ROOT / name).readlink()) != target)
        result = {'verified_files': len(baseline['files']), 'failures': failures}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    if result.get('failures'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
