#!/usr/bin/env python3
"""Prepare and open one stable editable Workbench development project."""
import argparse
import contextlib
import ctypes
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/workbench'))
from wire import parse, record, sexp
from workbench_provider import (ACCEPTANCE_FILES, SOURCE_DIRS, SOURCE_FILES, SOURCE_LAYOUT, SUITE_PATHS, SUITES,
                                environment, inventory, sha, source_drift)
from workbench_git import clean_environment

CONFIGS = ('simulation', 'asic', 'preparation')
TARGETS = ('ip/controlled_fifo/verif/simulation/test_provider.exe', 'ip/controlled_fifo/verif/simulation/fifo_sim.exe',
           'tooling_acceptance/workloads/workload_emit.exe', 'tooling_acceptance/workloads/workload_public.exe',
           'asics/fifo_demo/cli/project.exe')
IMPORT_GROUPS = {name: (name,) for name in ('ip/controlled_fifo/verif/cyclesim', 'asics/fifo_demo/verif',
    'tooling_acceptance/timing', 'bootstrap.sh')}
OWNED_SUPPORT = ('integration/workbench/workbench_provider.py', 'scripts/workbench_dev.py',
                 'scripts/test_workbench_dev.py', 'scripts/test_pt8_waveforms.py',
                  'scripts/workbench_git.py')


def require_source_layout(project, manifest=None):
    """Moves cannot be reconciled by the additive missing-source importer."""
    project = Path(project)
    legacy = ('lib', 'asic', 'bin', 'memory', 'variants', 'workloads', 'simulation',
              'test_support', 'test', 'asic_test', 'timing', 'named_timing', 'physical_timing')
    if ((manifest is not None and manifest.get('source_layout') != SOURCE_LAYOUT)
            or any((project / name).exists() or (project / name).is_symlink() for name in legacy)):
        raise RuntimeError('legacy source layout: existing copies/history remain unchanged; explicitly create '
                           'a new --store for the migrated ownership layout. '
                           '--refresh and --import-missing-source cannot migrate moved sources')


def rename_new(source, destination):
    """Linux atomic no-replace, including an existing EMPTY destination directory."""
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(destination))


def source_owner(prior, root):
    if prior:
        return Path(prior['source_owner_root']) if 'source_owner_root' in prior else Path(prior['inputs']['git_dir']).parent
    return root


def migrate_sources(args, store, prior, receipt):
    """Explicit additions/support updates; no merge/recopy of existing authored dirs."""
    require_source_layout(store / 'project', prior)
    owner = source_owner(prior, args.root).resolve(strict=True)
    project = store / 'project'
    planned = []
    if args.import_missing_source:
        for name, names in IMPORT_GROUPS.items():
            path = project / name
            if not path.exists() and not path.is_symlink():
                planned.append(dict(path=name, names=names, previous=None))
    if args.update_owned_support:
        for name in OWNED_SUPPORT:
            path, source = project / name, owner / name
            if path.parent.resolve() != path.parent:
                raise RuntimeError('owned support parent contains a symlink; refusing overwrite: ' + str(path))
            latest = sha(source)
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise RuntimeError('refusing edited/nonregular owned support: ' + str(path))
            previous = sha(path) if path.exists() else None
            if previous == latest:
                continue
            baseline = prior['source_files'].get(name) if prior else None
            if previous is not None and previous != baseline:
                raise RuntimeError('owned support differs from recorded baseline; refusing overwrite: ' + str(path))
            planned.append(dict(path=name, names=(name,), previous=previous))
    staged = receipt / 'source-stage'
    staged.mkdir()
    # Stage all entries and recheck the source/copy before publishing any entry.
    for entry in planned:
        expected = inventory(owner, entry['names'])
        for name in expected:
            destination = staged / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(owner / name, destination)
            destination.chmod((owner / name).stat().st_mode & 0o777)
            with destination.open('rb') as stream:
                os.fsync(stream.fileno())
        if inventory(owner, entry['names']) != expected or inventory(staged, entry['names']) != expected:
            raise RuntimeError('owner source changed during missing-source staging; retry explicit migration')
        entry['files'] = expected
    for directory in sorted((p for p in staged.rglob('*') if p.is_dir()), reverse=True):
        sync_dir(directory)
    sync_dir(staged)
    write(receipt / 'source-migration-intent.json', dict(owner_root=str(owner), entries=planned,
                                                       import_missing=args.import_missing_source,
                                                       update_owned_support=args.update_owned_support))
    sync_dir(receipt)
    installed = []
    try:
        for entry in planned:
            name = entry['path']
            destination = project / name
            if entry['previous'] is None:
                # No merging, even if another editor just created an empty dir.
                rename_new(staged / name, destination)
            else:
                if destination.is_symlink() or sha(destination) != entry['previous']:
                    raise RuntimeError('owned support changed during staging; refusing overwrite: ' + name)
                # Move old bytes aside without overwriting any path. Recheck them
                # AFTER the move, then publish only into a still-absent path. Any
                # racing editor's replacement is left untouched; old bytes survive.
                backup = receipt / 'source-backup' / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                rename_new(destination, backup)
                try:
                    if sha(backup) != entry['previous']:
                        raise RuntimeError('owned support raced migration; original retained at ' + str(backup))
                    rename_new(staged / name, destination)
                except BaseException:
                    if not destination.exists() and not destination.is_symlink():
                        rename_new(backup, destination)
                    raise
                sync_dir(backup.parent)
            sync_dir(destination.parent)
            installed.append(name)
    finally:
        # Added sources remain intentionally, even if capture/build later fails.
        # The durable intent also records an interrupted rename before this list.
        write(receipt / 'source-migration-result.json', dict(owner_root=str(owner), entries=planned,
                                                           installed=installed, retained_on_build_failure=True))
        sync_dir(receipt)
    return dict(receipt=str(receipt / 'source-migration-result.json'),
                sha256=sha(receipt / 'source-migration-result.json'), installed=installed)


