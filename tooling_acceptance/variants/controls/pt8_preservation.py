#!/usr/bin/env python3
"""Read-only seal of pre-existing sources, histories, and provider selections."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
EXCLUDED = {'.git', '_build_pt8', '__pycache__'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def owned(path):
    parts = path.relative_to(ROOT).parts
    return (parts[:2] == ('tooling_acceptance', 'variants') or parts[:2] in
            (('acceptance', 'pt8'), ('.dev', 'asic-pt8')) or
            (parts[0] in ('scripts', 'docs') and parts[-1].startswith('pt8')))


def snapshot():
    # Include ignored stores: histories/providers are often absent from git status.
    paths = set()
    for base in ('acceptance', '.dev', '_flow_results', 'tooling_acceptance/timing',
                 'scripts', 'docs'):
        paths.update(p for p in (ROOT / base).rglob('*')
                     if not owned(p) and not EXCLUDED.intersection(p.relative_to(ROOT).parts)
                     and (p.is_file() or p.is_symlink()))
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    paths.update(ROOT / name for name in tracked if name and (ROOT / name).exists())
    return {'files': {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)
                      if p.is_file() and not p.is_symlink()},
            'symlinks': {str(p.relative_to(ROOT)): str(p.readlink()) for p in sorted(paths)
                         if p.is_symlink()}}


def verify(baseline):
    failures = [name for name, digest in baseline['files'].items()
                if not (ROOT / name).is_file() or (ROOT / name).is_symlink()
                or sha(ROOT / name) != digest]
    failures += [name for name, target in baseline['symlinks'].items()
                 if not (ROOT / name).is_symlink() or str((ROOT / name).readlink()) != target]
    return {'verified_files': len(baseline['files']),
            'verified_symlinks': len(baseline['symlinks']), 'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('snapshot', 'verify'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    result = snapshot() if args.operation == 'snapshot' else verify(json.loads(args.baseline.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    if result.get('failures'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
