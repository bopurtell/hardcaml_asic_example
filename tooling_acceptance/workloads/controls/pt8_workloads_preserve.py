#!/usr/bin/env python3
"""Preserve all pre-existing regular files/symlinks outside build caches and C scope."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'acceptance/pt8-workloads'


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def owned(p):
    s = p.relative_to(ROOT).as_posix()
    return (s.startswith(('tooling_acceptance/workloads/', 'acceptance/pt8-workloads/',
                          '.dev/asic-pt8-workloads/', '_build_pt8_workloads/'))
            or s == 'docs/pt8_workloads_final.md')


def snapshot():
    files, links = {}, {}
    for base, dirs, names in os.walk(ROOT, followlinks=False):
        p = Path(base)
        dirs[:] = [d for d in dirs if d != '.git' and not d.startswith('_build')
                   and d != '__pycache__' and not owned(p / d / 'placeholder')]
        for name in names + [d for d in dirs if (p / d).is_symlink()]:
            q = p / name
            if owned(q):
                continue
            rel = q.relative_to(ROOT).as_posix()
            if q.is_symlink():
                links[rel] = str(q.readlink())
            elif q.is_file():
                files[rel] = sha(q)
    return {'files': files, 'symlinks': links,
            'git_status': subprocess.check_output(['git', 'status', '--porcelain=v1',
                '--untracked-files=all'], cwd=ROOT).decode(),
            'git_diff': subprocess.check_output(['git', 'diff', '--binary'], cwd=ROOT).decode(),
            'excluded': ['.git', '_build*', '__pycache__', 'new C scope']}


def main():
    if sys.argv[1] == 'baseline':
        value = snapshot()
    else:
        old = json.loads((OUT / 'preservation-baseline.json').read_text())
        failures = [s for s, h in old['files'].items()
                    if not (ROOT / s).is_file() or (ROOT / s).is_symlink() or sha(ROOT / s) != h]
        failures += [s for s, t in old['symlinks'].items()
                     if not (ROOT / s).is_symlink() or str((ROOT / s).readlink()) != t]
        value = {'files': len(old['files']), 'symlinks': len(old['symlinks']), 'failures': failures}
    with (OUT / ('preservation-' + sys.argv[1] + '.json')).open('x') as f:
        json.dump(value, f, indent=2)
    assert not value.get('failures'), value.get('failures')


if __name__ == '__main__':
    main()
