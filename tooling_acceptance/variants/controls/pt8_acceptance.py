#!/usr/bin/env python3
"""Bounded installed PT8 consumer; no EDA command exists in this harness."""
import argparse
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
STORE = ROOT / '.dev/asic-pt8'
EVIDENCE = ROOT / 'acceptance/pt8'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def sources(output):
    inventory = {}
    paths = list((ROOT / 'tooling_acceptance/variants').rglob('*'))
    paths += list((ROOT / 'tooling_acceptance/workloads/controls').glob('pt8*.py'))
    paths += list((ROOT / 'integration/workbench').glob('pt8*.py'))
    for path in sorted(paths):
        if path.is_file():
            relative = path.relative_to(ROOT)
            destination = output / 'consumer-source' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            inventory[str(relative)] = sha(path)
    write(output / 'consumer-source.json', inventory)


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


def capture(output):
    import asic_dependency as dep
    counter = 0

    def runner(argv, cwd=None, env=None):
        nonlocal counter
        counter += 1
        if argv[0] == 'dune':
            assert '-j' in argv and int(argv[argv.index('-j') + 1]) <= 6, argv
        if counter == 1:
            # Keep the exact captured source even if a nested build fails.
            shutil.copytree(cwd, output / 'source-snapshot', symlinks=True)
            write(output / 'source-snapshot.json', {
                str(p.relative_to(cwd)): sha(p) for p in sorted(Path(cwd).rglob('*'))
                if p.is_file() and not p.is_symlink()})
        # dep supplies the captured installed environment for the nested probe.
        directory = output / f'nested-{counter:02d}'
        directory.mkdir()
        with (directory / 'stdout.log').open('xb') as out, (directory / 'stderr.log').open('xb') as err:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err, timeout=1800)
        write(directory / 'command.json', {'argv': list(map(str, argv)), 'cwd': str(cwd),
              'exit_code': result.returncode, 'max_jobs': 6, 'eda_allocation': 0})
        if result.returncode:
            raise dep.Error(f'nested capture failure retained at {directory}')
        return (directory / 'stdout.log').read_bytes()

    dep.refresh(ROOT.parent / 'hardcaml_asic', 'development', STORE / 'provider',
                dep.record_read(ROOT / 'asic-dependency.json'), runner=runner, jobs=6)
    generation = (STORE / 'provider/current').resolve(strict=True)
    write(output / 'generation.json', {'generation': str(generation),
          'receipt_sha256': sha(generation / 'receipt.json'), 'nested_commands': counter})


def compare(output, label, generation, lk, left, rk, right, axis, expected=(0,), timeout=1800):
    cli = generation / 'bin/hardcaml-asic-flow'
    api = ROOT / '_build_pt8/default/tooling_acceptance/variants/variant_cli.exe'
    cli_file = command(output, label + '-cli', [cli, 'compare', '--left-kind', lk,
        '--left', left, '--right-kind', rk, '--right', right, '--axis', axis, '--json'],
        generation, expected, trace=True, timeout=timeout)
    api_file = command(output, label + '-api', [api, 'compare', lk, left, rk, right, axis],
                       generation, expected, trace=True, timeout=timeout)
    if expected == (0,):
        cli_value = json.loads(cli_file.read_text())
        api_value = json.loads(api_file.read_text())
        assert cli_value == api_value, 'installed public API/CLI parity'
        return cli_value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('sources', 'capture', 'capture-inner', 'build', 'functional', 'emit', 'compare'))
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', type=Path)
    parser.add_argument('--left-kind', choices=('bundle', 'execution', 'coarse_run'))
    parser.add_argument('--left', type=Path)
    parser.add_argument('--right-kind', choices=('bundle', 'execution', 'coarse_run'))
    parser.add_argument('--right', type=Path)
    parser.add_argument('--axis', choices=('hardware', 'resource_policy', 'flow_configuration', 'descriptive'))
    parser.add_argument('--reject', action='store_true')
    args = parser.parse_args()
    if Path(args.attempt).name != args.attempt:
        parser.error('attempt must be a single directory name')
    output = EVIDENCE / args.attempt
    output.mkdir(parents=True, exist_ok=False)
    generation = args.generation.resolve(strict=True) if args.generation else None
    if generation:
        assert generation.is_relative_to(STORE / 'provider/generations')
    if args.phase == 'sources':
        sources(output)
    elif args.phase == 'capture':
        command(output, 'capture', ['opam', 'exec', '--switch=5.2.0+ox', '--', 'flock',
                '/tmp/opencode/asic-pt7-build.lock', sys.executable, '-B', __file__,
                'capture-inner', '--attempt', args.attempt + '-nested'])
    elif args.phase == 'capture-inner':
        capture(output)
    elif args.phase == 'build':
        assert generation
        sources(output)
        command(output, 'build', ['opam', 'exec', '--switch=5.2.0+ox', '--', 'flock',
                '/tmp/opencode/example-pt7-build.lock', 'dune', 'build', '--build-dir',
                '_build_pt8', '-j6', 'tooling_acceptance/variants/variant_cli.exe', 'tooling_acceptance/variants/review_api.exe',
                'tooling_acceptance/variants/verif/conformance.exe'], generation)
    elif args.phase == 'functional':
        assert generation
        executable = ROOT / '_build_pt8/default/tooling_acceptance/variants/verif/conformance.exe'
        command(output, 'valid', [executable, 'valid'], generation)
        command(output, 'ignored-depth', [executable, 'ignored'], generation, (1,))
        write(output / 'allocation.json', {'functional_simulations': 6, 'eda_runs': 0})
    elif args.phase == 'emit':
        assert generation
        executable = ROOT / '_build_pt8/default/tooling_acceptance/variants/variant_cli.exe'
        for label, depth, policy, profile, ignored in (
                ('flops128', 128, 'flops', 'balanced', False),
                ('flops256', 256, 'flops', 'balanced', False),
                ('exact256', 256, 'exact', 'balanced', False),
                ('delay256', 256, 'flops', 'synth_delay', False),
                ('ignored128', 128, 'flops', 'balanced', True)):
            command(output, label, [executable, 'emit-ignored-negative' if ignored else 'emit',
                    ROOT, depth, policy, profile, STORE / 'bundles'], generation)
        command(output, 'exact128-rejected', [executable, 'emit', ROOT, 128, 'exact',
                'balanced', STORE / 'bundles'], generation, (2,))
    else:
        assert generation and args.left and args.right and args.axis
        result = compare(output, 'comparison', generation, args.left_kind, args.left,
                         args.right_kind, args.right, args.axis, (2,) if args.reject else (0,))
        if result:
            write(output / 'comparison.json', result)


if __name__ == '__main__':
    main()
