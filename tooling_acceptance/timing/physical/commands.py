#!/usr/bin/env python3
"""Isolated physical timing command receipts; no timing interpretation."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / '.dev/asic-timing-physical'
IMAGE = 'sha256:d109140b8f17fc54f4fca998beb8124f4949404ec52e339eebd2250854a18b5a'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(Path(root).rglob('*'))
            if p.is_file() and not p.is_symlink()}


def identity(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def command(output, argv, *, generation=None, inputs=(), timeout=900, container=None):
    output = Path(output).resolve()
    if not output.is_relative_to(STORE):
        raise ValueError('receipts must be inside .dev/asic-timing-physical')
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'OPENROAD_THREADS', '_OPENLANE_MAX_CORES'):
        env[key] = '1'
    if generation:
        generation = Path(generation).resolve(strict=True)
        if not generation.is_relative_to(STORE / 'provider/generations'):
            raise ValueError('provider must be from the new physical store')
        env['OCAMLPATH'] = str(generation / 'lib') + (':' + env['OCAMLPATH'] if env.get('OCAMLPATH') else '')
        env['PATH'] = str(generation / 'bin') + ':' + env['PATH']
    argv = list(map(str, argv))
    before = [identity(p) for p in inputs]
    receipt = {'argv': argv, 'cwd': str(ROOT), 'timeout_seconds': timeout,
               'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'allocation_workers': 6, 'sta_threads': 1, 'serialized': True,
               'generation': str(generation) if generation else None,
               'inputs_before': before, 'launcher': identity(__file__)}
    if generation:
        receipt['provider_receipt'] = identity(generation / 'receipt.json')
    if container:
        receipt['container'] = container
    write_new(output / 'prepared.json', receipt)
    # All C operations, including captures/builds, serialize under this lock.
    with Path('/tmp/opencode/example-timing-physical.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if before != [identity(p) for p in inputs]:
            raise RuntimeError('inputs changed while waiting for allocation')
        start = time.monotonic()
        with (output / 'stdout.log').open('xb') as out, (output / 'stderr.log').open('xb') as err:
            try:
                process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=out,
                                           stderr=err, start_new_session=True)
                try:
                    code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    receipt['timed_out'] = True
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    code = 124
            except OSError as exc:
                code = 127
                receipt['launch_error'] = str(exc)
            finally:
                if container:
                    receipt['owned_container_absent'] = False
                    try:
                        cleanup = subprocess.run(['docker', 'rm', '-f', container['name']],
                                                 capture_output=True, timeout=30)
                        (output / 'cleanup.stdout').write_bytes(cleanup.stdout)
                        (output / 'cleanup.stderr').write_bytes(cleanup.stderr)
                        # --rm may already have removed this exact owned container.
                        receipt['cleanup_exit_code'] = cleanup.returncode
                        check = subprocess.run(['docker', 'container', 'inspect', container['name']],
                                               capture_output=True, timeout=30)
                        (output / 'cleanup-inspect.stdout').write_bytes(check.stdout)
                        (output / 'cleanup-inspect.stderr').write_bytes(check.stderr)
                        receipt['owned_container_absent'] = check.returncode != 0 and b'No such' in check.stderr
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        receipt['cleanup_error'] = str(exc)
        receipt.update(exit_code=code, elapsed_seconds=time.monotonic() - start,
                       inputs_after=[identity(p) for p in inputs],
                       logs={name: sha(output / name) for name in ('stdout.log', 'stderr.log')})
        receipt['inputs_unchanged'] = receipt['inputs_after'] == before
        write_new(output / 'command.json', receipt)
    if not receipt['inputs_unchanged'] or (container and not receipt['owned_container_absent']):
        raise RuntimeError(f'input/cleanup failure: {output}')
    return code


def native(output, work, tool, inputs, mounts, arguments, timeout=180):
    if tool not in ('openroad', 'sta'):
        raise ValueError('only native ODB/STA diagnostics are admitted')
    work = Path(work).resolve(strict=True)
    if not work.is_relative_to(STORE) or work == STORE:
        raise ValueError('native work must belong to the new physical store')
    mounts = [Path(p).resolve(strict=True) for p in mounts]
    for path in inputs:
        path = Path(path).resolve(strict=True)
        if not path.is_relative_to(work) and not any(path == m or path.is_relative_to(m) for m in mounts):
            raise ValueError(f'unmounted input: {path}')
    name = 'asic-timing-physical-' + str(os.getpid())
    argv = ['docker', 'run', '--name', name, '--rm', '--pull=never', '--network=none',
            '--read-only', '--cpus=1', '--memory=4g', '--pids-limit=128',
            '--user', f'{os.getuid()}:{os.getgid()}', '--tmpfs', '/tmp:rw,nosuid,size=256m',
            '--mount', f'type=bind,src={work},dst={work}', '--workdir', str(work)]
    for mount in mounts:
        if mount == work or work.is_relative_to(mount):
            raise ValueError('read-only mount would overlap writable work')
        argv += ['--mount', f'type=bind,src={mount},dst={mount},readonly']
    for variable in ('OMP_NUM_THREADS', 'OPENROAD_THREADS', 'OPENBLAS_NUM_THREADS',
                     'MKL_NUM_THREADS', '_OPENLANE_MAX_CORES'):
        argv += ['--env', variable + '=1']
    argv += ['--entrypoint', tool, IMAGE, '-threads', '1', *map(str, arguments)]
    return command(output, argv, inputs=inputs, timeout=timeout,
                   container={'name': name, 'cpus': 1, 'memory_bytes': 4294967296,
                              'pids': 128, 'tool_threads': 1, 'image': IMAGE})
