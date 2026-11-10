#!/usr/bin/env python3
"""B's bounded direct-provider/lifecycle acceptance in a new private store. No EDA.

Uses the real captured SDK/native FIFO/PT8 tools. Every preparation build is -j2
under the shared example lock. C's native HTTP/PTY verification is separate.
"""
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
import urllib.request
import uuid
import zlib
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
import workbench_provider as router
import workbench_dev as dev
import workbench_git as scoped_git
from wire import parse, sexp


def selection(suite='controlled-fifo', *, mismatch=False, cases=None, seed=None):
    fifo = suite == 'controlled-fifo'
    return [('suite', suite), ('cases', cases or (['directed', 'seeded'] if fifo else ['flops256', 'exact256'])),
            ('seed', seed or ('18446744073709551615' if fifo else '34097')),
            ('parameters', [('checker', 'mismatch' if mismatch else 'normal'), ('cycles', '64')] if fifo else []),
            ('asic_inputs', [])]


def git_fixture(root, text):
    """Python constructs a tiny real Git object/index fixture; no Git write CLI."""
    metadata = root / '.git'
    (metadata / 'objects').mkdir(parents=True)
    (metadata / 'refs/heads').mkdir(parents=True)
    def obj(kind, data):
        raw = kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data
        oid = hashlib.sha1(raw).hexdigest()
        path = metadata / 'objects' / oid[:2] / oid[2:]
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(zlib.compress(raw))
        return oid
    tracked = root / 'tracked.txt'
    tracked.write_text(text)
    blob = obj('blob', tracked.read_bytes())
    tree = obj('tree', b'100644 tracked.txt\0' + bytes.fromhex(blob))
    commit = obj('commit', ('tree ' + tree + '\nauthor Fixture <fixture@example.test> 1 +0000\n'
                  'committer Fixture <fixture@example.test> 1 +0000\n\n' + text).encode())
    (metadata / 'HEAD').write_text('ref: refs/heads/main\n')
    (metadata / 'refs/heads/main').write_text(commit + '\n')
    st = tracked.stat()
    fields = (int(st.st_ctime), st.st_ctime_ns % 10**9, int(st.st_mtime), st.st_mtime_ns % 10**9,
              st.st_dev, st.st_ino, 0o100644, st.st_uid, st.st_gid, st.st_size)
    entry = struct.pack('>10I20sH', *(n & 0xffffffff for n in fields), bytes.fromhex(blob), len('tracked.txt'))
    entry += b'tracked.txt\0'
    entry += b'\0' * ((-len(entry)) % 8)
    index = b'DIRC' + struct.pack('>II', 2, 1) + entry
    (metadata / 'index').write_bytes(index + hashlib.sha1(index).digest())
    return commit