def write(path, value):
    path = Path(path)
    data = (json.dumps(value, indent=2) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def config_name(kind):
    return 'hardcaml-workbench-' + kind + '.sexp'


def unsettled(store):
    if (store / 'publication.json').exists():
        raise RuntimeError('interrupted configuration publication; launch/verification blocked. '
                           'Stop the development daemon, then run scripts/workbench_dev.py '
                           'prepare --refresh (with the same --store) to verify and roll back before retrying')


def config_hashes(manifest):
    # The old symlink generation recorded these same bytes in captured_files.
    return manifest.get('config_files', {config_name(kind): manifest['captured_files']['config/' + config_name(kind)]
                                        for kind in CONFIGS})


def config_state(path):
    if path.is_symlink():
        return dict(type='symlink', target=os.readlink(path), sha256=sha(path))
    if path.is_file():
        return dict(type='regular', sha256=sha(path))
    if not path.exists():
        return dict(type='missing')
    raise RuntimeError('nonregular private configuration: ' + str(path))


def replace_regular(path, data):
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex + '.pending')
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o444)
    os.replace(temporary, path)
    sync_dir(path.parent)


def select_generation(store, generation):
    selected = store / 'selected'
    if generation is None:
        selected.unlink(missing_ok=True)
    else:
        generation = Path(generation)
        if generation.parent != store / 'generations':
            raise RuntimeError('publication generation is outside this store')
        temporary = store / ('selection-' + uuid.uuid4().hex)
        temporary.symlink_to('generations/' + generation.name)
        os.replace(temporary, selected)
    sync_dir(store)


def recover_publication(store):
    """Called only under exclusive setup + both lifetime locks, on explicit refresh."""
    journal_path = store / 'publication.json'
    if not journal_path.exists():
        return
    journal = json.loads(journal_path.read_text())
    generation = Path(journal['new_generation'])
    if generation.parent != store / 'generations' or journal['store'] != str(store):
        raise RuntimeError('unowned publication journal; inspect publication.json without editing configs')
    receipt = store / 'receipts' / generation.name
    current = (store / 'selected').resolve() if (store / 'selected').exists() else None
    allowed = {generation, Path(journal['old_generation']) if journal['old_generation'] else None}
    if current not in allowed:
        raise RuntimeError('selection edited during interrupted publication; refusing automatic overwrite')
    # Validate ALL files and rollback bytes before replacing ANYTHING. Unknown
    # edits leave the journal intact for manual reconciliation, never overwritten.
    for kind in CONFIGS:
        name = config_name(kind)
        old = journal['old_configs'][name]
        new = dict(type='regular', sha256=journal['new_configs'][name])
        if config_state(store / 'project' / name) not in (old, new):
            raise RuntimeError('private configuration edited during interrupted publication; refusing overwrite: ' + name)
        if old['type'] != 'missing' and sha(receipt / 'rollback' / name) != old['sha256']:
            raise RuntimeError('rollback config checksum mismatch: ' + name)
    # First restore the old selection so restored legacy links name old bytes.
    select_generation(store, journal['old_generation'])
    for kind in CONFIGS:
        name = config_name(kind)
        path = store / 'project' / name
        old = journal['old_configs'][name]
        if config_state(path) == old:
            continue
        if old['type'] == 'missing':
            path.unlink(missing_ok=True)
        elif old['type'] == 'symlink':
            temporary = path.with_name('.rollback-' + uuid.uuid4().hex)
            temporary.symlink_to(old['target'])
            os.replace(temporary, path)
        else:
            replace_regular(path, (receipt / 'rollback' / name).read_bytes())
    sync_dir(store / 'project')
    os.replace(journal_path, receipt / 'rolled-back-publication.json')
    sync_dir(receipt)
    sync_dir(store)


