#!/usr/bin/env python3
"""Hash original example sources/history; verify without changing any originals."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('snapshot', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    if args.operation == 'snapshot':
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        paths = {ROOT / p for p in tracked if p}
        for name in ('acceptance/timing', 'acceptance/resource-inspector', 'acceptance/resource-measurements'):
            paths.update(p for p in (ROOT / name).rglob('*') if p.is_file())
        # Old provider pointer/configuration receipts are protected explicitly.
        for base in (ROOT / '.dev').iterdir():
            if base.name == 'asic-pt7c':
                continue
            for name in ('provider/current', 'provider/active.json', 'provider-inputs.json'):
                candidate = base / name
                if candidate.is_symlink():
                    paths.add(candidate)
        result = {'files': {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths) if p.is_file()},
                  'symlinks': {str(p.relative_to(ROOT)): str(p.readlink()) for p in sorted(paths) if p.is_symlink()}}
    else:
        baseline = json.loads(args.baseline.read_text())
        failures = [name for name, value in baseline['files'].items()
                    if not (ROOT / name).is_file() or sha(ROOT / name) != value]
        failures += [name for name, value in baseline['symlinks'].items()
                     if not (ROOT / name).is_symlink() or str((ROOT / name).readlink()) != value]
        result = {'verified_files': len(baseline['files']), 'failures': failures}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    if result.get('failures'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
