"""Record simulator commands and immutable JSON receipts."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def command(output, label, argv, generation=None, expected=(0,), cwd=ROOT, trace=False, timeout=1800):
    directory = output / label
    directory.mkdir()
    argv = list(map(str, argv))
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    if generation:
        env['OCAMLPATH'] = str(generation / 'lib')
        env['PATH'] = str(generation / 'bin') + ':' + env['PATH']
    effective = (['strace', '-f', '-s', '4096', '-e', 'trace=process,file,network', '-o',
                  str(directory / 'syscalls.log'), '--'] + argv) if trace else argv
    start = time.monotonic()
    with (directory / 'stdout.log').open('xb') as out, (directory / 'stderr.log').open('xb') as err:
        try:
            result = subprocess.run(effective, cwd=cwd, env=env, stdout=out, stderr=err,
                                    timeout=timeout)
        except subprocess.TimeoutExpired:
            write(directory / 'timeout.json', {'argv': effective, 'timeout_seconds': timeout})
            raise
    write(directory / 'command.json', {
        'argv': argv, 'effective_argv': effective, 'cwd': str(cwd),
        'exit_code': result.returncode, 'elapsed_seconds': time.monotonic() - start,
        'timeout_seconds': timeout,
        'generation': str(generation) if generation else None,
        'provider_receipt_sha256': sha(generation / 'receipt.json') if generation else None,
        'max_jobs': 6, 'eda_allocation': 0,
        'stdout_sha256': sha(directory / 'stdout.log'),
        'stderr_sha256': sha(directory / 'stderr.log')})
    if result.returncode not in expected:
        raise RuntimeError(f'{label} exit {result.returncode}; retained {directory}')
    if trace:
        lines = (directory / 'syscalls.log').read_text().splitlines()
        execs = [line for line in lines if 'execve(' in line]
        writes = [line for line in lines if
                  re.search(r'\b(open|openat|openat2)\(.*\bO_(WRONLY|RDWR|CREAT|TRUNC)\b', line)
                  or re.search(r'\b(mkdir|mkdirat|unlink|unlinkat|rename|renameat|renameat2|symlink|link|truncate|chmod|utime)\(', line)]
        # The native public CLI exec-replaces itself with its installed native
        # comparison helper. This is one process, not an EDA/tool subprocess.
        allowed = [argv[0]]
        if Path(argv[0]).name == 'hardcaml-asic-flow':
            allowed.append(str(Path(argv[0]).with_name('hardcaml-asic-experimental-compare')))
        assert 1 <= len(execs) <= len(allowed), execs
        assert all(f'execve("{binary}"' in line for binary, line in zip(allowed, execs)), execs
        assert len({line.split()[0] for line in execs}) == 1, execs
        children = [line for line in lines if re.search(r'\b(fork|vfork|clone|clone3)\(', line)]
        assert not children, children
        network = [line for line in lines if re.search(
            r'\b(socket|socketpair|connect|bind|listen|accept|accept4|sendto|sendmsg|recvfrom|recvmsg)\(', line)]
        assert not network, network
        assert not writes, writes
        write(directory / 'readonly.json', {'exec_count': len(execs), 'process_count': 1,
              'exec_replacement_allowlist': allowed, 'write_syscalls': writes,
              'network_syscalls': network,
              'tool_subprocesses': 0, 'renderer_subprocesses': 0,
              'syscalls_sha256': sha(directory / 'syscalls.log')})
    return directory / 'stdout.log'


