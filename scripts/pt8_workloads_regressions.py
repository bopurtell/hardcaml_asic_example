#!/usr/bin/env python3
"""Actual installed same-process FD and deterministic late raw-generation controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time

import pt8_workloads as p
from pt8_workloads_acceptance import load, replace


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--attempt', required=True)
    ap.add_argument('--generation', type=Path, required=True)
    a = ap.parse_args()
    out = p.EVIDENCE / a.attempt
    out.mkdir()
    generation = a.generation.resolve(strict=True)
    api = p.BUILD / 'workload_public.exe'
    cli = generation / 'bin/hardcaml-asic-flow'
    directory = out / 'rejected-directory'
    directory.mkdir()
    fd = load(p.command(out, 'directory-fds', [api, 'directory-fds', directory],
                        generation, trace=True, timeout=180))
    assert fd['iterations'] == 500 and fd['growth'] == 0
    assert fd['fd_before'] == fd['fd_after']
    p.command(out, 'compile-fence', ['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra',
        '-o', out / 'late_fence.so', p.ROOT / 'workloads/late_fence.c', '-ldl'])
    paths = {}
    for side, label in [('left', 'flops'), ('right', 'exact')]:
        work = out / (side + '-workload')
        shutil.copytree(p.EVIDENCE / 'simulation-04' / label, work)
        result = load(work / 'result.json')
        bundle = out / (side + '-bundle')
        shutil.copytree(result['bundle'], bundle)
        result['bundle'] = str(bundle)
        replace(work / 'result.json', result)
        paths[side] = bundle, work / 'result.json'
    lb, lw = paths['left']
    rb, rw = paths['right']
    commands = {
        'api': list(map(str, [api, 'compare', lb, rb, lw, rw])),
        'cli': list(map(str, [cli, 'compare', '--left-kind', 'bundle', '--left', lb,
            '--right-kind', 'bundle', '--right', rb, '--axis', 'resource_policy',
            '--left-workload', lw, '--right-workload', rw, '--json']))}
    for kind, argv in commands.items():
        value = load(p.command(out, 'clean-' + kind, argv, generation, trace=True, timeout=180))
        assert len([m for m in value['metrics'] if m['metric_id'].startswith('workload/')
                    and m['comparison'] == 'comparable']) == 7
    sources = {'opposite-workload': lw.parent / 'trace.json',
               'opposite-target-manifest': lb / 'manifest.json',
               'opposite-target-rtl': lb / load(lb / 'manifest.json')['synthesis_sources'][0]}
    checks = []
    for kind, argv in commands.items():
        for label, source in sources.items():
            d = out / (label + '-' + kind)
            d.mkdir()
            original = source.read_bytes()
            # Whitespace-only mutation keeps JSON/RTL parseable. A semantic replay
            # of the already-completed opposite side cannot detect this afterward.
            assert original.endswith(b'\n')
            changed = original[:-1] + b' '
            nr, nw = os.pipe()
            rr, release = os.pipe()
            env = dict(os.environ, OCAMLPATH=str(generation / 'lib'),
                PATH=str(generation / 'bin') + ':' + os.environ['PATH'],
                LD_PRELOAD=str(out / 'late_fence.so'), PT8_NOTIFY=str(nw), PT8_RELEASE=str(rr))
            started = time.monotonic()
            process = subprocess.Popen(argv, cwd=p.ROOT, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, pass_fds=(nw, rr))
            try:
                assert select.select([nr], [], [], 30)[0], 'seventh workload open not reached'
                assert os.read(nr, 1) == b'R'
                source.write_bytes(changed)
                replace(d / 'mutation.json', {'source': str(source),
                    'before_raw_sha256': hashlib.sha256(original).hexdigest(),
                    'after_raw_sha256': p.sha(source), 'changed_before_release': True,
                    'trigger': 'result.json open7: right deep recheck after left deep recheck'})
                os.write(release, b'R')
                stdout, stderr = process.communicate(timeout=180)
                (d / 'stdout.log').write_bytes(stdout)
                (d / 'stderr.log').write_bytes(stderr)
                receipt = {'argv': argv, 'exit_code': process.returncode,
                    'elapsed_seconds': time.monotonic() - started,
                    'provider_generation': str(generation),
                    'provider_receipt_sha256': p.sha(generation / 'receipt.json'),
                    'preload_sha256': p.sha(out / 'late_fence.so'),
                    'executable_sha256': p.sha(Path(argv[0])),
                    'stdout_sha256': p.sha(d / 'stdout.log'), 'stderr_sha256': p.sha(d / 'stderr.log'),
                    'test_only_interposition': True, 'max_jobs': 1, 'eda_allocation': 0}
                p.write(d / 'command.json', receipt)
                assert process.returncode == 2 and not stdout, (stdout, stderr)
                assert b'final raw source generation changed' in stderr, stderr
                checks.append({'kind': kind, 'source': label, 'exit': process.returncode,
                               'error': stderr.decode().strip()})
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                for f in (nr, nw, rr, release):
                    os.close(f)
                source.write_bytes(original)
    p.write(out / 'assertions.json', {'pass': True, 'directory_fd': fd,
        'late_mutations': checks, 'additional_simulations': 0,
        'generation': str(generation), 'fence_source_sha256': p.sha(p.ROOT / 'workloads/late_fence.c')})


if __name__ == '__main__':
    main()
