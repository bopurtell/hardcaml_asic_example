#!/usr/bin/env python3
"""Explicit PDK-free FIFO build/install/configure. Never runs tests or daemons."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import re
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/workbench'))
from wire import parse, record, sexp
import config_location


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_write(path, contents):
    with path.open('xb') as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def replace_bytes(path, contents):
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    durable_write(pending, contents)
    os.replace(pending, path)
    sync_directory(path.parent)


def config_fields(contents):
    fields = record(parse(contents.decode()), [
        'schema_version', 'provider_executable', 'provider_args',
        'discovery_timeout_seconds', 'run_timeout_seconds'])
    if fields['schema_version'] != '1':
        raise RuntimeError('Adoption requires schema_version 1')
    for key, maximum in (('discovery_timeout_seconds', 60), ('run_timeout_seconds', 86400)):
        value = fields[key]
        if not isinstance(value, str) or not re.fullmatch('[1-9][0-9]*', value) or not 1 <= int(value) <= maximum:
            raise RuntimeError('Invalid adoption timeout: ' + key)
    return fields


def executable(path):
    path = path.resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError('not an executable file: ' + str(path))
    return path


def adoption_timeouts(root, old, ownership, expected):
    if not re.fullmatch('[0-9a-f]{64}', expected) or old is None or digest(old) != expected:
        raise RuntimeError('Adoption SHA256 does not match current configuration bytes')
    if ownership is None:
        raise RuntimeError('Adoption requires existing ownership manifest')
    owned = json.loads(ownership)
    generation = Path(owned['generation'])
    if (not generation.is_absolute() or generation.resolve(strict=True) != generation
            or generation.parent != root / '.dev/fifo-simulation'):
        raise RuntimeError('Adoption requires an original owned project generation')
    hashes = owned.get('sha256', {})
    if not isinstance(hashes, dict) or not hashes:
        raise RuntimeError('Adoption requires generation checksums')
    for name, checksum in hashes.items():
        path = generation / name
        if (Path(name).name != name or path.is_symlink() or not path.is_file()
                or digest(path.read_bytes()) != checksum):
            raise RuntimeError('Original generation checksum/provenance mismatch: ' + name)
    original = generation / 'configuration.sexp'
    if not original.exists():
        receipt = Path(owned.get('receipt', ''))
        if (not receipt.is_absolute() or receipt.resolve(strict=True) != receipt
                or receipt.parent != root / '.dev/fifo-simulation-receipts'):
            raise RuntimeError('Adoption requires original configuration provenance')
        original = receipt / 'configuration.sexp'
    if original.is_symlink() or digest(original.read_bytes()) != owned['config_sha256']:
        raise RuntimeError('Original owned configuration checksum mismatch')
    previous = config_fields(original.read_bytes())
    current = config_fields(old)
    for key in ('schema_version', 'provider_executable', 'provider_args'):
        if current[key] != previous[key]:
            raise RuntimeError('Adoption refuses unrelated provider configuration: ' + key)
    if (previous['provider_executable'] == str(generation / 'test_provider.exe')
            and previous['provider_args'] == []):
        required = {'test_provider.exe', 'fifo_sim.exe'}
    elif (isinstance(previous['provider_executable'], str)
          and Path(previous['provider_executable']).is_absolute()
          and Path(previous['provider_executable']).name.startswith('python')
          and previous['provider_args'] == [str(generation / 'provider.py')]):
        required = {'provider.py', 'wire.py', 'fifo_sim.exe'}
    else:
        raise RuntimeError('Adoption requires a recognized original FIFO provider')
    if not required <= hashes.keys():
        raise RuntimeError('Adoption requires original provider and simulator checksums')
    return int(current['discovery_timeout_seconds']), int(current['run_timeout_seconds'])


def main(argv=None, *, root=ROOT):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', action='store_true', help='explicitly build test_provider.exe and fifo_sim.exe at -j<=6')
    p.add_argument('--with-switch', type=Path, default=ROOT.parent / 'hardcaml_workbench/scripts/with-switch.sh')
    p.add_argument('--build-dir', type=Path, default=Path('/tmp/opencode/native-provider-example'))
    p.add_argument('--jobs', type=int, choices=range(1, 7), default=6)
    p.add_argument('--simulator', type=Path, help='already verified executable; required without --build')
    p.add_argument('--provider', type=Path, help='prebuilt native test_provider.exe; required without --build')
    p.add_argument('--adopt-config-sha256', metavar='EXPECTED',
                   help='explicitly adopt these exact edited config bytes, with verified prior ownership and persistent backup')
    a = p.parse_args(argv)
    root = root.resolve(strict=True)
    config = config_location.selected(root, 'hardcaml-workbench-simulation.sexp')
    manifest = root / '.dev/fifo-simulation-install.json'
    old = config.read_bytes() if config.exists() else None
    ownership = manifest.read_bytes() if manifest.exists() else None
    timeouts = (10, 120)
    if a.adopt_config_sha256 is not None:
        if config.is_symlink() or manifest.is_symlink():
            raise RuntimeError('Adoption refuses symlink configuration or ownership')
        timeouts = adoption_timeouts(root, old, ownership, a.adopt_config_sha256)
    elif old is not None:
        if ownership is None or digest(old) != json.loads(ownership)['config_sha256']:
            raise RuntimeError('Refusing to overwrite unrelated or edited FS2 configuration: ' + str(config))
    if a.build and (a.simulator is not None or a.provider is not None):
        p.error('--build cannot be combined with prebuilt executables')
    if not a.build and (a.simulator is None or a.provider is None):
        p.error('supply both --provider and --simulator or explicitly --build')
    if not a.build:
        a.simulator, a.provider = executable(a.simulator), executable(a.provider)
    manifest.parent.mkdir(exist_ok=True)
    with (manifest.parent / 'fifo-simulation-install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        install(a, root, config, manifest, old, ownership, timeouts)


def install(a, root, config, manifest, old, ownership, timeouts):
    targets = config_location.destinations(root, config.name)
    def unchanged():
        if (config_location.destinations(root, config.name) != targets
                or any(config_location.read_regular(path) != old for path in targets)):
            raise RuntimeError('configuration changed during install; refusing edit')
        if (manifest.read_bytes() if manifest.exists() else None) != ownership:
            raise RuntimeError('ownership changed during install; refusing edit')

    unchanged()
    if a.build:
        subprocess.run([str(a.with_switch.resolve(strict=True)), 'dune', 'build', '--root', str(root),
                        '--build-dir', str(a.build_dir.resolve()), '-j' + str(a.jobs),
                        'ip/controlled_fifo/verif/simulation/test_provider.exe',
                        'ip/controlled_fifo/verif/simulation/fifo_sim.exe'], check=True,
                       env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1'))
        binary = a.build_dir / 'default/ip/controlled_fifo/verif/simulation/fifo_sim.exe'
        provider = a.build_dir / 'default/ip/controlled_fifo/verif/simulation/test_provider.exe'
    else:
        binary = a.simulator
        provider = a.provider
    binary, provider = executable(binary), executable(provider)
    generation = root / '.dev/fifo-simulation' / uuid.uuid4().hex
    generation.mkdir(parents=True)
    shutil.copy2(binary, generation / 'fifo_sim.exe')
    shutil.copy2(provider, generation / 'test_provider.exe')
    for path in generation.iterdir():
        with path.open('rb') as stream:
            os.fsync(stream.fileno())
    sync_directory(generation)
    sync_directory(generation.parent)
    contents = (sexp([('schema_version', 1), ('provider_executable', str(generation / 'test_provider.exe')),
                       ('provider_args', []),
                       ('discovery_timeout_seconds', timeouts[0]), ('run_timeout_seconds', timeouts[1])]) + '\n').encode()
    unchanged()
    receipt = root / '.dev/fifo-simulation-receipts' / generation.name
    receipt.mkdir(parents=True)
    sync_directory(receipt.parent)
    sync_directory(manifest.parent)
    if old is not None:
        durable_write(receipt / 'previous-configuration.sexp', old)
    if ownership is not None:
        durable_write(receipt / 'previous-ownership.json', ownership)
    durable_write(receipt / 'configuration.sexp', contents)
    installed = dict(generation=str(generation), receipt=str(receipt),
        config_sha256=digest(contents),
        sha256={f.name: digest(f.read_bytes()) for f in generation.iterdir()})
    durable_write(receipt / 'ownership.json', json_bytes(installed))
    transaction = dict(status='prepared', config=str(config), generation=str(generation),
        config_paths=list(map(str, targets)),
        adoption_sha256=a.adopt_config_sha256,
        previous_config_sha256=digest(old) if old is not None else None,
        previous_ownership_sha256=digest(ownership) if ownership is not None else None,
        config_sha256=digest(contents), ownership_sha256=digest(json_bytes(installed)),
        discovery_timeout_seconds=timeouts[0], run_timeout_seconds=timeouts[1])
    durable_write(receipt / 'receipt.json', json_bytes(transaction))
    pending = manifest.parent / ('configuration-' + generation.name + '.pending')
    durable_write(pending, contents)
    unchanged()
    changed = []
    try:
        for path in targets:
            if old is None:
                os.link(pending, path)
            else:
                replace_bytes(path, contents)
            changed.append(path)
            sync_directory(path.parent)
    except Exception:
        for path in reversed(changed):
            if config_location.read_regular(path) != contents:
                raise RuntimeError('concurrent configuration edit; inspect prepared receipt')
            if old is None:
                path.unlink()
            else:
                replace_bytes(path, old)
        raise
    finally:
        pending.unlink(missing_ok=True)
    replace_bytes(manifest, json_bytes(installed))
    transaction['status'] = 'published'
    replace_bytes(receipt / 'receipt.json', json_bytes(transaction))
    print(json.dumps(dict(config=str(config), generation=str(generation), receipt=str(receipt),
                         config_sha256=digest(contents)), indent=2))


if __name__ == '__main__':
    main()
