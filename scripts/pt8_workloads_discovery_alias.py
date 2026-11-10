#!/usr/bin/env python3
"""Installed F2/B-A1 controls on disposable, explicitly synthetic coarse fixtures."""
import argparse
import importlib.util
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
    ap.add_argument('--capture', required=True)
    a = ap.parse_args()
    out = p.EVIDENCE / a.attempt
    out.mkdir()
    generation = a.generation.resolve(strict=True)
    fixture_source = p.EVIDENCE / a.capture / 'source-snapshot/test/check_resource_evidence.py'
    shutil.copyfile(fixture_source, out / 'captured-fixture.py')
    spec = importlib.util.spec_from_file_location('captured_coarse_fixture', fixture_source)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    coarse = out / 'synthetic-coarse-not-executed'
    coarse.mkdir()
    flow, _, record = fixture.fixture(coarse)
    sim = p.EVIDENCE / 'simulation-04'
    lw, rw = sim / 'flops/result.json', sim / 'exact/result.json'
    lr, rr = load(lw), load(rw)
    shutil.copytree(lr['bundle'], coarse / 'project', dirs_exist_ok=True)
    record.update(build_identity=load(Path(lr['bundle']) / 'manifest.json')['identity'],
                  manifest_sha256=p.sha(coarse / 'project/manifest.json'))
    replace(coarse / 'run.json', record)
    api, cli = p.BUILD / 'workload_public.exe', generation / 'bin/hardcaml-asic-flow'
    commands = {
        'api': list(map(str, [api, 'targets', 'coarse_run', coarse, 'bundle', rr['bundle'], lw, rw])),
        'cli': list(map(str, [cli, 'compare', '--left-kind', 'coarse_run', '--left', coarse,
            '--right-kind', 'bundle', '--right', rr['bundle'], '--axis', 'resource_policy',
            '--left-workload', lw, '--right-workload', rw, '--json']))}
    p.command(out, 'compile-fence', ['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra',
        '-o', out / 'late_fence.so', p.ROOT / 'workloads/late_fence.c', '-ldl'])
    checks = []

    def clean(label):
        values = [load(p.command(out, label + '-' + kind, argv, generation, trace=True, timeout=180))
                  for kind, argv in commands.items()]
        assert values[0] == values[1], 'complete API/CLI parity'
        metrics = [m for m in values[0]['metrics'] if m['metric_id'].startswith('workload/')]
        assert len(metrics) == 7 and all(m['comparison'] == 'comparable' for m in metrics)
        return values[0]

    def late(kind, label, action, expected):
        d = out / (label + '-' + kind)
        d.mkdir()
        nr, nw = os.pipe()
        release_read, release_write = os.pipe()
        env = dict(os.environ, OCAMLPATH=str(generation / 'lib'),
            PATH=str(generation / 'bin') + ':' + os.environ['PATH'],
            LD_PRELOAD=str(out / 'late_fence.so'), PT8_OPEN_COUNT='5',
            PT8_NOTIFY=str(nw), PT8_RELEASE=str(release_read))
        started = time.monotonic()
        process = subprocess.Popen(commands[kind], cwd=p.ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(nw, release_read))
        try:
            assert select.select([nr], [], [], 30)[0], 'deep replay boundary not reached'
            assert os.read(nr, 1) == b'R'
            action()
            p.write(d / 'mutation.json', {'trigger': 'result.json open5 before left workload recheck',
                'action': label, 'completed_before_release': True,
                'scope': 'synthetic disposable fixture; original simulations unmodified'})
            os.write(release_write, b'R')
            stdout, stderr = process.communicate(timeout=180)
            (d / 'stdout.log').write_bytes(stdout)
            (d / 'stderr.log').write_bytes(stderr)
            p.write(d / 'command.json', {'argv': commands[kind], 'exit_code': process.returncode,
                'elapsed_seconds': time.monotonic() - started, 'provider_generation': str(generation),
                'executable_sha256': p.sha(Path(commands[kind][0])),
                'preload_sha256': p.sha(out / 'late_fence.so'), 'max_jobs': 1, 'eda_allocation': 0,
                'stdout_sha256': p.sha(d / 'stdout.log'), 'stderr_sha256': p.sha(d / 'stderr.log')})
            assert process.returncode == 2 and not stdout and expected.encode() in stderr, (stdout, stderr)
            checks.append({'kind': kind, 'case': label, 'error': stderr.decode().strip()})
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            for fd in (nr, nw, release_read, release_write):
                os.close(fd)

    checks_root = coarse / 'checks'
    for state in ('absent', 'empty', 'child-without-postcheck'):
        for kind in commands:
            if state != 'absent':
                checks_root.mkdir()
            if state == 'child-without-postcheck':
                (checks_root / 'existing-child').mkdir()
            clean(state + '-' + kind + '-clean')
            def add_postcheck():
                child = checks_root / ('existing-child' if state == 'child-without-postcheck' else 'new-child')
                child.mkdir(parents=True, exist_ok=True)
                replace(child / 'postcheck.json', {'status': 'failed',
                    'checks': {'precheck': 'fail', 'gate_level': 'fail'}})
            try:
                late(kind, state, add_postcheck, 'postcheck discovery generation changed')
            finally:
                if checks_root.exists():
                    shutil.rmtree(checks_root)
    canonical = clean('canonical-flow')
    actual = flow.with_name('asic-real')
    flow.rename(actual)
    flow.symlink_to(actual.name, target_is_directory=True)
    aliased = clean('permitted-flow-alias')
    assert canonical['left']['outcomes'] == aliased['left']['outcomes']
    alternate = flow.with_name('asic-alternate')
    shutil.copytree(actual, alternate)
    for kind in commands:
        def retarget():
            flow.unlink()
            flow.symlink_to(alternate.name, target_is_directory=True)
        try:
            late(kind, 'alias-retarget-identical-bytes', retarget, 'final raw source alias changed')
        finally:
            flow.unlink()
            flow.symlink_to(actual.name, target_is_directory=True)
    p.write(out / 'assertions.json', {'pass': True, 'checks': checks,
        'permitted_internal_alias': 'admitted_in_API_and_CLI_with_identical_outcomes',
        'api_cli_parity': True, 'fixture_source_sha256': p.sha(fixture_source),
        'generation': str(generation), 'scope': 'synthetic reader controls, not new hardware/physical execution',
        'additional_simulations': 0, 'eda_runs': 0})


if __name__ == '__main__':
    main()
