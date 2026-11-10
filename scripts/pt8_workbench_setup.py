#!/usr/bin/env python3
"""Explicit private PT8 capture/build/config setup. Never changes root configs."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
import asic_dependency as dep
from pt8_acceptance import sha, write

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '.dev/asic-pt8-workbench'
BUILD = '_build_pt8_workbench'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', default='session-' + uuid.uuid4().hex)
    parser.add_argument('--reuse-provider-session', type=Path,
                        help='reuse an existing immutable ASIC generation; no ASIC rebuild')
    args = parser.parse_args()
    if Path(args.session).name != args.session or args.session in ('.', '..'):
        parser.error('session must be a single new directory name')
    session = BASE / args.session
    session.mkdir(parents=True, exist_ok=False)
    commands = session / 'commands'
    commands.mkdir()
    # Independent source and build closure, never symlinks into the owner checkout.
    project = session / 'project'
    project.mkdir()
    for name in ('dune-project', 'asic-dependency.json', 'README.md'):
        shutil.copyfile(ROOT / name, project / name)
    for name in ('lib', 'asic', 'bin', 'memory', 'variants', 'workloads',
                 'simulation', 'test_support', 'scripts'):
        shutil.copytree(ROOT / name, project / name,
                        ignore=shutil.ignore_patterns('_build*', '__pycache__', '*.pyc'))
    source_files = {str(p.relative_to(project)): sha(p)
                    for p in sorted(project.rglob('*')) if p.is_file()}
    # Reject a copy whose source bytes raced another owner; preserve the partial session.
    assert all(sha(ROOT / name) == digest for name, digest in source_files.items())
    write(session / 'source-snapshot.json', source_files)
    count = 0
    def run(argv, cwd=None, env=None):
        nonlocal count
        count += 1
        argv = list(map(str, argv))
        if argv[0] == 'dune':
            if '-j' not in argv or argv[argv.index('-j') + 1] != '2':
                raise RuntimeError('every nested dune command must explicitly use two jobs')
            if '--build-dir' in argv:
                argv[argv.index('--build-dir') + 1] = BUILD
            else:
                argv += ['--build-dir', BUILD]
        if count == 1 and not args.reuse_provider_session:
            shutil.copytree(cwd, session / 'asic-source', symlinks=True)
        directory = commands / f'{count:02d}'
        directory.mkdir()
        print('SETUP ' + ' '.join(argv), flush=True)
        with (directory / 'stdout.log').open('xb') as out, (directory / 'stderr.log').open('xb') as err:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err, timeout=1800)
        write(directory / 'command.json', {'argv': argv, 'cwd': str(cwd),
            'exit_code': result.returncode, 'max_jobs': 2, 'eda_allocation': 0})
        if result.returncode:
            raise RuntimeError(f'setup failed: see {directory}')
        return (directory / 'stdout.log').read_bytes()
    original = dep.included
    dep.included = lambda name, source, store: not any(
        p.startswith('_build') for p in Path(name).parts) and original(name, source, store)
    # Hold the same shared lock across build, install and nested consumer probes.
    if args.reuse_provider_session:
        previous = args.reuse_provider_session.resolve(strict=True)
        old_manifest = json.loads((previous / 'manifest.json').read_text())
        assert all(sha(previous / 'provider' / name) == digest
                   for name, digest in old_manifest['captured_files'].items())
        generation = Path(old_manifest['generation']).resolve(strict=True)
        write(session / 'reused-provider.json', {'session': str(previous),
            'generation': str(generation), 'receipt_sha256': sha(generation / 'receipt.json')})
    else:
        with open('/tmp/opencode/asic-pt7-build.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            receipt = dep.refresh(ROOT.parent / 'hardcaml_asic', 'development', session / 'asic',
                dep.record_read(ROOT / 'asic-dependency.json'), runner=run, jobs=2)
        generation = Path(receipt['generation'])
    identity = json.loads(run([generation / 'bin/hardcaml-asic-flow', '--version', '--json'], cwd=ROOT))
    assert identity['cli_contract']['capabilities']['workload_inspection1']['max_response_bytes'] == 1048576
    env = dict(os.environ, OCAMLPATH=str(generation / 'lib'),
               HARDCAML_ASIC_GENERATION=str(generation),
               PATH=str(generation / 'bin') + ':' + os.environ['PATH'])
    with open('/tmp/opencode/example-pt7-build.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run(['dune', 'build', '-j', '2', '--root', str(project), '--build-dir', BUILD,
             'workloads/workload_emit.exe', 'workloads/workload_public.exe', 'bin/project.exe'], cwd=project, env=env)
    captured = session / 'provider'
    (captured / 'scripts').mkdir(parents=True)
    (captured / 'simulation').mkdir()
    for name in ('pt8_workbench_provider.py', 'pt8_workbench_runner.py',
                 'pt8_workloads.py', 'pt8_acceptance.py'):
        shutil.copyfile(ROOT / 'scripts' / name, captured / 'scripts' / name)
    shutil.copyfile(ROOT / 'simulation/wire.py', captured / 'simulation/wire.py')
    tools = session / 'tool-bin'
    tools.mkdir()
    shutil.copyfile(ROOT / 'scripts/pt8_workbench_dune.py', tools / 'dune')
    (tools / 'dune').chmod(0o555)
    for name in ('workload_emit', 'workload_public'):
        shutil.copyfile(project / BUILD / 'default/workloads' / (name + '.exe'), captured / (name + '.exe'))
        (captured / (name + '.exe')).chmod(0o555)
    shutil.copyfile(project / BUILD / 'default/bin/project.exe', captured / 'project.exe')
    (captured / 'project.exe').chmod(0o555)
    # Resolve the exact stock model paths through the existing PDK tree.
    pdk = ROOT / '_flow_tools/pdk/ihp-sg13cmos5l'
    matches = list((pdk / 'libs.ref/sg13cmos5l_sram/verilog').resolve(strict=True).glob('RM_IHPSG13_1P_256x16_c2_bm_bist.v'))
    if len(matches) != 1:
        raise RuntimeError(f'expected one stock model under {pdk}, found {len(matches)}')
    models = captured / 'models'
    models.mkdir()
    for name in ('RM_IHPSG13_1P_256x16_c2_bm_bist.v', 'RM_IHPSG13_1P_core_behavioral_bm_bist.v'):
        shutil.copyfile(matches[0].parent / name, models / name)
    provider = [sys.executable, '-B', str(captured / 'scripts/pt8_workbench_provider.py'),
        '--producer-root', str(project), '--generation', str(generation),
        '--emitter', str(captured / 'workload_emit.exe'), '--model-root', str(models)]
    write(session / 'provider-command.json', provider)
    sys.path.insert(0, str(ROOT / 'simulation'))
    from wire import sexp
    (project / 'hardcaml-workbench-preparation.sexp').write_text(sexp([
        ('schema_version', 1), ('build_target', 'bin/project.exe'),
        ('results_root', str(session / 'preparation-results')),
        ('timeout_seconds', 600)]) + '\n')
    (project / 'hardcaml-workbench-simulation.sexp').write_text(sexp([
        ('schema_version', 1), ('provider_executable', provider[0]), ('provider_args', provider[1:]),
        ('discovery_timeout_seconds', 10), ('run_timeout_seconds', 600)]) + '\n')
    (project / 'hardcaml-workbench-asic.sexp').write_text(sexp([
        ('schema_version', 1), ('project_executable', str(captured / 'project.exe')),
        ('provider_executable', str(generation / 'bin/hardcaml-asic-flow')),
        ('results_root', str(session / 'asic-results')), ('toolchain', str(ROOT / '_flow_tools')),
        ('python', [str(ROOT / '_flow_tools/.venv/bin/python')]),
        ('support_tools', [str(ROOT / '_flow_tools/tt')]), ('pdk_root', [str(ROOT / '_flow_tools/pdk')]),
        ('stage_timeout_seconds', ['600'])]) + '\n')
    write(session / 'manifest.json', {'session': str(session), 'project_root': str(project),
        'producer_root': str(project), 'generation': str(generation),
        'source_snapshot': source_files, 'max_jobs': 2,
        'private_source_root': str(project),
        'provider_command': provider, 'real_dune': shutil.which('dune'),
        'wb_build_root': str(ROOT.parent / 'hardcaml_workbench' / BUILD),
        'captured_files': {str(p.relative_to(captured)): sha(p)
                           for p in sorted(captured.rglob('*')) if p.is_file()}})
    for p in project.glob('*.sexp'):
        p.chmod(0o444)
    # Freeze this configured generation. A future setup always creates a new session.
    for p in captured.rglob('*'):
        if p.is_file():
            p.chmod(0o555 if p.suffix == '.exe' else 0o444)
    print(str(session), flush=True)


if __name__ == '__main__':
    main()