class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = STORE
        cls.evidence = STORE / 'test-evidence'
        cls.evidence.mkdir()
        cls.counter = 0
        cls.protected = {}
        for name in ('hardcaml-workbench-simulation.sexp', 'hardcaml-workbench-asic.sexp',
                     'hardcaml-workbench-preparation.sexp', 'asic/project.ml', 'acceptance/dune'):
            path = ROOT / name
            cls.protected[str(path)] = router.sha(path)
        for name in ('simulation', 'asic'):
            fields = dict(parse((ROOT / ('hardcaml-workbench-' + name + '.sexp')).read_text()))
            for key in ('provider_executable', 'project_executable'):
                if key in fields:
                    path = Path(fields[key])
                    cls.protected[str(path)] = router.sha(path)
        cls.prepare()
        cls.manifest = json.loads((STORE / 'manifest.json').read_text())
        cls.initial = cls.manifest
        cls.provider = cls.manifest['provider_command']
        cls.children = cls.manifest['provider_commands']

    @classmethod
    def prepare(cls, *options, expected=0):
        cls.counter += 1
        command = [sys.executable, '-B', str(ROOT / 'scripts/workbench_dev.py'),
                   '--store', str(cls.store), 'prepare', *options]
        result = subprocess.run(command, capture_output=True, timeout=1800)
        prefix = cls.evidence / ('prepare-%02d' % cls.counter)
        prefix.with_suffix('.stdout').write_bytes(result.stdout)
        prefix.with_suffix('.stderr').write_bytes(result.stderr)
        if result.returncode != expected:
            raise AssertionError((command, result.returncode, result.stderr.decode()))
        return result

    @classmethod
    def tearDownClass(cls):
        after = {path: router.sha(path) for path in cls.protected}
        dev.write(cls.evidence / 'preservation.json', dict(before=cls.protected, after=after, unchanged=after == cls.protected))
        if after != cls.protected:
            raise AssertionError('protected owner files changed')

    def request(self, label, selected=None, *, command=None, attempt=None):
        directory = self.evidence / label
        directory.mkdir()
        artifacts = directory / 'artifacts'
        artifacts.mkdir()
        request = directory / 'request.sexp'
        request.write_text(sexp([('protocol_version', 1), ('attempt_id', attempt or label),
                                 ('selection', selected or selection())]) + '\n')
        events = directory / 'events.sexp'
        events.touch()
        argv = (command or self.provider) + ['run', '--protocol-version', '1', '--request', str(request),
                                           '--events', str(events), '--artifact-dir', str(artifacts)]
        return directory, argv

    def execute(self, directory, argv, expected=0):
        result = subprocess.run(argv, capture_output=True, timeout=180)
        (directory / 'stdout.log').write_bytes(result.stdout)
        (directory / 'stderr.log').write_bytes(result.stderr)
        dev.write(directory / 'command.json', dict(argv=argv, exit_code=result.returncode))
        self.assertEqual(result.returncode, expected, result.stderr.decode())
        events = [dict(parse(line)) for line in (directory / 'events.sexp').read_text().splitlines()]
        if events:
            self.assertEqual([int(e['sequence']) for e in events], list(range(len(events))))
            self.assertTrue(all(e['attempt_id'] == dict(parse((directory / 'request.sexp').read_text()))['attempt_id'] for e in events))
        return result, events

    def test_01_catalog_exact_union(self):
        for name in router.SOURCE_FILES + router.SOURCE_DIRS:
            self.assertTrue((self.store / 'project' / name).exists(), name)
            self.assertTrue((Path(self.initial['generation']) / 'source' / name).exists(), name)
        self.assertEqual(self.initial['source_dirs'], list(router.SOURCE_DIRS))
        self.prepare('--refresh', '--expected-client-sha256', '0' * 64, expected=2)
        self.assertEqual(dev.selected_manifest(self.store), self.initial)
        catalogs = []
        for command in [self.children[suite] for suite in router.SUITES] + [self.provider]:
            result = subprocess.run(command + ['discover', '--protocol-version', '1'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            catalogs.append(router.validate_catalog(parse(result.stdout.decode())))
        self.assertEqual(catalogs[2]['suites'], catalogs[0]['suites'] + catalogs[1]['suites'])
        dev.write(self.evidence / 'catalogs.json', catalogs)

    def test_02_fifo_real_checks_and_delegation(self):
        for label, selected, outcome in (
            ('fifo-normal', selection(), 'Passed'),
            ('fifo-zero', selection(seed='0', cases=['seeded']), 'Passed'),
            ('fifo-mismatch', selection(mismatch=True), 'Failed'),
        ):
            directory, argv = self.request(label, selected)
            result, events = self.execute(directory, argv)
            self.assertEqual(events[0]['payload'], 'Started')
            self.assertEqual(events[-1]['payload'], ['Finished', outcome])
            for case in dict(selected)['cases']:
                report = (directory / 'artifacts' / (case + '.sexp')).read_text()
                self.assertIn(outcome, report)
                self.assertIn('checks', report)
                wave = directory / 'artifacts' / (case + '.vcd')
                self.assertIn(b'$enddefinitions', wave.read_bytes())
                if outcome == 'Failed':
                    self.assertIn('injected true', report)
                    self.assertIn('occupancy', report)
            if label == 'fifo-normal':
                direct, command = self.request('fifo-native-direct', selected,
                    command=self.children['controlled-fifo'], attempt=label)
                raw, original = self.execute(direct, command)
                self.assertEqual(original, events)
                self.assertEqual(raw.stdout, result.stdout)
                for path in (directory / 'artifacts').iterdir():
                    # VCD date is metadata, every other byte must match.
                    def stable(data):
                        if path.suffix == '.vcd' and b'$date' in data:
                            begin = data.index(b'$date')
                            end = data.index(b'$end', begin) + 4
                            return data[:begin] + b'$date <date> $end' + data[end:]
                        return data
                    self.assertEqual(stable(path.read_bytes()), stable((direct / 'artifacts' / path.name).read_bytes()))

    def test_03_pt8_both_actual_result_waveforms(self):
        directory, argv = self.request('pt8-positive-both', selection('pt8-memory-workloads'))
        _, events = self.execute(directory, argv)
        self.assertEqual(events[-1]['payload'], ['Finished', 'Passed'])
        for case in ('flops256', 'exact256'):
            reference = json.loads((directory / 'artifacts' / (case + '-result-reference.json')).read_text())
            result = Path(reference['result'])
            self.assertTrue(result.is_relative_to(self.store / 'project/.dev/asic-pt8-workbench/workloads'))
            inspected = subprocess.run([self.initial['inputs']['asic_generation'] + '/bin/hardcaml-asic-flow',
                'workload-inspect', str(result), '--json'], capture_output=True, timeout=30, check=True)
            inspection = json.loads(inspected.stdout)
            self.assertEqual(inspection['source_digest'], reference['source_digest'])
            self.assertEqual(inspection['outcome']['functional'], 'pass')
            self.assertEqual(len(inspection['metrics']), 7)
            (directory / (case + '-inspection.json')).write_bytes(inspected.stdout)
            wave = directory / 'artifacts' / (case + '-waveform.vcd')
            self.assertEqual(wave.read_bytes(), (result.parent / 'waveform.vcd').read_bytes())
            self.assertTrue(50000 < wave.stat().st_size < 100000)
            self.assertEqual(json.loads((result.parent / 'waveform.json').read_text())['cycles'], 1307)
            simulation = json.loads((result.parent / 'simulation.json').read_text())
            self.assertEqual(simulation['rtl_mode'], 'implementation')

    def test_04_invalid_selection_no_events(self):
        for label, changes in (
            ('unknown-suite', {'suite': 'unknown'}),
            ('duplicate-case', {'cases': ['directed', 'directed']}),
            ('bad-seed', {'seed': '18446744073709551616'}),
            ('bad-options', {'parameters': [('cycles', '65'), ('checker', 'normal')]}),
        ):
            selected = dict(selection())
            selected.update(changes)
            directory, argv = self.request(label, list(selected.items()))
            self.execute(directory, argv, expected=2 if label == 'unknown-suite' else 1)
            self.assertEqual((directory / 'events.sexp').read_bytes(), b'')
            self.assertEqual(list((directory / 'artifacts').iterdir()), [])
        selected = dict(selection('pt8-memory-workloads'))
        selected['seed'] = '42'
        directory, argv = self.request('pt8-wrong-seed', list(selected.items()))
        self.execute(directory, argv, expected=2)
        self.assertEqual((directory / 'events.sexp').read_bytes(), b'')

    def test_05_discovery_bounds_failure_and_no_partial(self):
        for label, program in (
            ('oversize', 'import sys; sys.stdout.write("x" * (1024*1024+1))'),
            ('stderr', 'import sys; sys.stderr.write("x" * 65537)'),
            ('timeout', 'import time; time.sleep(10)'),
            ('nonzero', 'raise SystemExit(7)'),
            ('malformed', 'print("(broken")'),
        ):
            with self.assertRaises((ValueError, subprocess.TimeoutExpired)):
                router.discover_child([sys.executable, '-c', program], os.environ, timeout=.3)
        bad = dict(self.initial)
        bad['provider_commands'] = dict(self.children)
        bad['provider_commands']['pt8-memory-workloads'] = [sys.executable, '-c', 'print("(broken")']
        path = self.evidence / 'bad-discovery-manifest.json'
        dev.write(path, bad)
        command = [sys.executable, '-B', str(ROOT / 'simulation/workbench_provider.py'), '--manifest', str(path),
                   'discover', '--protocol-version', '1']
        result = subprocess.run(command, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')
        for invalid in (
            [('protocol_version', 1), ('suites', [dict(parse(subprocess.run(self.children['controlled-fifo'] +
                ['discover', '--protocol-version', '1'], capture_output=True, check=True).stdout.decode()))['suites'][0]] * 2)],
            [('protocol_version', 2), ('suites', [])],
        ):
            with self.assertRaises(ValueError):
                router.validate_catalog(parse(sexp(invalid)))

    def test_06_exec_identity_and_untouched_argv(self):
        directory = self.evidence / 'exec-identity'
        directory.mkdir()
        fixture = directory / 'child.py'
        fixture.write_text('import json,os,sys\nprint(json.dumps(dict(pid=os.getpid(),pgid=os.getpgrp(),argv=sys.argv[1:])))\n')
        fake = dict(self.initial)
        fake['provider_commands'] = dict(self.children, **{'controlled-fifo': [sys.executable, str(fixture)]})
        manifest = directory / 'manifest.json'
        dev.write(manifest, fake)
        command = [sys.executable, '-B', str(ROOT / 'simulation/workbench_provider.py'), '--manifest', str(manifest)]
        transport, argv = self.request('exec-transport', command=command)
        child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = child.communicate(timeout=30)
        self.assertEqual(child.returncode, 0, stderr.decode())
        identity = json.loads(stdout)
        self.assertEqual(identity['pid'], child.pid)
        self.assertEqual(identity['pgid'], os.getpgrp())
        self.assertEqual(identity['argv'], argv[len(command):])
        self.assertEqual((transport / 'events.sexp').read_bytes(), b'')
        dev.write(directory / 'identity.json', identity)

    def test_07_real_cancellation_valid_prefix_and_reaping(self):
        # Adopt/reap only descendants launched by this test, including a native
        # FIFO child whose parent receives the same supervisor process-group TERM.
        self.assertEqual(ctypes.CDLL(None).prctl(36, 1, 0, 0, 0), 0)  # PR_SET_CHILD_SUBREAPER
        for suite in router.SUITES:
            selected = dict(selection(suite, cases=['seeded'] if suite == 'controlled-fifo' else ['exact256']))
            if suite == 'controlled-fifo':
                selected['parameters'] = [('checker', 'normal'), ('cycles', '20000')]
            directory, argv = self.request('cancel-' + suite, list(selected.items()))
            observed = []
            with (directory / 'stdout.log').open('wb') as out, (directory / 'stderr.log').open('wb') as err:
                process = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True)
                try:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline and process.poll() is None:
                        children = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
                        if children:
                            observed = list(map(int, children))
                            if suite == 'pt8-memory-workloads':
                                process.send_signal(signal.SIGTERM)  # runner must reap even PID-only signal
                            else:
                                os.killpg(process.pid, signal.SIGTERM)
                            break
                        time.sleep(.001)
                    self.assertTrue(observed, 'no owned native child observed')
                    code = process.wait(timeout=10)
                    self.assertEqual(code, 130 if suite == 'pt8-memory-workloads' else -signal.SIGTERM)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                for pid in observed:
                    try:
                        os.waitpid(pid, 0)
                    except ChildProcessError:
                        pass
                    self.assertFalse(Path('/proc/' + str(pid)).exists(), 'owned child not reaped')
            events = [dict(parse(line)) for line in (directory / 'events.sexp').read_text().splitlines()]
            self.assertEqual([int(e['sequence']) for e in events], list(range(len(events))))
            self.assertEqual(events[0]['payload'], 'Started')
            self.assertTrue(all(e['payload'][0] != 'Finished' for e in events if isinstance(e['payload'], list)))
            self.assertNotIn('Incomplete', (directory / 'events.sexp').read_text())
            dev.write(directory / 'cancellation.json', dict(exit_code=code, native_child_pids=observed,
                                                           children_reaped=True, accepted_prefix=True))

    def test_08_source_drift_idempotence_locks_refresh_failure(self):
        marker = self.store / 'state/history-sentinel'
        marker.write_bytes(b'old attempt/artifact identity\0')
        preference = self.store / 'client-state/preferences-sentinel'
        preference.write_bytes(b'saved UI selection')
        edited = self.store / 'project/lib/controlled_fifo.ml'
        original = edited.read_bytes()
        edited.write_bytes(original + b'\n(* deliberate editable-development-source test *)\n')
        self.prepare()
        self.assertEqual(json.loads((self.store / 'manifest.json').read_text())['generation'], self.initial['generation'])
        directory, argv = self.request('stale-fifo')
        result, _ = self.execute(directory, argv, expected=2)
        self.assertIn(b'prepare --refresh', result.stderr)
        self.assertEqual((directory / 'events.sexp').read_bytes(), b'')
        renamed = edited.with_suffix('.temporarily-missing')
        edited.rename(renamed)
        try:
            directory, argv = self.request('missing-fifo-source')
            result, _ = self.execute(directory, argv, expected=2)
            self.assertIn(b'prepare --refresh', result.stderr)
        finally:
            renamed.rename(edited)
        # Both actual lifetime locks independently prevent refresh, even without launcher fencing.
        for name in ('state', 'discovery'):
            with (self.store / name / 'lifetime.lock').open('a+b') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.prepare('--refresh', expected=2)
        self.prepare('--refresh', '--dune', '/bin/false', expected=2)
        self.assertEqual(json.loads((self.store / 'manifest.json').read_text()), self.initial)
        self.assertIn(b'deliberate editable', edited.read_bytes())
        self.prepare('--refresh')
        current = json.loads((self.store / 'manifest.json').read_text())
        self.assertNotEqual(current['generation'], self.initial['generation'])
        self.assertEqual(current['project_root'], self.initial['project_root'])
        self.assertEqual(current['inputs']['sdk_prefix'], self.initial['generation'] + '/sdk')
        self.assertEqual(marker.read_bytes(), b'old attempt/artifact identity\0')
        self.assertEqual(preference.read_bytes(), b'saved UI selection')
        dev.verify(self.initial, configs=False)
        dev.verify(current)
        self.assertTrue(Path(self.initial['generation']).is_dir())
        self.assertIn(b'deliberate editable', edited.read_bytes())
        # Previously published VCD/JSON and full result closure survive refresh byte-exact.
        positive = self.evidence / 'pt8-positive-both/artifacts'
        references = list(positive.glob('*-result-reference.json'))
        self.assertEqual(len(references), 2)
        for reference_file in references:
            reference = json.loads(reference_file.read_text())
            inspected = subprocess.run([current['inputs']['asic_generation'] + '/bin/hardcaml-asic-flow',
                'workload-inspect', reference['result'], '--json'], capture_output=True, check=True, timeout=30)
            self.assertEqual(json.loads(inspected.stdout)['source_digest'], reference['source_digest'])
        # New selection uses the edited source capture and has the same report contract.
        directory, argv = self.request('refreshed-fifo', command=current['provider_command'])
        _, events = self.execute(directory, argv)
        self.assertEqual(events[-1]['payload'], ['Finished', 'Passed'])
        self.prepare()
        self.assertEqual(json.loads((self.store / 'manifest.json').read_text()), current)
        # Configs are admitted regular files, with exact selected-manifest hashes.
        for name, digest in current['config_files'].items():
            path = self.store / 'project' / name
            self.assertFalse(path.is_symlink())
            self.assertEqual(router.sha(path), digest)
        path = self.store / 'project/hardcaml-workbench-simulation.sexp'
        owned = path.read_bytes()
        dev.replace_regular(path, owned + b'\n; user-edited configuration\n')
        edited_bytes = path.read_bytes()
        self.prepare('--refresh', expected=2)
        self.assertEqual(path.read_bytes(), edited_bytes)
        self.assertEqual(json.loads((self.store / 'manifest.json').read_text()), current)
        dev.replace_regular(path, owned)

        # Inject failure/process death BETWEEN regular-config replacements. These
        # deliberately minimal test generations are never used as runtime apps.
        def candidate():
            generation = self.store / 'generations' / uuid.uuid4().hex
            (generation / 'config').mkdir(parents=True)
            for name in current['config_files']:
                data = (Path(current['generation']) / 'config' / name).read_bytes()
                if name == dev.config_name('simulation'):
                    data = data.replace(b'"600"', b'"601"')
                (generation / 'config' / name).write_bytes(data)
            manifest = dict(current, generation=str(generation), generation_id=generation.name,
                            config_files={name: router.sha(generation / 'config' / name) for name in current['config_files']},
                            captured_files=dev.tree_hashes(generation))
            dev.write(generation / 'manifest.json', manifest)
            receipt = self.store / 'receipts' / generation.name
            receipt.mkdir()
            return manifest, receipt
        replace = dev.replace_regular
        class Crash(BaseException):
            pass
        for failure in (RuntimeError, Crash):
            candidate_manifest, receipt = candidate()
            calls = 0
            def interrupted(path, data):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise failure('injected after first config replacement')
                return replace(path, data)
            with dev.locked(self.store / 'prepare.lock'), dev.locked(self.store / 'state/lifetime.lock'), \
                 dev.locked(self.store / 'discovery/lifetime.lock'):
                with patch.object(dev, 'replace_regular', side_effect=interrupted):
                    with self.assertRaises(failure):
                        dev.publish(self.store, current, candidate_manifest, receipt)
            if failure is Crash:
                self.assertTrue((self.store / 'publication.json').exists())
                with self.assertRaisesRegex(RuntimeError, 'prepare --refresh'):
                    dev.selected_manifest(self.store)
                # Unknown concurrent config edits are never overwritten by recovery.
                path = self.store / 'project/hardcaml-workbench-simulation.sexp'
                partial = path.read_bytes()
                dev.replace_regular(path, partial + b'\n; edited after interruption\n')
                changed = path.read_bytes()
                self.prepare('--refresh', expected=2)
                self.assertEqual(path.read_bytes(), changed)
                self.assertTrue((self.store / 'publication.json').exists())
                dev.replace_regular(path, partial)
                # Explicit refresh first rolls back, then this intentional build
                # failure proves the original selection/configs were recovered.
                self.prepare('--refresh', '--dune', '/bin/false', expected=2)
            self.assertFalse((self.store / 'publication.json').exists())
            self.assertEqual(dev.selected_manifest(self.store), current)
            dev.verify(current)
        dev.write(self.evidence / 'refresh.json', dict(old_generation=self.initial['generation'],
                  new_generation=current['generation'], edited_source_preserved=True, history_preferences_preserved=True,
                  regular_config_hashes=current['config_files'], publication_rollback=True,
                  crash_requires_explicit_recovery=True, edited_configs_not_overwritten=True))

    def test_09_normal_asic_source_plan_build_emission(self):
        manifest = json.loads((self.store / 'manifest.json').read_text())
        project = Path(manifest['project_root'])
        env = router.environment(manifest)
        directory = self.evidence / 'standard-source-flow'
        directory.mkdir()
        def command(label, argv):
            result = subprocess.run(argv, cwd=project, env=env, capture_output=True, timeout=600)
            (directory / (label + '.stdout')).write_bytes(result.stdout)
            (directory / (label + '.stderr')).write_bytes(result.stderr)
            dev.write(directory / (label + '.command.json'), dict(argv=list(map(str, argv)),
                       exit_code=result.returncode, max_jobs=2, eda_allocation=0))
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return result.stdout
        options = ['--flow', 'standard', '--profile', 'balanced', '--endpoint', 'synthesis',
                   '--source-root', str(project), '--json']
        driver = manifest['generation'] + '/provider/project.exe'
        planned = json.loads(command('captured-plan', [driver, 'flow', 'plan', *options]))
        # Exercise exactly the private _build/default location stock Preparation executes.
        command('source-build', ['dune', 'build', '--root', str(project), '-j2', '--', 'bin/project.exe'])
        command('ordinary-tests', ['dune', 'runtest', '--root', str(project), '-j2', 'test', 'asic_test', 'timing'])
        driver = str(project / '_build/default/bin/project.exe')
        fresh = json.loads(command('source-plan', [driver, 'flow', 'plan', *options]))
        self.assertEqual(fresh['plan_identity'], planned['plan_identity'])
        emitted = json.loads(command('source-emit', [driver, 'flow', 'emit', *options,
                                  '--results-root', str(directory / 'emitted')]))
        bundle = Path(emitted['output_dir'])
        self.assertTrue(bundle.is_relative_to(self.store))
        bundle_manifest = json.loads((bundle / 'manifest.json').read_text())
        self.assertTrue(bundle_manifest['source_inputs'])
        # Actual bundle inputs must be the edited prepared files, not owner checkout bytes.
        copied = bundle / 'inputs/lib/controlled_fifo.ml'
        self.assertEqual(copied.read_bytes(), (project / 'lib/controlled_fifo.ml').read_bytes())
        self.assertIn(b'deliberate editable', copied.read_bytes())
        self.assertNotEqual(copied.read_bytes(), (ROOT / 'lib/controlled_fifo.ml').read_bytes())

    def test_10_launcher_foreground_lock_and_explicit_connection(self):
        directory = self.evidence / 'launcher'
        directory.mkdir()
        prefix = [sys.executable, '-B', str(ROOT / 'scripts/workbench_dev.py'), '--store', str(self.store)]
        with (directory / 'daemon.stdout').open('wb') as out, (directory / 'daemon.stderr').open('wb') as err:
            process = subprocess.Popen(prefix + ['daemon'], stdout=out, stderr=err, start_new_session=True)
            try:
                deadline = time.monotonic() + 30
                metadata = self.store / 'discovery/daemon.sexp'
                while not metadata.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertIsNone(process.poll(), (directory / 'daemon.stderr').read_text())
                self.assertTrue(metadata.exists())
                self.prepare()  # idempotent verification is allowed with an active daemon
                self.prepare('--refresh', expected=2)
                client = subprocess.run(prefix + ['client', '--', '--api', '--plain',
                    '--asic-operation', 'Get'], capture_output=True, timeout=60)
                (directory / 'client.stdout').write_bytes(client.stdout)
                (directory / 'client.stderr').write_bytes(client.stderr)
                self.assertEqual(client.returncode, 0, client.stderr.decode())
                self.assertEqual(parse(client.stdout.decode())[0], 'Ok')
                self.assertIn(str(self.store / 'project').encode(), client.stderr)
                metadata_fields = dict(parse(metadata.read_text()))
                http_records = []
                def http(path, payload):
                    request = urllib.request.Request(metadata_fields['endpoint'] + path, data=sexp(payload).encode(),
                        headers={'Content-Type': 'application/sexp', 'X-Workbench-Protocol': '1'})
                    with urllib.request.urlopen(request, timeout=30) as response:
                        body = response.read().decode()
                        value = parse(body)
                    http_records.append(dict(path=path, request=payload, response=value))
                    self.assertEqual(value[0], 'Ok', body)
                    return value[1]
                opened = http('/api/v1/open-project', [('instance_id', metadata_fields['instance_id']),
                    ('root', str(self.store / 'project')), ('environment', 'Inherit_daemon')])
                project_id = dict(dict(opened)['project'])['id']
                def simulation(operation):
                    return dict(http('/api/v1/simulation', [('instance_id', metadata_fields['instance_id']),
                        ('project', project_id), ('operation', operation)]))
                discovered = simulation('Discover')
                deadline = time.monotonic() + 30
                while not discovered['discovery'] and not discovered['discovery_error'] and time.monotonic() < deadline:
                    time.sleep(.05)
                    discovered = simulation('Get')
                self.assertEqual(discovered['discovery_error'], [])
                self.assertTrue(discovered['discovery'], 'native simulation discovery did not finish')
                self.assertEqual([dict(s)['id'] for s in dict(discovered['discovery'][0])['suites']], list(router.SUITES))
                for kind in dev.CONFIGS:
                    self.assertFalse((self.store / 'project' / dev.config_name(kind)).is_symlink())
                dev.write(directory / 'native-discover.json', dict(passed=True, requests=http_records,
                          discovery=discovered, regular_configs=True))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        client = subprocess.run(prefix + ['client'], capture_output=True, timeout=30)
        self.assertEqual(client.returncode, 2)
        self.assertIn(b'start it explicitly', client.stderr)
        self.assertEqual((self.store / 'state/history-sentinel').read_bytes(), b'old attempt/artifact identity\0')

    def test_11_explicit_missing_source_import_preserves_edits_on_failed_build(self):
        current = dev.selected_manifest(self.store)
        project = self.store / 'project'
        removed = self.evidence / 'legacy-omitted-sources'
        removed.mkdir()
        for name in dev.IMPORT_GROUPS:
            (project / name).rename(removed / name)
        before = router.inventory(project, ('lib', 'simulation', 'scripts'))
        self.prepare()  # reports the gap; never silently imports
        self.assertFalse((project / 'test').exists())
        self.prepare('--refresh', expected=2)
        self.assertEqual(dev.selected_manifest(self.store), current)
        self.prepare('--refresh', '--import-missing-source', '--dune', '/bin/false', expected=2)
        self.assertEqual(dev.selected_manifest(self.store), current)
        self.assertEqual(router.inventory(project, ('lib', 'simulation', 'scripts')), before)
        for name, roots in dev.IMPORT_GROUPS.items():
            self.assertEqual(router.inventory(project, roots), router.inventory(ROOT, roots))
        # Only authored acceptance harness files, not retained snapshots/results.
        self.assertEqual(set(p.name for p in (project / 'acceptance').iterdir()),
                         {Path(name).name for name in router.ACCEPTANCE_FILES})
        edited_test = project / 'test/fifo_test.ml'
        edited_test.write_bytes(edited_test.read_bytes() + b'\n(* user test-source edit, retained on repeat import *)\n')
        test_digest = router.sha(edited_test)
        # Explicit support update must refuse a user edit against the baseline.
        router_path = project / 'simulation/workbench_provider.py'
        router_before = router_path.read_bytes()
        router_path.write_bytes(router_before + b'\n# user-owned router edit\n')
        user_router = router_path.read_bytes()
        self.prepare('--refresh', '--import-missing-source', '--update-owned-support', expected=2)
        self.assertEqual(router_path.read_bytes(), user_router)
        self.assertEqual(dev.selected_manifest(self.store), current)
        router_path.write_bytes(router_before)
        # Legacy captures lack this new helper: only explicit owned-support
        # migration adds it, and the old immutable helper/source stays intact.
        helper = project / 'scripts/workbench_git.py'
        helper.rename(removed / 'workbench_git.py')
        self.prepare('--refresh', expected=2)
        self.assertFalse(helper.exists())
        self.prepare('--refresh', '--import-missing-source', '--update-owned-support')
        final = dev.selected_manifest(self.store)
        self.assertNotEqual(final['generation'], current['generation'])
        self.assertEqual(final['source_owner_root'], str(ROOT))
        self.assertEqual(final['source_dirs'], list(router.SOURCE_DIRS))
        self.assertEqual(router.sha(edited_test), test_digest)
        self.assertEqual(router.sha(Path(final['generation']) / 'source/test/fifo_test.ml'), test_digest)
        self.assertEqual(router.sha(Path(final['generation']) / 'provider/simulation/workbench_provider.py'), router.sha(router_path))
        self.prepare()
        self.assertEqual(dev.selected_manifest(self.store), final)
        self.assertEqual((self.store / 'state/history-sentinel').read_bytes(), b'old attempt/artifact identity\0')
        dev.write(self.evidence / 'source-import.json', dict(passed=True, generation=final['generation'],
                  default_dirs=list(router.SOURCE_DIRS), source_owner_root=final['source_owner_root'],
                  source_edit_preserved=True, additions_retained_after_failed_build=True,
                  arbitrary_support_edit_refused=True, no_acceptance_snapshots=True))

    def test_12_migration_atomic_noreplace_and_baseline_support_updates(self):
        directory = self.evidence / 'migration-races'
        directory.mkdir()
        store = directory / 'store'
        project = store / 'project'
        project.mkdir(parents=True)
        owner = directory / 'owner'
        owner.mkdir()
        for name, roots in dev.IMPORT_GROUPS.items():
            if name == 'test':
                (owner / 'test').mkdir()
                (owner / 'test/owned.ml').write_text('let owned = true\n')
            elif name == 'bootstrap.sh':
                (project / name).write_text('existing user file\n')
            else:
                (project / name).mkdir()
        prior = dict(source_owner_root=str(owner), inputs={'git_dir': str(owner / '.git')}, source_files={})
        args = SimpleNamespace(root=ROOT, import_missing_source=True, update_owned_support=False)
        rename = dev.rename_new
        for race in ('empty-directory', 'symlink'):
            receipt = directory / race
            receipt.mkdir()
            def collide(source, target):
                if target == project / 'test':
                    if race == 'empty-directory':
                        target.mkdir()
                    else:
                        target.symlink_to(owner / 'test', target_is_directory=True)
                return rename(source, target)
            with patch.object(dev, 'rename_new', side_effect=collide):
                with self.assertRaises(FileExistsError):
                    dev.migrate_sources(args, store, prior, receipt)
            self.assertTrue((receipt / 'source-stage/test/owned.ml').is_file())
            self.assertTrue((receipt / 'source-migration-intent.json').exists())
            self.assertEqual(json.loads((receipt / 'source-migration-result.json').read_text())['installed'], [])
            if race == 'empty-directory':
                self.assertEqual(list((project / 'test').iterdir()), [])
                (project / 'test').rmdir()
            else:
                self.assertTrue((project / 'test').is_symlink())
                (project / 'test').unlink()
        args.import_missing_source = False
        args.update_owned_support = True
        for name in dev.OWNED_SUPPORT:
            source, path = owner / name, project / name
            source.parent.mkdir(parents=True, exist_ok=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('# new owned support\n')
            path.write_text('# old recorded support\n')
            prior['source_files'][name] = router.sha(path)
        receipt = directory / 'owned-update'
        receipt.mkdir()
        result = dev.migrate_sources(args, store, prior, receipt)
        self.assertEqual(set(result['installed']), set(dev.OWNED_SUPPORT))
        for name in dev.OWNED_SUPPORT:
            self.assertEqual((project / name).read_bytes(), (owner / name).read_bytes())
            self.assertEqual(router.sha(receipt / 'source-backup' / name), prior['source_files'][name])
        self.assertEqual((project / 'bootstrap.sh').read_text(), 'existing user file\n')
        simulation = project / 'simulation'
        simulation.rename(project / 'simulation-saved')
        simulation.symlink_to(owner / 'simulation', target_is_directory=True)
        receipt = directory / 'symlink-support-parent'
        receipt.mkdir()
        owner_before = router.sha(owner / 'simulation/workbench_provider.py')
        with self.assertRaisesRegex(RuntimeError, 'parent contains a symlink'):
            dev.migrate_sources(args, store, prior, receipt)
        self.assertEqual(router.sha(owner / 'simulation/workbench_provider.py'), owner_before)

    def test_13_scoped_git_real_repositories_and_inherited_selectors(self):
        current = dev.selected_manifest(self.store)
        self.assertIsNone(dev.git_context_diagnostic(current))
        self.assertFalse(set(current['environment']) & scoped_git.REPOSITORY_ENV)
        context = current['git_context']
        real = context['real_git']
        command = str(Path(current['generation']) / 'tool-bin/git')
        directory = self.evidence / 'scoped-git'
        directory.mkdir()
        fixture = directory / 'collateral-repo'
        fixture_revision = git_fixture(fixture, 'independent fixture collateral\n')
        type(self).fixture_git_root = fixture
        bad = dict(os.environ, GIT_DIR=current['inputs']['git_dir'], GIT_WORK_TREE=current['project_root'],
                   GIT_INDEX_FILE='/nonexistent/poison-index', GIT_OBJECT_DIRECTORY='/nonexistent/poison-objects',
                   GIT_COMMON_DIR='/nonexistent/poison-common', GIT_CONFIG_COUNT='1',
                   GIT_CONFIG_KEY_0='core.worktree', GIT_CONFIG_VALUE_0='/nonexistent/poison-tree',
                   CUSTOM_CONTEXT_MARKER='preserved', GIT_AUTHOR_NAME='preserved-author')
        clean = scoped_git.clean_environment(bad)
        self.assertEqual(clean['CUSTOM_CONTEXT_MARKER'], 'preserved')
        self.assertEqual(clean['GIT_AUTHOR_NAME'], 'preserved-author')
        with patch.dict(os.environ, bad, clear=True):
            generated = router.environment(current)
        self.assertFalse(set(generated) & scoped_git.REPOSITORY_ENV)
        self.assertNotIn('GIT_CONFIG_KEY_0', generated)
        self.assertEqual(generated['CUSTOM_CONTEXT_MARKER'], 'preserved')
        records = []
        def invoke(argv, cwd=directory, expected_env=None):
            observed = subprocess.run([command, *argv], cwd=cwd, env=bad, capture_output=True, timeout=30)
            wanted = subprocess.run([real, *argv], cwd=cwd, env=expected_env or clean, capture_output=True, timeout=30)
            records.append(dict(argv=argv, cwd=str(cwd), code=observed.returncode,
                                stdout=observed.stdout.decode(), stderr=observed.stderr.decode()))
            self.assertEqual((observed.returncode, observed.stdout, observed.stderr),
                             (wanted.returncode, wanted.stdout, wanted.stderr))
            return observed
        # Real independent repo and clean tracked-file status (including index checksum).
        before = dev.tree_hashes(fixture / '.git')
        self.assertEqual(invoke(['-C', str(fixture), 'rev-parse', 'HEAD']).stdout.decode().strip(), fixture_revision)
        status = invoke(['-C', str(directory), '-C', 'collateral-repo', 'status', '--porcelain', '--', 'tracked.txt'])
        self.assertEqual(status.returncode, 0)
        self.assertEqual(status.stdout, b'')
        self.assertEqual(invoke(['-Ccollateral-repo', 'rev-parse', 'HEAD']).returncode, 129)
        self.assertEqual(invoke(['-C', str(fixture), 'rev-parse', '--verify', 'missing-ref']).returncode, 128)
        self.assertEqual(before, dev.tree_hashes(fixture / '.git'))
        # Each exact source root gets its own real working tree and recorded metadata.
        source_index = Path(current['inputs']['git_dir']) / 'index'
        source_index_before = router.sha(source_index)
        for root in context['source_roots']:
            source_env = dict(clean, GIT_DIR=current['inputs']['git_dir'], GIT_WORK_TREE=root)
            self.assertEqual(invoke(['rev-parse', 'HEAD'], cwd=Path(root), expected_env=source_env).returncode, 0)
            invoke(['-C', root, '-C', '', 'status', '--porcelain', '--', 'lib/controlled_fifo.ml'], expected_env=source_env)
        self.assertEqual(router.sha(source_index), source_index_before)
        # Descendants/other temporary roots are not prefix-matched into source context.
        invoke(['-C', current['project_root'], '-C', 'lib', 'rev-parse', 'HEAD'])
        invoke(['--no-pager', '-C', current['project_root'], '-C', str(fixture), 'rev-parse', '--git-dir'])
        invoke(['--version'])
        for override in (['--git-dir', current['inputs']['git_dir']], ['--work-tree=/tmp'],
                         ['-c', 'core.worktree=/tmp'], ['--bare'], ['--namespace=unknown']):
            result = subprocess.run([command, *override, 'rev-parse', 'HEAD'], env=bad, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b'')
        tools = Path(current['inputs']['toolchain'])
        actual = {}
        for label, repo, expected in (
            ('support', tools / 'tt', 'd66cf179e7bc4d296362ab7e2e3b344dc3c4f665'),
            ('pdk', tools / 'pdk', '2bbec755dc67ca3db0261c3d6163e15735d66710'),
        ):
            index = repo / '.git/index'
            before = router.sha(index)
            revision = invoke(['-C', str(repo), 'rev-parse', 'HEAD']).stdout.decode().strip()
            self.assertEqual(revision, expected)
            self.assertNotEqual(revision, fixture_revision)  # wrong expected revision still fails equality
            status = invoke(['-C', str(repo), 'status', '--porcelain', '--', 'README.md'])
            self.assertEqual(status.returncode, 0)
            self.assertEqual(status.stdout, b'')
            self.assertEqual(router.sha(index), before)
            actual[label] = revision
        unsafe = dict(current, environment=dict(current['environment'], GIT_DIR=current['inputs']['git_dir'],
                                                GIT_WORK_TREE=current['project_root']))
        self.assertIn('prepare --refresh --update-owned-support', dev.git_context_diagnostic(unsafe))
        dev.write(directory / 'receipt.json', dict(passed=True, fixture_revision=fixture_revision, actual=actual,
                  real_git=real, real_git_sha256=context['real_git_sha256'], commands=records,
                  real_stdout_status_preserved=True, git_indexes_unchanged=True, global_selectors_absent=True))

    def test_14_installed_preflight_real_collateral_and_wrong_revision(self):
        current = dev.selected_manifest(self.store)
        project = Path(current['project_root'])
        directory = self.evidence / 'installed-git-preflight'
        directory.mkdir()
        env = router.environment(current)
        # A fresh source-only bundle; no physical stage/EDA command exists here.
        emitted = subprocess.run([current['generation'] + '/provider/project.exe', 'flow', 'emit',
            '--flow', 'standard', '--profile', 'balanced', '--endpoint', 'synthesis',
            '--source-root', str(project), '--results-root', str(directory / 'bundles'), '--json'],
            cwd=project, env=env, capture_output=True, timeout=90, check=True)
        (directory / 'emitted.json').write_bytes(emitted.stdout)
        bundle = json.loads(emitted.stdout)['output_dir']
        tools = Path(current['inputs']['toolchain'])
        reports = {}
        for label, support in (('actual', tools / 'tt'), ('wrong-revision', self.fixture_git_root)):
            output = directory / (label + '.json')
            argv = [current['inputs']['asic_generation'] + '/bin/hardcaml-asic-flow', 'preflight', bundle,
                    '--support-tools', str(support), '--pdk-root', str(tools / 'pdk'),
                    '--python', str(tools / '.venv/bin/python'), '--results-root', str(directory / 'results'),
                    '--output', str(output), '--native', '--json']
            result = subprocess.run(argv, cwd=project, env=env, capture_output=True, timeout=90)
            (directory / (label + '.stdout')).write_bytes(result.stdout)
            (directory / (label + '.stderr')).write_bytes(result.stderr)
            dev.write(directory / (label + '.command.json'), dict(argv=argv, exit_code=result.returncode,
                        metadata_only=True, container_probes=0, eda_allocation=0))
            self.assertTrue(output.exists(), result.stderr.decode())
            report = json.loads(output.read_text())
            issues = report['issues']
            self.assertFalse(any('PDK revision ' in issue for issue in issues), issues)
            if label == 'actual':
                self.assertEqual(result.returncode, 0, issues)
                self.assertTrue(report['ready'])
                self.assertEqual(issues, [])
                self.assertFalse(any('support tools revision ' in issue for issue in issues), issues)
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(any('support tools revision ' in issue and '; requested ' in issue for issue in issues), issues)
                self.assertFalse(report['ready'])
            reports[label] = dict(exit_code=result.returncode, issues=issues)
        dev.write(directory / 'receipt.json', dict(passed=True, reports=reports,
                  actual_revisions_accepted=True, real_wrong_revision_rejected=True,
                  native_metadata_only=True, eda_allocation=0))


def main():
    global STORE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, help='new independent test store (must not exist)')
    args = parser.parse_args()
    STORE = args.store.absolute() if args.store else Path(tempfile.mkdtemp(prefix='workbench-dev-b-', dir='/tmp/opencode')) / 'store'
    if STORE.exists():
        parser.error('test store must not exist')
    STORE.mkdir(parents=True)
    print('Evidence: ' + str(STORE / 'test-evidence'), flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    dev.write(STORE / 'test-evidence/result.json', dict(passed=result.wasSuccessful(), tests_run=result.testsRun,
              failures=[(str(test), failure) for test, failure in result.failures + result.errors],
              store=str(STORE), max_jobs=2, eda_allocation=0))
    return int(not result.wasSuccessful())


if __name__ == '__main__':
    sys.exit(main())
