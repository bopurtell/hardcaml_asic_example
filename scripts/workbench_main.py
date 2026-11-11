#!/usr/bin/env python3
"""Persistent Workbench on this checkout. Preparation never starts a server.

Simulation helper handoff: supply a regular FS2 configuration with --simulation-config.
Its provider_args must select integration/workbench/checkout_provider.py and an
absolute --manifest whose project_root is this checkout. The simulation helper owns
that manifest and its refresh/build policy; this launcher only publishes companions.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid
from urllib.parse import urlparse

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/workbench'))
from wire import parse, record, sexp
import config_location
sys.path.insert(0, str(ROOT / 'scripts'))
from workbench_git import clean_environment

KINDS = ('asic', 'preparation', 'simulation')
TARGETS = ('asics/fifo_demo/cli/project.exe',
           'ip/controlled_fifo/verif/simulation/test_provider.exe',
           'ip/controlled_fifo/verif/simulation/fifo_sim.exe',
           'tooling_acceptance/workloads/workload_emit.exe',
           'tooling_acceptance/workloads/workload_public.exe')
GENERATION = '36205ea4748c4972877ac198356d8e44'
SWITCH_BIN = Path.home() / '.opam/5.2.0+ox/bin'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(path, missing=False):
    """Never read through a symlink configuration or ownership record."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise
    if not stat.S_ISREG(info.st_mode) or path.parent.resolve() != path.parent:
        raise RuntimeError('expected independent regular file: ' + str(path))
    return path.read_bytes()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.resolve() != path.parent:
        raise RuntimeError('symlinked destination: ' + str(path))
    pending = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with pending.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        pending.unlink(missing_ok=True)


def json_write(path, value):
    write(path, (json.dumps(value, indent=2) + '\n').encode())


@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('owner/build lock held: ' + str(path)) from None
        yield fd
    finally:
        os.close(fd)


def unlocked(path):
    if not path.exists():
        return True
    with path.open('rb') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False


def environment(root, store, asic, sdk, inherited=None):
    env = clean_environment(os.environ if inherited is None else inherited)
    # Captured-session selectors and the opt-in synthesis-only envelope must not leak.
    for name in list(env):
        if name.startswith(('PT8_', 'HARDCAML_WORKBENCH_', 'SSH_')) or name in (
                'HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT', 'TMUX', 'TMUX_PANE'):
            env.pop(name)
    env.update(OCAMLPATH=str(asic / 'lib') + ':' + str(sdk / 'lib'),
               HARDCAML_ASIC_GENERATION=str(asic),
               # Reconstruct from selected installations, never filter an inherited
               # PATH by a list of known acceptance directories.
               PATH=os.pathsep.join(map(str, (SWITCH_BIN, asic / 'bin', Path('/usr/bin'), Path('/bin')))),
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(store / 'tmp'), PWD=str(root))
    return env


def selected_tools(env):
    expected = dict(dune=SWITCH_BIN / 'dune', git=Path('/usr/bin/git'), python=Path('/usr/bin/python3'))
    result = {}
    for name, path in expected.items():
        actual = shutil.which('python3' if name == 'python' else name, path=env['PATH'])
        if actual is None or Path(actual).resolve(strict=True) != path.resolve(strict=True):
            raise RuntimeError('selected PATH does not resolve intended tool: ' + name)
        if name in ('dune', 'git'):
            with path.open('rb') as stream:
                if stream.read(4) != b'\x7fELF':
                    raise RuntimeError('intended tool is not a native executable: ' + str(path))
        result[name] = str(path.resolve(strict=True))
    return result


