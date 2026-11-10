#!/usr/bin/env python3
"""Composite FS2v1 catalog and exec-only suite routing. Never builds."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from wire import parse, record, sexp
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from workbench_git import clean_environment

SUITES = ('controlled-fifo', 'pt8-memory-workloads')
LIMIT = 1024 * 1024
SOURCE_DIRS = ('lib', 'asic', 'bin', 'memory', 'variants', 'workloads',
               'simulation', 'test_support', 'scripts', 'test', 'asic_test',
               'timing', 'named_timing', 'physical_timing')
# Only the authored harness, never acceptance result/snapshot directories.
ACCEPTANCE_FILES = ('acceptance/dune', 'acceptance/export_trace.ml',
                    'acceptance/check_bundle.py', 'acceptance/replay.v')
SOURCE_FILES = ('dune-project', 'asic-dependency.json', 'README.md', 'bootstrap.sh', *ACCEPTANCE_FILES)
SUITE_PATHS = {
    'controlled-fifo': ('dune-project', 'lib', 'simulation', 'test_support', 'scripts/workbench_git.py'),
    'pt8-memory-workloads': ('dune-project', 'variants', 'workloads',
        'simulation/wire.py', 'simulation/workbench_provider.py',
        'scripts/pt8_workbench_provider.py', 'scripts/pt8_workbench_runner.py',
        'scripts/pt8_workloads.py', 'scripts/pt8_acceptance.py'),
}
SUITE_PATHS['pt8-memory-workloads'] += ('scripts/workbench_git.py',)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory(root, names):
    """Independent regular source files; reject symlinks instead of following owners."""
    root = Path(root)
    result = {}
    def visit(path):
        if path.is_symlink():
            raise ValueError('source symlink is not an independent snapshot: ' + str(path))
        if path.is_dir():
            for child in sorted(path.iterdir()):
                if child.name == '__pycache__' or child.name.startswith(('_build', '.dev', '.git')):
                    continue
                if child.suffix != '.pyc':
                    visit(child)
        elif path.is_file():
            result[str(path.relative_to(root))] = sha(path)
        else:
            raise ValueError('missing/nonregular source: ' + str(path))
    for name in names:
        visit(root / name)
    return result


def source_drift(manifest, suite):
    expected = manifest['suite_sources'][suite]
    try:
        actual = inventory(manifest['project_root'], SUITE_PATHS[suite])
    except (OSError, ValueError) as error:
        return ['source inventory unavailable: ' + str(error)]
    return sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))


def bounded_read(path, limit=LIMIT):
    with Path(path).open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('input exceeds byte limit: ' + str(path))
    return data.decode('utf-8')


def discover_child(command, env, timeout=8):
    """Bound both pipes while reading, including a child that never exits."""
    with subprocess.Popen(command + ['discover', '--protocol-version', '1'],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) as child:
        buffers = {child.stdout: bytearray(), child.stderr: bytearray()}
        try:
            with selectors.DefaultSelector() as poll:
                for pipe in buffers:
                    poll.register(pipe, selectors.EVENT_READ)
                deadline = time.monotonic() + timeout
                while poll.get_map():
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise ValueError('child discovery timed out')
                    for key, _ in poll.select(min(left, .1)):
                        pipe = key.fileobj
                        block = os.read(pipe.fileno(), 65536)
                        if not block:
                            poll.unregister(pipe)
                            continue
                        buffers[pipe].extend(block)
                        if len(buffers[pipe]) > (LIMIT if pipe is child.stdout else 65536):
                            raise ValueError('child discovery output exceeds byte limit')
                child.wait(timeout=max(.001, deadline - time.monotonic()))
            if child.returncode:
                raise ValueError('child discovery failed: ' + buffers[child.stderr].decode('utf-8', 'replace')[:2000])
            return parse(buffers[child.stdout].decode('utf-8'))
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()


def validate_catalog(value):
    d = record(value, ('protocol_version', 'suites'))
    if d['protocol_version'] != '1' or not isinstance(d['suites'], list) or len(d['suites']) > 64:
        raise ValueError('invalid discovery version/suite count')
    def text(s):
        if not isinstance(s, str) or '\0' in s or len(s.encode()) > 4096:
            raise ValueError('invalid discovery string')
    def unique(values, field):
        seen = set()
        for value in values:
            k = value[field]
            if not isinstance(k, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', k) or k in seen:
                raise ValueError('invalid/duplicate discovery key')
            seen.add(k)
    suites = [record(s, ('id', 'label', 'cases', 'parameters', 'default_seed')) for s in d['suites']]
    unique(suites, 'id')
    total = 0
    for s in suites:
        text(s['label'])
        seed = s['default_seed']
        if not isinstance(seed, str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}', seed) or int(seed) >= 2**64:
            raise ValueError('invalid discovery seed')
        if not isinstance(s['cases'], list) or not s['cases'] or not isinstance(s['parameters'], list) or len(s['parameters']) > 32:
            raise ValueError('invalid discovery cases/parameters')
        cases = [record(c, ('id', 'label')) for c in s['cases']]
        unique(cases, 'id')
        total += len(cases)
        for c in cases:
            text(c['label'])
        parameters = [record(p, ('key', 'label', 'default', 'choices')) for p in s['parameters']]
        unique(parameters, 'key')
        for p in parameters:
            text(p['label'])
            text(p['default'])
            if not isinstance(p['choices'], list) or len(p['choices']) > 64:
                raise ValueError('invalid discovery choices')
            for c in p['choices']:
                text(c)
            if p['choices'] and p['default'] not in p['choices']:
                raise ValueError('default outside choices')
    if total > 1024:
        raise ValueError('too many discovery cases')
    return d


def environment(manifest):
    # Do not propagate an inherited daemon/shell repository selector into tools
    # probing collateral or other repositories. Also reject legacy global captures.
    return clean_environment(dict(os.environ, **manifest['environment'], PYTHONDONTWRITEBYTECODE='1'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('operation', choices=('discover', 'run'))
    parser.add_argument('--protocol-version', required=True, choices=['1'])
    parser.add_argument('--request', type=Path)
    parser.add_argument('--events', type=Path)
    parser.add_argument('--artifact-dir', type=Path)
    original = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(original)
    manifest = json.loads(bounded_read(args.manifest, 8 * LIMIT))
    env = environment(manifest)
    if args.operation == 'discover':
        suites = []
        for suite in SUITES:
            child = discover_child(manifest['provider_commands'][suite], env)
            fields = validate_catalog(child)
            if [dict(s)['id'] for s in fields['suites']] != [suite]:
                raise ValueError('child catalog does not match owned suite: ' + suite)
            suites.extend(fields['suites'])
        value = [('protocol_version', 1), ('suites', suites)]
        validate_catalog(parse(sexp(value)))
        output = sexp(value) + '\n'
        if len(output.encode()) > LIMIT:
            raise ValueError('combined discovery exceeds 1 MiB')
        print(output, end='', flush=True)
        return 0
    if not all((args.request, args.events, args.artifact_dir)):
        parser.error('run requires request, events and artifact-dir')
    req = record(parse(bounded_read(args.request)), ('protocol_version', 'attempt_id', 'selection'))
    selection = record(req['selection'], ('suite', 'cases', 'seed', 'parameters', 'asic_inputs'))
    suite = selection['suite']
    if not isinstance(suite, str) or suite not in SUITES:
        raise ValueError('unknown suite')
    drift = source_drift(manifest, suite)
    if drift:
        raise ValueError('stale ' + suite + ' source capture (' + ', '.join(drift[:8]) +
                         '); run scripts/workbench_dev.py prepare --refresh in the example checkout' +
                         ' (same --store for private verification)')
    # Strip ONLY the router prefix. All operation/request/events/artifact argv is original.
    for index, token in enumerate(original):
        if token == '--manifest':
            del original[index:index + 2]
            break
        if token.startswith('--manifest='):
            del original[index]
            break
    command = manifest['provider_commands'][suite] + original
    os.execve(command[0], command, env)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, RecursionError, subprocess.TimeoutExpired) as error:
        print('Composite provider: ' + str(error), file=sys.stderr)
        sys.exit(2)