def publish(store, prior, manifest, receipt):
    """Regular configs + selection commit; readers are fenced by setup/lifetime locks."""
    rollback = receipt / 'rollback'
    rollback.mkdir()
    old_configs = {}
    for kind in CONFIGS:
        name = config_name(kind)
        path = store / 'project' / name
        state = config_state(path)
        if prior is None and state['type'] != 'missing':
            raise RuntimeError('refusing unowned initial configuration: ' + str(path))
        old_configs[name] = state
        if state['type'] != 'missing':
            with (rollback / name).open('xb') as stream:
                stream.write(path.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
    sync_dir(rollback)
    journal = dict(schema_version=1, store=str(store), old_generation=prior['generation'] if prior else None,
                   new_generation=manifest['generation'], old_configs=old_configs, new_configs=manifest['config_files'])
    # Publish a complete, fsynced journal atomically: a crash while writing JSON
    # must not leave an unreadable recovery marker before any config changed.
    intent = receipt / 'publication-intent.json'
    write(intent, journal)
    sync_dir(receipt)
    os.link(intent, store / 'publication.json')
    sync_dir(store)
    try:
        for kind in CONFIGS:
            name = config_name(kind)
            path = store / 'project' / name
            if config_state(path) != old_configs[name]:
                raise RuntimeError('private configuration changed during publication: ' + name)
            data = (Path(manifest['generation']) / 'config' / name).read_bytes()
            replace_regular(path, data)
        select_generation(store, manifest['generation'])
        verify(manifest, allow_pending=True)
        os.replace(store / 'publication.json', receipt / 'committed-publication.json')
        sync_dir(receipt)
        sync_dir(store)
    except Exception:
        # BaseException/process death deliberately leaves the durable journal:
        # every ordinary entry point blocks until explicit refresh recovery.
        if (store / 'publication.json').exists():
            recover_publication(store)
        raise


@contextlib.contextmanager
def locked(path, *, nonblocking=False, inheritable=False, shared=False):
    with Path(path).open('a+b') as stream:
        try:
            fcntl.flock(stream, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | (fcntl.LOCK_NB if nonblocking else 0))
        except BlockingIOError:
            raise RuntimeError('lock held; stop the development daemon explicitly before refresh/start: ' + str(path)) from None
        if inheritable:
            os.set_inheritable(stream.fileno(), True)
        yield stream


def tree_hashes(root):
    root = Path(root)
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def verify_hashes(root, expected):
    for name, digest in expected.items():
        if sha(Path(root) / name) != digest:
            raise RuntimeError('capture integrity mismatch: ' + str(Path(root) / name))


def copy_checked(source, destination):
    before = tree_hashes(source) if Path(source).is_dir() else sha(source)
    if Path(source).is_dir():
        shutil.copytree(source, destination)
        copied = tree_hashes(destination)
        after = tree_hashes(source)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied, after = sha(destination), sha(source)
    if before != copied or before != after:
        raise RuntimeError('input changed during capture; retry prepare --refresh: ' + str(source))


def copy_sources(source, destination):
    before = inventory(source, SOURCE_FILES + SOURCE_DIRS)
    destination.mkdir()
    for name in before:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        target.chmod((source / name).stat().st_mode & 0o777)
    if inventory(source, SOURCE_FILES + SOURCE_DIRS) != before or inventory(destination, SOURCE_FILES + SOURCE_DIRS) != before:
        raise RuntimeError('source changed during independent copy; partial capture retained')
    return before


def selected_manifest(store):
    require_source_layout(store / 'project')
    unsettled(store)
    path = store / 'manifest.json'
    if not path.exists():
        return None
    if not path.is_symlink() or os.readlink(path) != 'selected/manifest.json':
        raise RuntimeError('edited/unowned store manifest; refusing automatic adoption')
    value = json.loads(path.read_text())
    if value['schema_version'] != 1 or value['store'] != str(store) or value['project_root'] != str(store / 'project'):
        raise RuntimeError('manifest does not own this fixed store/project')
    if Path(value['generation']).resolve() != (store / 'selected').resolve():
        raise RuntimeError('manifest selection mismatch')
    require_source_layout(store / 'project', value)
    return value


def verify(manifest, *, configs=True, allow_legacy=False, allow_pending=False):
    require_source_layout(manifest['project_root'], manifest)
    verify_hashes(manifest['generation'], manifest['captured_files'])
    verify_hashes(manifest['inputs']['asic_generation'], manifest['asic_files'])
    if 'git_context' in manifest and sha(manifest['git_context']['real_git']) != manifest['git_context']['real_git_sha256']:
        raise RuntimeError('pinned real Git executable changed; explicit stopped-daemon refresh required')
    if sha(Path(manifest['inputs']['asic_generation']) / 'receipt.json') != manifest['asic_receipt_sha256']:
        raise RuntimeError('ASIC receipt changed')
    store = Path(manifest['store'])
    if not allow_pending:
        unsettled(store)
    if not configs:
        return
    if (store / 'selected').resolve() != Path(manifest['generation']):
        raise RuntimeError('configuration manifest is not the selected generation')
    project = store / 'project'
    if project.resolve() != project:
        raise RuntimeError('private project path contains a symlink')
    for kind in CONFIGS:
        config = project / config_name(kind)
        expected = store / 'selected/config' / config.name
        if config.is_symlink():
            if not allow_legacy or 'config_files' in manifest:
                raise RuntimeError('legacy symlink configuration requires explicit prepare --refresh: ' + str(config))
            if os.readlink(config) != str(expected):
                raise RuntimeError('private configuration link edited; refusing overwrite: ' + str(config))
        elif not config.is_file():
            raise RuntimeError('private configuration edited; refusing overwrite: ' + str(config))
        if sha(config) != config_hashes(manifest)[config.name]:
            raise RuntimeError('private configuration hash changed; refusing overwrite: ' + str(config))


def show(manifest, *, stream=sys.stdout):
    drift = {}
    for suite in SUITES:
        try:
            drift[suite] = source_drift(manifest, suite)
        except (ValueError, OSError) as error:
            drift[suite] = [str(error)]
    result = dict(prepared=True, editable_project=manifest['project_root'],
                  generation=manifest['generation'], paths=manifest['paths'],
                  environment=manifest['environment'], provider_command=manifest['provider_command'],
                  provider_commands=manifest['provider_commands'], apps=manifest['apps'], source_drift=drift,
                  source_dirs=list(SOURCE_DIRS), source_files=list(SOURCE_FILES),
                  missing_source=[name for name in SOURCE_FILES + SOURCE_DIRS
                                  if not (Path(manifest['project_root']) / name).exists()],
                  git_context_diagnostic=git_context_diagnostic(manifest))
    print(json.dumps(result, indent=2), file=stream, flush=True)


def default_inputs(root):
    return dict(asic_generation=str(root / '.dev/asic-pt8-workbench/session-final-review-01/asic/generations/ee3af8de9f83418b9afed9c67e473e3c'),
                sdk_prefix=str(root / '.dev/workbench-provider-sdk'),
                wb_build_root=str(root.parent / 'hardcaml_workbench/_build_pt8_workbench'),
                dune=shutil.which('dune'), python=str(Path(sys.executable).resolve()),
                toolchain=str(root / '_flow_tools'), git_dir=str(root / '.git'),
                git=shutil.which('git', path=clean_environment(os.environ).get('PATH')))


def git_context_diagnostic(manifest):
    selectors = [key for key in manifest['environment'] if key.startswith('GIT_') and key not in
                 ('GIT_OPTIONAL_LOCKS', 'GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL')]
    if selectors or 'git_context' not in manifest:
        return ('Legacy unsafe global Git context: ' + ', '.join(selectors) +
                '. History remains retained. Do not use this capture for collateral validation; '
                'after the owner explicitly stops its daemon, run prepare --refresh --update-owned-support '
                'from the owner checkout with the same --store. No automatic refresh or restart.')
    return None


def capture_apps_only(args, store, prior, receipt):
    """New immutable app pair, retaining exact provider/config/history scope.

    Provider commands and environment intentionally keep naming the retained old
    generation. This is an application recapture, not a dependency/source refresh.
    """
    if prior is None:
        raise RuntimeError('--apps-only requires an existing prepared generation')
    if any(getattr(args, name, None) is not None for name in ('asic_generation', 'sdk_prefix', 'dune', 'git')):
        raise RuntimeError('--apps-only cannot change dependency, SDK, Dune or Git inputs')
    requested = getattr(args, 'synthesis_task_limit', None)
    if requested is not None and prior['environment'].get('HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT') != str(requested):
        raise RuntimeError('--apps-only cannot change synthesis task-limit opt-in')
    if any(getattr(args, 'expected_' + kind + '_sha256', None) is None for kind in ('daemon', 'client')):
        raise RuntimeError('--apps-only requires both explicit expected app hashes')
    if inventory(store / 'project', SOURCE_FILES + SOURCE_DIRS) != prior['source_files']:
        raise RuntimeError('--apps-only refuses source drift')
    if inventory(store / 'project', ('.',)) != dict(prior['source_files'], **config_hashes(prior)):
        raise RuntimeError('--apps-only refuses additional authored source/configuration')
    verify(prior)
    generation = store / 'generations' / receipt.name
    generation.mkdir()
    old = Path(prior['generation'])
    replaced = {'apps/daemon.exe', 'apps/client.exe', 'setup/workbench_dev.py'}
    for name in prior['captured_files']:
        if name not in replaced:
            copy_checked(old / name, generation / name)
            (generation / name).chmod((old / name).stat().st_mode & 0o777)
    copy_checked(Path(__file__), generation / 'setup/workbench_dev.py')
    inputs = dict(prior['inputs'])
    if args.wb_build_root is not None:
        inputs['wb_build_root'] = str(args.wb_build_root.resolve(strict=True))
    with locked('/tmp/opencode/workbench-pt8-build.lock'):
        originals = {kind: Path(inputs['wb_build_root']) / relative for kind, relative in
                     (('daemon', 'default/daemon/main.exe'), ('client', 'default/terminal/main.exe'))}
        before = {kind: sha(path) for kind, path in originals.items()}
        for kind, path in originals.items():
            if before[kind] != getattr(args, 'expected_' + kind + '_sha256'):
                raise RuntimeError('reviewed app hash mismatch: ' + kind)
            copy_checked(path, generation / 'apps' / (kind + '.exe'))
        if before != {kind: sha(path) for kind, path in originals.items()}:
            raise RuntimeError('app pair changed during app-only capture')
    if inventory(store / 'project', SOURCE_FILES + SOURCE_DIRS) != prior['source_files']:
        raise RuntimeError('source changed during app-only capture')
    if inventory(store / 'project', ('.',)) != dict(prior['source_files'], **config_hashes(prior)):
        raise RuntimeError('source/configuration closure changed during app-only capture')
    verify(prior)
    manifest = json.loads(json.dumps(prior))
    manifest.update(generation_id=receipt.name, generation=str(generation), inputs=inputs,
        apps={kind: dict(path=str(generation / 'apps' / (kind + '.exe')), sha256=before[kind])
              for kind in ('daemon', 'client')},
        setup=dict(source=str(Path(__file__).resolve()), captured=str(generation / 'setup/workbench_dev.py'),
                   sha256=sha(generation / 'setup/workbench_dev.py')),
        app_recapture=dict(previous_generation=str(old), previous_manifest_sha256=sha(old / 'manifest.json'),
                           provider_config_environment_preserved=True))
    for path in generation.rglob('*'):
        if path.is_file():
            path.chmod(0o555 if path.stat().st_mode & 0o111 or path.suffix == '.exe' else 0o444)
    manifest['captured_files'] = tree_hashes(generation)
    write(generation / 'manifest.json', manifest)
    (generation / 'manifest.json').chmod(0o444)
    for path in generation.rglob('*'):
        if path.is_file():
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
    for directory in sorted((p for p in generation.rglob('*') if p.is_dir()), reverse=True):
        sync_dir(directory)
        directory.chmod(0o555)
    sync_dir(generation)
    generation.chmod(0o555)
    sync_dir(generation.parent)
    return manifest


def synthesis_task_limit(args, prior):
    """A normal refresh retains its resource opt-in; absence never disables it."""
    previous = (prior or {}).get('environment', {}).get('HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT')
    if previous not in (None, '6'):
        raise RuntimeError('invalid retained synthesis task-limit opt-in; explicit reconciliation required')
    requested = getattr(args, 'synthesis_task_limit', None)
    if requested not in (None, 6):
        raise RuntimeError('synthesis task-limit must be absent or 6')
    return 6 if requested == 6 or previous == '6' else None


def capture(args, store, prior, receipt, migration=None):
    task_limit = synthesis_task_limit(args, prior)
    inputs = dict(prior['inputs']) if prior else default_inputs(args.root)
    inputs.setdefault('git_dir', str(args.root / '.git'))
    inputs.setdefault('git', shutil.which('git', path=clean_environment(os.environ).get('PATH')))
    if prior:
        # An ordinary source/app refresh is not an implicit SDK upgrade. New SDK
        # input is used only with an explicit --sdk-prefix override.
        inputs['sdk_prefix'] = str(Path(prior['generation']) / 'sdk')
    for name in ('asic_generation', 'sdk_prefix', 'wb_build_root', 'dune', 'git'):
        if getattr(args, name) is not None:
            inputs[name] = str(getattr(args, name))
    for name, value in inputs.items():
        if value is None:
            raise RuntimeError('missing activated tool: ' + name)
        original = Path(value).absolute()
        # Never accept mutable current pointers as the ASIC identity.
        if name == 'asic_generation' and original.resolve(strict=True) != original:
            raise RuntimeError('ASIC generation must be an exact immutable path, not a symlink')
        inputs[name] = str(original.resolve(strict=True))
    generation = store / 'generations' / receipt.name
    generation.mkdir()
    source = generation / 'source'
    sources = copy_sources(store / 'project', source)
    if not (source / 'scripts/workbench_git.py').is_file():
        raise RuntimeError('missing scoped Git helper; explicit prepare --refresh --update-owned-support is required')
    sdk = generation / 'sdk'
    copy_checked(Path(inputs['sdk_prefix']) / 'lib', sdk / 'lib')
    asic = Path(inputs['asic_generation'])
    asic_files = tree_hashes(asic)
    for directory in ('apps', 'provider', 'config', 'tool-bin'):
        (generation / directory).mkdir()
    # The setup owner can evolve independently of the copied editable scripts.
    # Record the actual installer that produced these configs, not an old copy.
    copy_checked(Path(__file__), generation / 'setup/workbench_dev.py')
    # A builds under this same lock: capture the pair together, then recheck both.
    with locked('/tmp/opencode/workbench-pt8-build.lock'):
        originals = {kind: Path(inputs['wb_build_root']) / ('default/' + directory + '/main.exe')
                     for kind, directory in (('daemon', 'daemon'), ('client', 'terminal'))}
        before = {kind: sha(path) for kind, path in originals.items()}
        for kind, digest in before.items():
            expected = getattr(args, 'expected_' + kind + '_sha256', None)
            if expected is not None and digest != expected:
                raise RuntimeError('prebuilt ' + kind + ' hash differs from explicit expected capture: ' + digest)
        for kind, path in originals.items():
            copy_checked(path, generation / 'apps' / (kind + '.exe'))
        if before != {kind: sha(path) for kind, path in originals.items()}:
            raise RuntimeError('Workbench app pair changed during capture; retry refresh')
    for directory, names in (
        ('integration/workbench', ('pt8_workbench_provider.py', 'pt8_workbench_runner.py', 'workbench_paths.py', 'wire.py', 'workbench_provider.py')),
        ('tooling_acceptance/workloads/controls', ('pt8_workloads.py',)),
        ('tooling_acceptance/variants/controls', ('pt8_acceptance.py',)),
        ('scripts', ('workbench_git.py',))):
        for name in names:
            copy_checked(source / directory / name, generation / 'provider' / directory / name)
    # Reuse the proven two-job private-root shim, with its existing variable contract.
    copy_checked(source / 'integration/workbench/pt8_workbench_dune.py', generation / 'tool-bin/dune')
    real_git = Path(inputs['git'])
    with real_git.open('rb') as stream:
        if stream.read(4) != b'\x7fELF':
            raise RuntimeError('--git must select the real Git executable, not another dispatcher/wrapper')
    git_context = dict(schema_version=1, real_git=str(real_git), real_git_sha256=sha(real_git),
                       source_roots={str(store / 'project'): inputs['git_dir'], str(source): inputs['git_dir']})
    copy_checked(source / 'scripts/workbench_git.py', generation / 'tool-bin/git')
    (generation / 'tool-bin/git').chmod(0o555)
    write(generation / 'tool-bin/git-context.json', git_context)
    env = dict(OCAMLPATH=str(asic / 'lib') + ':' + str(sdk / 'lib'),
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               HARDCAML_ASIC_GENERATION=str(asic),
               PATH=str(generation / 'tool-bin') + ':' + str(asic / 'bin') + ':' + os.environ['PATH'],
                PT8_PROJECT_ROOT=str(store / 'project'), PT8_REAL_DUNE=inputs['dune'],
                GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    if task_limit is not None:
        env['HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT'] = str(task_limit)
    build = store / 'builds' / receipt.name
    argv = [inputs['dune'], 'build', '--root', str(source), '--build-dir', str(build), '-j2', *TARGETS]
    # Both dependency environments are read-only; no install/refresh of ASIC or SDK.
    with locked('/tmp/opencode/example-pt7-build.lock'):
        with (receipt / 'build.stdout').open('xb') as out, (receipt / 'build.stderr').open('xb') as err:
            result = subprocess.run(argv, cwd=source, env=dict(clean_environment(os.environ), **env),
                                    stdout=out, stderr=err, timeout=1800)
    write(receipt / 'build.json', dict(argv=argv, cwd=str(source), exit_code=result.returncode, max_jobs=2, eda_allocation=0))
    if result.returncode:
        raise RuntimeError('private source build failed; see ' + str(receipt / 'build.stderr'))
    for target in TARGETS:
        copy_checked(build / 'default' / target, generation / 'provider' / Path(target).name)
    models = generation / 'provider/models'
    models.mkdir()
    model_root = Path(inputs['toolchain']) / 'pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog'
    for name in ('RM_IHPSG13_1P_256x16_c2_bm_bist.v', 'RM_IHPSG13_1P_core_behavioral_bm_bist.v'):
        copy_checked(model_root / name, models / name)
    python = inputs['python']
    commands = {
        'controlled-fifo': [str(generation / 'provider/test_provider.exe'), '--simulator', str(generation / 'provider/fifo_sim.exe')],
        'pt8-memory-workloads': [python, '-B', str(generation / 'provider/integration/workbench/pt8_workbench_provider.py'),
            '--generation', str(asic), '--producer-root', str(store / 'project'),
            '--emitter', str(generation / 'provider/workload_emit.exe'), '--model-root', str(models)],
    }
    provider = [python, '-B', str(generation / 'provider/integration/workbench/workbench_provider.py'),
                '--manifest', str(generation / 'manifest.json')]
    def config(kind, values):
        (generation / 'config' / ('hardcaml-workbench-' + kind + '.sexp')).write_text(sexp(values) + '\n')
    config('simulation', [('schema_version', 1), ('provider_executable', provider[0]), ('provider_args', provider[1:]),
                          ('discovery_timeout_seconds', 30), ('run_timeout_seconds', 600)])
    config('preparation', [('schema_version', 1), ('build_target', 'asics/fifo_demo/cli/project.exe'),
                           ('results_root', str(store / 'preparation-results')), ('timeout_seconds', 600)])
    tools = Path(inputs['toolchain'])
    config('asic', [('schema_version', 1), ('project_executable', str(generation / 'provider/project.exe')),
                    ('provider_executable', str(asic / 'bin/hardcaml-asic-flow')), ('results_root', str(store / 'asic-results')),
                    ('toolchain', str(tools)), ('python', [str(tools / '.venv/bin/python')]),
                    ('support_tools', [str(tools / 'tt')]), ('pdk_root', [str(tools / 'pdk')]), ('stage_timeout_seconds', ['600'])])
    if inventory(store / 'project', SOURCE_FILES + SOURCE_DIRS) != sources:
        raise RuntimeError('editable source changed during capture; retry refresh')
    if tree_hashes(asic) != asic_files:
        raise RuntimeError('immutable ASIC dependency changed during capture')
    for path in generation.rglob('*'):
        if path.is_file():
            path.chmod(0o555 if path.stat().st_mode & 0o111 or path.suffix == '.exe' or path == generation / 'tool-bin/dune' else 0o444)
    manifest = dict(schema_version=1, generation_id=receipt.name, generation=str(generation), store=str(store),
                    project_root=str(store / 'project'), paths={k: str(store / v) for k, v in
                        (('project', 'project'), ('state', 'state'), ('discovery', 'discovery'), ('client_state', 'client-state'))},
                    inputs=inputs, environment=env, source_files=sources,
                    suite_sources={suite: inventory(source, SUITE_PATHS[suite]) for suite in SUITES},
                    provider_commands=commands, provider_command=provider,
                    apps={kind: dict(path=str(generation / 'apps' / (kind + '.exe')),
                                     sha256=sha(generation / 'apps' / (kind + '.exe'))) for kind in ('daemon', 'client')},
                    captured_files=tree_hashes(generation), asic_receipt_sha256=sha(asic / 'receipt.json'),
                    asic_files=asic_files, max_jobs=2, eda_allocation=0,
                    setup=dict(source=str(Path(__file__).resolve()), captured=str(generation / 'setup/workbench_dev.py'),
                               sha256=sha(generation / 'setup/workbench_dev.py')),
                    config_files={config_name(kind): sha(generation / 'config' / config_name(kind)) for kind in CONFIGS})
    manifest.update(source_layout=SOURCE_LAYOUT, source_owner_root=str(source_owner(prior, args.root).resolve(strict=True)),
                    source_dirs=list(SOURCE_DIRS), source_roots=list(SOURCE_FILES + SOURCE_DIRS),
                    source_migration=migration, git_context=git_context)
    write(generation / 'manifest.json', manifest)
    (generation / 'manifest.json').chmod(0o444)
    for path in generation.rglob('*'):
        if path.is_file():
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
    # Directory permissions prevent accidental creation in the immutable capture.
    for directory in sorted((p for p in generation.rglob('*') if p.is_dir()), reverse=True):
        sync_dir(directory)
        directory.chmod(0o555)
    sync_dir(generation)
    generation.chmod(0o555)
    return manifest


def prepare(args, store):
    require_source_layout(store / 'project')
    if (store / 'manifest.json').exists():
        require_source_layout(store / 'project', json.loads((store / 'manifest.json').read_text()))
    store.mkdir(parents=True, exist_ok=True)
    # Read-only idempotent prepare also works while the daemon retains its shared
    # startup fence. Only an actual capture/switch requires exclusive ownership.
    if not args.refresh:
        with locked(store / 'prepare.lock', nonblocking=True, shared=True):
            current = selected_manifest(store)
            if current:
                verify(current)
                show(current)
                return
    with locked(store / 'prepare.lock', nonblocking=True):
        for name in ('state', 'discovery', 'client-state', 'generations', 'builds', 'receipts'):
            (store / name).mkdir(exist_ok=True)
        with locked(store / 'state/lifetime.lock', nonblocking=True):
            with locked(store / 'discovery/lifetime.lock', nonblocking=True):
                if args.refresh:
                    recover_publication(store)
                prior = selected_manifest(store)
                if prior and not args.refresh:
                    verify(prior)
                    show(prior)
                    return
                if prior:
                    verify(prior, allow_legacy=args.refresh)
                elif not (store / 'project').exists():
                    pending = store / ('project-copy-' + uuid.uuid4().hex)
                    copy_sources(args.root, pending)
                    rename_new(pending, store / 'project')
                    sync_dir(store)
                # A previous failed initial prepare may have its copied project. Never overwrite it.
                receipt = store / 'receipts' / uuid.uuid4().hex
                receipt.mkdir()
                try:
                    migration = migrate_sources(args, store, prior, receipt) if args.import_missing_source or args.update_owned_support else None
                    missing = [name for name in SOURCE_FILES + SOURCE_DIRS if not (store / 'project' / name).exists()]
                    if missing:
                        raise RuntimeError('missing authored source: ' + ', '.join(missing) +
                                           '; use prepare --refresh --import-missing-source; existing directories are never merged')
                    manifest = (capture_apps_only(args, store, prior, receipt) if getattr(args, 'apps_only', False) else
                                capture(args, store, prior, receipt, migration))
                    manifest_link = store / 'manifest.json'
                    if not manifest_link.is_symlink():
                        if manifest_link.exists():
                            raise RuntimeError('refusing unrelated store manifest')
                        manifest_link.symlink_to('selected/manifest.json')
                    # All potentially failing integrity checks precede publication.
                    write(receipt / 'prepared.json', dict(status='prepared', generation=manifest['generation'],
                          previous=prior['generation'] if prior else None, source_files=manifest['source_files']))
                    sync_dir(store / 'generations')
                    # Recheck ownership after the build; never overwrite intervening edits.
                    if prior:
                        verify(prior, allow_legacy=args.refresh)
                    publish(store, prior, manifest, receipt)
                except Exception as error:
                    write(receipt / 'failure.json', dict(error=str(error), previous=prior['generation'] if prior else None))
                    raise
                show(manifest)


def launch(args, store, extras):
    # Inherited prepare lock closes the refresh/start race for the daemon lifetime.
    with locked(store / 'prepare.lock', nonblocking=True, inheritable=args.command == 'daemon', shared=True):
        manifest = selected_manifest(store)
        if manifest is None:
            raise RuntimeError('not prepared; run scripts/workbench_dev.py prepare')
        verify(manifest)
        show(manifest, stream=sys.stderr)
        if git_context_diagnostic(manifest):
            raise RuntimeError(git_context_diagnostic(manifest))
        env = environment(manifest)
        env['XDG_STATE_HOME'] = str(store / 'client-state')
        if args.command == 'daemon':
            command = [manifest['apps']['daemon']['path'], '--port', '0', '--state-dir', str(store / 'state'),
                       '--discovery-dir', str(store / 'discovery')]
        else:
            for option in extras:
                if option.split('=', 1)[0] in ('--connect', '--project-root', '--discover-project', '--environment', '--daemon'):
                    raise RuntimeError('client cannot override fixed connection/project/environment')
            metadata = record(parse((store / 'discovery/daemon.sexp').read_text()), ('endpoint', 'instance_id', 'pid'))
            # A stale metadata file never authorizes connection to a different project daemon.
            with (store / 'state/lifetime.lock').open('a+b') as state:
                try:
                    fcntl.flock(state, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    raise RuntimeError('development daemon is not running; start it explicitly')
            command = [manifest['apps']['client']['path'], '--connect', metadata['endpoint'],
                       '--project-root', manifest['project_root'], '--environment', 'inherited', *extras]
        os.chdir(manifest['project_root'])
        os.execve(command[0], command, env)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--store', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare', allow_abbrev=False)
    prep.add_argument('--refresh', action='store_true')
    prep.add_argument('--apps-only', action='store_true',
                      help='explicit reviewed app-pair recapture; retain provider/config/environment history scope')
    prep.add_argument('--synthesis-task-limit', type=int, choices=(6,),
                      help='opt in to total container tasks<=6 for fresh synthesis/report collection; retained on refresh')
    prep.add_argument('--import-missing-source', action='store_true', help='explicitly add entirely missing approved authored source entries')
    prep.add_argument('--update-owned-support', action='store_true', help='explicitly update only baseline-matching B-owned support files')
    for kind in ('client', 'daemon'):
        prep.add_argument('--expected-' + kind + '-sha256', help='require this exact prebuilt app hash before capture')
    for name in ('asic-generation', 'sdk-prefix', 'wb-build-root', 'dune', 'git'):
        prep.add_argument('--' + name, type=Path)
    for name in ('daemon', 'client', 'status'):
        sub.add_parser(name, allow_abbrev=False)
    args, extras = parser.parse_known_args(argv)
    extras = extras[1:] if extras[:1] == ['--'] else extras
    if extras and args.command != 'client':
        parser.error('unexpected options: ' + ' '.join(extras))
    if args.command == 'prepare' and (args.import_missing_source or args.update_owned_support) and not args.refresh:
        parser.error('source migration flags require explicit prepare --refresh')
    if args.command == 'prepare' and args.apps_only and (not args.refresh or args.import_missing_source or args.update_owned_support):
        parser.error('--apps-only requires --refresh and cannot migrate source/support')
    args.root = args.root.resolve(strict=True)
    store = args.store.absolute() if args.store else args.root / '.dev/workbench-development'
    if store.exists() and store.resolve() != store:
        raise RuntimeError('store must be a fixed canonical path, not a symlink')
    # Diagnose before acquiring locks or recovering an old publication journal.
    require_source_layout(store / 'project')
    if (store / 'manifest.json').exists():
        require_source_layout(store / 'project', json.loads((store / 'manifest.json').read_text()))
    if args.command == 'prepare':
        prepare(args, store)
    elif args.command == 'status':
        manifest = selected_manifest(store)
        if manifest is None:
            print(json.dumps(dict(prepared=False, store=str(store))))
        else:
            verify(manifest)
            show(manifest)
    else:
        launch(args, store, extras)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('Development session: ' + str(error), file=sys.stderr)
        sys.exit(2)
