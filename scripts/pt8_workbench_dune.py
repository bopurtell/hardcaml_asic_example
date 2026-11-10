#!/usr/bin/env python3
"""Private-session Dune budget shim for Workbench's stock project probes/actions."""
import os
import sys
import fcntl
from pathlib import Path

argv = sys.argv[1:]
if argv != ['--version']:
    lock = os.open('/tmp/opencode/example-pt7-build.lock', os.O_CREAT | os.O_RDWR, 0o600)
    os.set_inheritable(lock, True)
    fcntl.flock(lock, fcntl.LOCK_EX)
    bounded = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('-j', '--jobs', '--build-dir'):
            i += 2
            continue
        if arg.startswith(('-j', '--jobs=', '--build-dir=')):
            i += 1
            continue
        bounded.append(arg)
        i += 1
    root = Path(os.environ['PT8_PROJECT_ROOT']).resolve(strict=True)
    if Path.cwd().resolve() != root:
        raise RuntimeError('private Dune invocation must run in the captured project')
    # Insert before the target separator. Preparation executes _build/default,
    # so its real build must produce exactly there, inside the private snapshot.
    split = bounded.index('--') if '--' in bounded else len(bounded)
    argv = bounded[:split] + ['-j2', '--build-dir', str(root / '_build')] + bounded[split:]
real = os.environ['PT8_REAL_DUNE']
os.execv(real, [real, *argv])