def verify_tools(root, env):
    tools = selected_tools(env)
    # Resolve in an actual child with precisely the environment given to builds.
    probe = subprocess.run([tools['python'], '-c',
        'import json,os,shutil; print(json.dumps({n:os.path.realpath(shutil.which(n)) for n in ("dune","git","python3")}))'],
        cwd=root, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    found = json.loads(probe.stdout)
    if found != {'dune': tools['dune'], 'git': tools['git'], 'python3': tools['python']}:
        raise RuntimeError('subprocess resolved unexpected tools')
    versions = {}
    for name in ('dune', 'git'):
        probe = subprocess.run([tools[name], '--version'], cwd=root, env=env, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        versions[name] = probe.stdout.decode().strip()
    version = tuple(int(part) for part in versions['dune'].split('.')[:2])
    if version < (3, 22):
        raise RuntimeError('Dune 3.22 or newer is required')
    return dict(paths=tools, versions=versions)


def option(argv, name):
    for index, value in enumerate(argv):
        if value == name and index + 1 < len(argv):
            return argv[index + 1]
        if value.startswith(name + '='):
            return value[len(name) + 1:]
    return None


def root_users(root, proc=Path('/proc')):
    """Read-only Linux inspection, including retained workspace project keys.

    Unknown daemon state fails closed. Other explicitly separate project sessions
    remain running. This is a preflight, not a system-wide interprocess protocol:
    other launchers must not open this root during publication.
    """
    users = []
    for entry in proc.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            argv = (entry / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
            selected = option(argv, '--project-root')
            if selected and Path(selected).resolve() == root:
                users.append(entry.name)
            elif option(argv, '--state-dir') or option(argv, '--discovery-dir'):
                cwd = (entry / 'cwd').resolve(strict=True)
                state = option(argv, '--state-dir')
                discovery = option(argv, '--discovery-dir')
                if not state and discovery:
                    state = str(Path(discovery) / 'state')
                raw_env = (entry / 'environ').read_bytes().decode().rstrip('\0').split('\0')
                process_env = dict(item.split('=', 1) for item in raw_env if '=' in item)
                selected = process_env.get('PT8_PROJECT_ROOT') or process_env.get('GIT_WORK_TREE')
                state = Path(state) if state else None
                held = state is not None and not unlocked(state / 'lifetime.lock')
                discovery_held = discovery is not None and not unlocked(Path(discovery) / 'lifetime.lock')
                if cwd == root or (selected and Path(selected).resolve() == root):
                    users.append(entry.name + ' (root cwd/environment)')
                elif state is None or not state.is_dir() or not (held or discovery_held):
                    users.append(entry.name + ' (uncertain state/discovery ownership)')
                else:
                    records = list(state.glob('workspace-*.sexp'))
                    for file in records:
                        if str(root) in regular(file).decode():
                            users.append(entry.name + ' (root workspace registry)')
                            break
                    else:
                        if not records:
                            users.append(entry.name + ' (uncertain: locked daemon has no workspace records)')
        except FileNotFoundError:
            if (entry / 'cmdline').exists():
                users.append(entry.name + ' (uncertain: process ownership evidence disappeared)')
        except (PermissionError, UnicodeError) as error:
            raise RuntimeError('cannot inspect process ownership: ' + str(entry)) from error
    return sorted(set(users))


def ensure_stopped(root, store, inspect_root=False):
    for file in (store / 'discovery/lifetime.lock', store / 'state/lifetime.lock'):
        if not unlocked(file):
            raise RuntimeError('main daemon owns ' + str(file))
    if inspect_root:
        users = root_users(root)
        if users:
            raise RuntimeError('root checkout may be in use by Workbench PIDs: ' + ', '.join(users))


def paths(root):
    return root / '.dev/workbench-main'


def companion(root, kind):
    return config_location.selected(root, 'hardcaml-workbench-' + kind + '.sexp')


def metadata(store):
    data = regular(store / 'install.json')
    value = json.loads(data)
    if value['schema_version'] != 1 or value['store'] != str(store):
        raise RuntimeError('foreign main installation metadata')
    return value


def verify_simulation(value):
    from checkout_provider import validate_manifest
    manifest = json.loads(regular(Path(value['simulation_manifest'])))
    if manifest['project_root'] != value['project_root'] or manifest['asic_generation'] != value['asic_generation']:
        raise RuntimeError('simulation manifest root/dependency selection changed; explicitly rebuild')
    validate_manifest(manifest, 'discover')


def verify_install(root, store, published=False):
    if (store / 'publication-pending.json').exists():
        raise RuntimeError('interrupted publication: inspect publication-pending.json and exact backups before recovery')
    value = metadata(store)
    if value['project_root'] != str(root):
        raise RuntimeError('main installation belongs to another checkout')
    for kind, app in value['apps'].items():
        if sha(regular(Path(app['path']))) != app['sha256']:
            raise RuntimeError('installed app changed: ' + kind)
    for kind, digest in value['config_sha256'].items():
        if sha(regular(Path(value['selection']) / 'config' / companion(root, kind).name)) != digest:
            raise RuntimeError('prepared companion changed: ' + kind)
        if published and sha(regular(companion(root, kind))) != digest:
            raise RuntimeError('root companion differs; explicitly publish prepared configuration: ' + kind)
    return value


def simulation_config(root, path):
    data = regular(path)
    fields = record(parse(data.decode()), ('schema_version', 'provider_executable', 'provider_args',
                                          'discovery_timeout_seconds', 'run_timeout_seconds'))
    if fields['schema_version'] != '1' or not Path(fields['provider_executable']).is_absolute():
        raise RuntimeError('invalid simulation configuration')
    args = fields['provider_args']
    if not isinstance(args, list) or str(root / 'integration/workbench/checkout_provider.py') not in args:
        raise RuntimeError('simulation config must select the actual checkout_provider.py')
    regular(root / 'integration/workbench/checkout_provider.py')
    if not os.access(fields['provider_executable'], os.X_OK):
        raise RuntimeError('simulation executable is not available')
    manifest = option(args, '--manifest')
    if not manifest or not Path(manifest).is_absolute():
        raise RuntimeError('simulation provider requires an absolute --manifest')
    if json.loads(regular(Path(manifest)))['project_root'] != str(root):
        raise RuntimeError('simulation manifest must use the actual checkout root')
    for name, limit in (('discovery_timeout_seconds', 60), ('run_timeout_seconds', 86400)):
        if not str(fields[name]).isdecimal() or not 1 <= int(fields[name]) <= limit:
            raise RuntimeError('invalid simulation timeout: ' + name)
    return data, manifest


def bounded_build(argv, *, cwd, env):
    """Bound helper build output and deadline; reap the owned build group on failure."""
    with subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, start_new_session=True) as child:
        output = bytearray()
        deadline = time.monotonic() + 1800
        try:
            with selectors.DefaultSelector() as poll:
                poll.register(child.stdout, selectors.EVENT_READ)
                while poll.get_map():
                    if time.monotonic() >= deadline:
                        raise RuntimeError('source build exceeded 1800 seconds')
                    for key, _ in poll.select(.1):
                        block = os.read(key.fd, 65536)
                        if not block:
                            poll.unregister(key.fileobj)
                            continue
                        output.extend(block)
                        if len(output) > 8 * 1024 * 1024:
                            raise RuntimeError('source build output exceeded 8 MiB')
            code = child.wait(timeout=max(.001, deadline - time.monotonic()))
            if code:
                raise RuntimeError('source build failed:\n' + output[-16384:].decode('utf-8', 'replace'))
            return subprocess.CompletedProcess(argv, code)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


def build(root, store, asic, sdk):
    from checkout_setup import prepare_simulation
    env = environment(root, store, asic, sdk)
    (store / 'tmp').mkdir(parents=True, exist_ok=True)
    # Persistent shared locks: no dependency on historical /tmp acceptance locks.
    with lock(root.parent / '.workbench-example-build.lock'):
        tools = verify_tools(root, env)
        json_write(store / 'tools.json', tools)
        return prepare_simulation(project_root=root, build_dir=root / '_build',
            asic_generation=asic, run=bounded_build, environment=env,
            dune=tools['paths']['dune'], python=tools['paths']['python'],
            model_root=root / '_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog',
            simulation_dir=store / 'simulation')


def prepare(args, root, store):
    ensure_stopped(root, store)
    prior = verify_install(root, store) if (store / 'install.json').exists() else None
    if prior and not args.update:
        verify_simulation(prior)
        return prior
    asic = args.asic_generation.resolve(strict=True)
    sdk = args.sdk_prefix.resolve(strict=True)
    for path in (asic / 'bin/hardcaml-asic-flow', asic / 'receipt.json', sdk / 'lib'):
        if not path.exists():
            raise RuntimeError('missing installed dependency: ' + str(path))
    wb = args.wb_build_root.resolve(strict=True)
    source_apps = {kind: wb / 'default' / directory / 'main.exe'
                   for kind, directory in (('daemon', 'daemon'), ('client', 'terminal'))}
    app_bytes = {kind: regular(path) for kind, path in source_apps.items()}
    for kind, path in source_apps.items():
        if not os.access(path, os.X_OK):
            raise RuntimeError('app is not executable: ' + str(path))
        expected = getattr(args, 'expected_' + kind + '_sha256')
        if expected and sha(app_bytes[kind]) != expected:
            raise RuntimeError('unexpected prebuilt app hash: ' + kind)
    store.mkdir(parents=True, exist_ok=True)
    (store / 'tmp').mkdir(exist_ok=True)
    if args.build:
        build(root, store, asic, sdk)
    sim_path = args.simulation_config
    if sim_path is None:
        manifest_path = store / 'simulation/manifest.json'
        sim_manifest = json.loads(regular(manifest_path))
        command = sim_manifest['provider_command']
        sim_path = store / 'simulation/configuration.sexp'
        data = (sexp([('schema_version', 1), ('provider_executable', command[0]),
                      ('provider_args', command[1:]), ('discovery_timeout_seconds', 30),
                      ('run_timeout_seconds', 600)]) + '\n').encode()
        existing = regular(sim_path, missing=True)
        if existing is not None and existing != data:
            raise RuntimeError('unknown simulation handoff edit; use explicit --simulation-config')
        write(sim_path, data)
    sim, manifest = simulation_config(root, sim_path.absolute())
    sim_manifest = json.loads(regular(Path(manifest)))
    if sim_manifest.get('asic_generation', str(asic)) != str(asic):
        raise RuntimeError('simulation manifest selects a different ASIC generation; explicitly rebuild')
    for kind, path in source_apps.items():
        if regular(path) != app_bytes[kind]:
            raise RuntimeError('prebuilt app changed during preparation; retry: ' + kind)
    for target in TARGETS:
        if not os.access(root / '_build/default' / target, os.X_OK):
            raise RuntimeError('missing current target; explicitly prepare --build: ' + target)
    configs = dict(simulation=sim)
    configs['preparation'] = (sexp([('schema_version', 1), ('build_target', TARGETS[0]),
        ('results_root', str(root / '_flow_results/workbench/preparation')), ('timeout_seconds', 600)]) + '\n').encode()
    tools = root / '_flow_tools'
    configs['asic'] = (sexp([('schema_version', 1),
        ('project_executable', str(root / '_build/default' / TARGETS[0])),
        ('provider_executable', str(asic / 'bin/hardcaml-asic-flow')),
        ('results_root', str(root / '_flow_results/workbench/asic')), ('toolchain', str(tools)),
        ('python', [str(tools / '.venv/bin/python')]), ('support_tools', [str(tools / 'tt')]),
        ('pdk_root', [str(tools / 'pdk')]), ('stage_timeout_seconds', [3600])]) + '\n').encode()
    # Immutable app/config selection, committed by one install.json replacement.
    selection = store / 'installs' / uuid.uuid4().hex
    selection.mkdir(parents=True)
    apps = {}
    for kind, data in app_bytes.items():
        dest = selection / 'apps' / (kind + '.exe')
        write(dest, data)
        dest.chmod(0o555)
        apps[kind] = dict(path=str(dest), sha256=sha(data), source=str(source_apps[kind]))
    for kind, data in configs.items():
        write(selection / 'config' / companion(root, kind).name, data)
    # Baseline records exact existing root bytes, never an implicit adoption.
    baseline = prior['baseline_sha256'] if prior else {}
    for kind in KINDS:
        old = regular(companion(root, kind), missing=True)
        if prior is None:
            baseline[kind] = None if old is None else sha(old)
            if old is not None:
                write(selection / 'baseline' / companion(root, kind).name, old)
    value = dict(schema_version=1, project_root=str(root), store=str(store),
                 asic_generation=str(asic), sdk_prefix=str(sdk), apps=apps,
                 selection=str(selection), simulation_manifest=manifest,
                 baseline_sha256=baseline, config_sha256={k: sha(v) for k, v in configs.items()})
    value['tools'] = selected_tools(environment(root, store, asic, sdk))
    verify_simulation(value)
    json_write(store / 'install.json', value)
    return value


def publish(root, store, dry_run=False):
    ensure_stopped(root, store, inspect_root=True)
    value = verify_install(root, store)
    verify_simulation(value)
    owned_path = store / 'published.json'
    owned = json.loads(regular(owned_path)) if owned_path.exists() else None
    expected = owned['config_sha256'] if owned else value['baseline_sha256']
    targets = {kind: config_location.destinations(root, 'hardcaml-workbench-' + kind + '.sexp')
               for kind in KINDS}
    previous = {kind: regular(targets[kind][0], missing=True) for kind in KINDS}
    for kind, data in previous.items():
        if (None if data is None else sha(data)) != expected[kind]:
            raise RuntimeError('unknown root companion edit; refusing overwrite: ' + kind)
    if dry_run:
        return dict(ready=True, published=False, project_root=str(root),
                    config_sha256=value['config_sha256'], previous_sha256=expected,
                    config_paths={kind: list(map(str, paths)) for kind, paths in targets.items()})
    receipt = store / 'publications' / uuid.uuid4().hex
    receipt.mkdir(parents=True)
    for kind, data in previous.items():
        if data is not None:
            write(receipt / companion(root, kind).name, data)
    pending = dict(previous_sha256=expected, config_sha256=value['config_sha256'], backup=str(receipt),
                   config_paths={kind: list(map(str, paths)) for kind, paths in targets.items()})
    json_write(store / 'publication-pending.json', pending)
    changed = []
    try:
        ensure_stopped(root, store, inspect_root=True)
        for kind in KINDS:
            if config_location.destinations(root, 'hardcaml-workbench-' + kind + '.sexp') != targets[kind]:
                raise RuntimeError('companion locations changed during publication: ' + kind)
            if any(regular(path, missing=True) != previous[kind] for path in targets[kind]):
                raise RuntimeError('companion changed during publication: ' + kind)
            data = regular(Path(value['selection']) / 'config' / targets[kind][0].name)
            for path in targets[kind]:
                write(path, data)
                changed.append((kind, path))
        json_write(owned_path, pending)
    except BaseException:
        # Restore only bytes still owned by this transaction. Unknown concurrent
        # edits leave the journal for explicit recovery instead of being erased.
        for kind, path in reversed(changed):
            if sha(regular(path)) != value['config_sha256'][kind]:
                raise RuntimeError('concurrent edit; publication journal retained')
            if previous[kind] is None:
                path.unlink()
            else:
                write(path, previous[kind])
        (store / 'publication-pending.json').unlink()
        raise
    (store / 'publication-pending.json').unlink()
    return pending


def endpoint(store):
    if unlocked(store / 'discovery/lifetime.lock'):
        raise RuntimeError('main daemon is not running; explicitly run daemon')
    fields = record(parse(regular(store / 'discovery/daemon.sexp').decode()), ('endpoint', 'instance_id', 'pid'))
    url = urlparse(fields['endpoint'])
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.path:
        raise RuntimeError('invalid loopback discovery endpoint')
    os.kill(int(fields['pid']), 0)
    return fields['endpoint']


def run_owned(argv, root, env):
    # Keep the session lock in the supervisor, not in arbitrary daemon children.
    child = subprocess.Popen(argv, cwd=root, env=env)
    previous = {}
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, lambda sig, frame: child.send_signal(sig) if child.poll() is None else None)
        return child.wait()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if child.poll() is None:
            child.terminate()
            child.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare', help='stage installation/configuration; never publish or start')
    prep.add_argument('--build', action='store_true', help='explicitly compile current source at -j2')
    prep.add_argument('--update', action='store_true', help='explicitly replace the selected apps/configuration')
    prep.add_argument('--asic-generation', type=Path)
    prep.add_argument('--sdk-prefix', type=Path)
    prep.add_argument('--wb-build-root', type=Path)
    prep.add_argument('--simulation-config', type=Path)
    for kind in ('daemon', 'client'):
        prep.add_argument('--expected-' + kind + '-sha256')
    publication = commands.add_parser('publish', help='explicit guarded root-companion publication')
    publication.add_argument('--dry-run', action='store_true', help='check readiness without changing companions')
    commands.add_parser('build', help='explicit current-source build at -j2; no app/config publication')
    commands.add_parser('daemon', help='foreground production daemon on an available loopback port')
    commands.add_parser('client', help='connect only; never start a daemon')
    commands.add_parser('status', help='read installation/ownership without starting work')
    args = parser.parse_args(argv)
    root = args.root.resolve(strict=True)
    regular(root / 'dune-project')
    store = paths(root)
    if args.command == 'status':
        if not (store / 'install.json').exists():
            print(json.dumps(dict(prepared=False, project_root=str(root), store=str(store))))
            return 0
        value = verify_install(root, store)
        try:
            verify_simulation(value)
            value['simulation_ready'] = True
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            value['simulation_ready'] = False
            value['simulation_error'] = str(error)
        value['daemon_running'] = not unlocked(store / 'discovery/lifetime.lock')
        value['root_companions_match'] = all(regular(companion(root, k), missing=True) is not None and
            sha(regular(companion(root, k))) == value['config_sha256'][k] for k in KINDS)
        print(json.dumps(value, indent=2))
        return 0
    if args.command == 'client':
        value = verify_install(root, store, published=True)
        url = endpoint(store)
        env = environment(root, store, Path(value['asic_generation']), Path(value['sdk_prefix']))
        return subprocess.call([value['apps']['client']['path'], '--connect', url,
                                '--project-root', str(root), '--environment', 'inherited'], cwd=root, env=env)
    with lock(store / 'session.lock'):
        if args.command == 'prepare':
            args.asic_generation = args.asic_generation or root / '.dev/asic-synthesis-envelope-v1/generations' / GENERATION
            args.sdk_prefix = args.sdk_prefix or root / '.dev/workbench-provider-sdk'
            args.wb_build_root = args.wb_build_root or root.parent / 'hardcaml_workbench/_build_pt8_workbench'
            if args.build and (store / 'install.json').exists() and not args.update:
                raise RuntimeError('use build, or prepare --update --build for an existing installation')
            value = prepare(args, root, store)
        elif args.command == 'publish':
            value = publish(root, store, dry_run=args.dry_run)
        else:
            value = verify_install(root, store, published=args.command == 'daemon')
            ensure_stopped(root, store)
            if args.command == 'build':
                build(root, store, Path(value['asic_generation']), Path(value['sdk_prefix']))
            else:
                verify_simulation(value)
                env = environment(root, store, Path(value['asic_generation']), Path(value['sdk_prefix']))
                verify_tools(root, env)
                # The normal daemon ensures state itself, but its explicit
                # discovery-dir must already exist before acquiring its lock.
                for name in ('state', 'discovery', 'tmp'):
                    directory = store / name
                    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                    if directory.resolve() != directory or not directory.is_dir():
                        raise RuntimeError('runtime directory must be independent: ' + str(directory))
                    directory.chmod(0o700)
                return run_owned([value['apps']['daemon']['path'], '--port', '0',
                    '--state-dir', str(store / 'state'), '--discovery-dir', str(store / 'discovery')], root, env)
        print(json.dumps(value, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print('workbench-main: ' + str(error), file=sys.stderr)
        sys.exit(2)
