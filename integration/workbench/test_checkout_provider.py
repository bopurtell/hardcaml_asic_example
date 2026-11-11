"""Controlled checkout adapter tests; no Dune builds, EDA, or owner operations."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import checkout_provider as checkout
from checkout_setup import prepare_simulation
import workbench_provider as router
from wire import parse, record, sexp

ROOT = Path(__file__).resolve().parents[2]
FIFO_CATALOG = [('protocol_version', 1), ('suites', [[
    ('id', 'controlled-fifo'), ('label', 'Controlled FIFO / independent list checker'),
    ('cases', [[('id', case), ('label', 'FIFO ' + case)] for case in ('directed', 'seeded')]),
    ('parameters', []), ('default_seed', 42)]])]


class CheckoutProvider(unittest.TestCase):
    def setUp(self):
        base = ROOT / '.dev/workbench-main-verification'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='adapter-test-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'checkout'
        self.root.mkdir()
        # A synthetic authored closure: only imports needed by actual discovery
        # use real helper bytes. No copied project/store or real compiler runs.
        names = set()
        for paths in checkout.SOURCE_PATHS.values():
            for name in paths:
                source = ROOT / name
                if source.is_dir():
                    destination = self.root / name
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / 'fixture.ml').write_text('fixture source\n')
                else:
                    names.add(name)
        names.update(('integration/workbench/pt8_workbench_provider.py',
                      'integration/workbench/pt8_workbench_runner.py',
                      'integration/workbench/workbench_paths.py',
                      'tooling_acceptance/workloads/controls/pt8_workloads.py',
                      'tooling_acceptance/variants/controls/pt8_acceptance.py'))
        for name in names:
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes())
        self.build = self.root / '_build_checkout'
        self.generation = self.directory / 'asic'
        (self.generation / 'lib').mkdir(parents=True)
        (self.generation / 'lib/library.a').write_text('compiled ASIC library')
        (self.generation / 'bin').mkdir()
        self.executable(self.generation / 'bin/hardcaml-asic-flow', 'pass\n')
        self.models = self.directory / 'models'
        self.models.mkdir()
        for name in checkout.MODELS:
            (self.models / name).write_text('module model; endmodule\n')
        self.calls = []
        self.options = dict(project_root=self.root, build_dir=self.build,
                            asic_generation=self.generation, model_root=self.models,
                            run=self.build_fake, environment={'PATH': os.defpath})

    def executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!' + sys.executable + '\n' + body)
        path.chmod(0o755)

    def build_fake(self, argv, *, cwd, env):
        self.calls.append((argv, cwd, env))
        for target in checkout.TARGETS:
            self.executable(self.build / 'default' / target, 'pass\n')
        self.executable(self.build / 'default' / checkout.TARGETS[0],
            'import json, os, pathlib, sys, time\n'
            f'catalog = {sexp(FIFO_CATALOG)!r}\n'
            'if "discover" in sys.argv:\n'
            '    print(catalog)\n'
            'else:\n'
            '    request = pathlib.Path(sys.argv[sys.argv.index("--request") + 1])\n'
            '    request.with_suffix(".argv.json").write_text(json.dumps(sys.argv[1:]))\n'
            '    request.with_suffix(".env.json").write_text(json.dumps(dict(os.environ)))\n'
            '    if request.name.startswith("cancel"):\n'
            '        time.sleep(30)\n'
            '    else:\n'
            '        events = pathlib.Path(sys.argv[sys.argv.index("--events") + 1])\n'
            '        events.write_text("child events unchanged\\n")\n')

    def prepare(self):
        self.manifest = prepare_simulation(**self.options)
        self.manifest_path = Path(self.manifest['manifest_path'])
        return self.manifest

    def invoke(self, *args):
        return subprocess.run(self.manifest['provider_command'] + list(args),
                              capture_output=True, text=True, timeout=10)

    def request(self, name='request', suite='controlled-fifo'):
        request = self.directory / (name + '.sexp')
        request.write_text(sexp([('protocol_version', 1), ('attempt_id', 'test'),
            ('selection', [('suite', suite),
                           ('cases', ['directed'] if suite == 'controlled-fifo' else ['flops256']),
                           ('seed', 42 if suite == 'controlled-fifo' else 34097),
                           ('parameters', []), ('asic_inputs', [])])]))
        return request

    def run_args(self, request):
        return ['run', '--protocol-version', '1', '--request', str(request),
                '--events', str(self.directory / 'events'),
                '--artifact-dir', str(self.directory / 'artifacts')]

    def test_prepare_and_real_composite_discovery(self):
        manifest = self.prepare()
        argv, cwd, env = self.calls[0]
        self.assertEqual(argv[-len(checkout.TARGETS):], list(checkout.TARGETS))
        self.assertEqual(argv[argv.index('-j') + 1], '2')
        self.assertEqual(cwd, self.root)
        self.assertEqual(env['HARDCAML_ASIC_GENERATION'], str(self.generation))
        self.assertEqual(manifest['project_root'], str(self.root))
        self.assertEqual(self.manifest_path, self.root / '.dev/workbench-main/simulation/manifest.json')
        self.assertEqual(json.loads(self.manifest_path.read_text()), manifest)
        self.assertIn('--output-root', manifest['provider_commands']['pt8-memory-workloads'])
        self.assertNotIn('/tmp', json.dumps(manifest))
        result = self.invoke('discover', '--protocol-version', '1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        suites = record(parse(result.stdout), ('protocol_version', 'suites'))['suites']
        fields = [dict(suite) for suite in suites]
        self.assertEqual([suite['id'] for suite in fields], list(router.SUITES))
        self.assertEqual([[dict(case)['id'] for case in suite['cases']] for suite in fields],
                         [['directed', 'seeded'], ['flops256', 'exact256']])
        for suite in router.SUITES:
            self.assertEqual(checkout.drift(manifest, suite), [])

    def test_exec_preserves_child_argv_and_output(self):
        self.prepare()
        request = self.request()
        args = self.run_args(request)
        result = self.invoke(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(json.loads(request.with_suffix('.argv.json').read_text()),
                         self.manifest['provider_commands']['controlled-fifo'][1:] + args)
        self.assertEqual((self.directory / 'events').read_text(), 'child events unchanged\n')

    def test_supplied_complete_environment_preserves_absence_in_build_and_run(self):
        ambient = {'HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT': '6',
                   'PT8_PROJECT_ROOT': '/obsolete/project', 'PT8_REAL_DUNE': '/obsolete/dune',
                   'HARDCAML_WORKBENCH_DISCOVERY_DIR': '/obsolete/discovery',
                   'CHECKOUT_AMBIENT_ONLY': 'must not return', 'GIT_DIR': '/obsolete/git'}
        supplied = {'PATH': os.defpath, 'CHECKOUT_SELECTED': 'retained'}
        with patch.dict(os.environ, ambient):
            self.options['environment'] = supplied
            manifest = self.prepare()
            env = self.calls[0][2]
            self.assertEqual(supplied, {'PATH': os.defpath, 'CHECKOUT_SELECTED': 'retained'})
            for removed in ambient:
                self.assertNotIn(removed, env)
                self.assertNotIn(removed, manifest['environment'])
                self.assertNotIn(removed, checkout.environment(manifest))
            request = self.request()
            result = self.invoke(*self.run_args(request))
            self.assertEqual(result.returncode, 0, result.stderr)
            runtime = json.loads(request.with_suffix('.env.json').read_text())
            for removed in ambient:
                self.assertNotIn(removed, runtime)
            self.assertEqual(runtime['CHECKOUT_SELECTED'], 'retained')

    def test_empty_environment_is_complete_and_default_environment_is_cleaned(self):
        ambient = {'HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT': '6',
                   'PT8_VENDOR_MODEL_ROOT': '/obsolete/models',
                   'HARDCAML_WORKBENCH_SESSION': 'obsolete', 'CHECKOUT_AMBIENT_ONLY': 'ambient'}
        with patch.dict(os.environ, ambient):
            self.options['environment'] = {}
            self.prepare()
            for name in ambient:
                self.assertNotIn(name, self.calls[-1][2])
            self.options['environment'] = None
            self.prepare()
            env = self.calls[-1][2]
            self.assertEqual(env['CHECKOUT_AMBIENT_ONLY'], 'ambient')
            for name in ambient.keys() - {'CHECKOUT_AMBIENT_ONLY'}:
                self.assertNotIn(name, env)

    def test_launcher_simulation_dir_and_bounded_runner_signature(self):
        state = self.directory / 'launcher-state/simulation'
        manifest = prepare_simulation(**dict(self.options, simulation_dir=state))
        self.assertEqual(manifest['manifest_path'], str(state / 'manifest.json'))
        command = manifest['provider_commands']['pt8-memory-workloads']
        self.assertEqual(command[command.index('--output-root') + 1], str(state / 'workloads'))
        self.assertEqual(checkout.PREPARE, 'python scripts/workbench_main.py build')

    def test_reject_source_add_edit_delete_and_target_drift(self):
        self.prepare()
        for path in (self.root / 'ip/controlled_fifo/rtl/new.ml',
                     self.root / 'ip/controlled_fifo/rtl/fixture.ml',
                     Path(self.manifest['provider_commands']['controlled-fifo'][0]),
                     self.root / 'dune-workspace'):
            original = path.read_bytes() if path.exists() else None
            path.write_bytes(b'changed\n')
            result = self.invoke('discover', '--protocol-version', '1')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn(checkout.PREPARE, result.stderr)
            result = self.invoke(*self.run_args(self.request()))
            self.assertEqual(result.returncode, 2)
            self.assertIn(checkout.PREPARE, result.stderr)
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)
        path = self.root / 'ip/controlled_fifo/rtl/fixture.ml'
        path.unlink()
        self.assertTrue(checkout.drift(self.manifest, 'controlled-fifo'))

    def test_pt8_dependency_model_and_transitive_source_coverage(self):
        self.prepare()
        paths = (self.generation / 'lib/library.a',
                 self.generation / 'bin/hardcaml-asic-flow',
                 self.models / checkout.MODELS[0],
                 self.root / 'asics/fifo_demo/project/fixture.ml',
                 self.root / 'tooling_acceptance/variants/controls/pt8_acceptance.py',
                 self.build / 'default' / checkout.TARGETS[2])
        for path in paths:
            original = path.read_bytes()
            path.write_bytes(original + b'changed\n')
            self.assertTrue(checkout.drift(self.manifest, 'pt8-memory-workloads'), str(path))
            self.assertEqual(checkout.drift(self.manifest, 'controlled-fifo'), [], str(path))
            path.write_bytes(original)

    def test_failure_or_racing_sources_never_refresh_manifest(self):
        self.prepare()
        old = self.manifest_path.read_bytes()
        def failed(*args, **kwargs):
            return subprocess.CompletedProcess([], 1)
        with self.assertRaisesRegex(RuntimeError, 'build failed'):
            prepare_simulation(**dict(self.options, run=failed))
        self.assertEqual(self.manifest_path.read_bytes(), old)
        def race(*args, **kwargs):
            self.build_fake(*args, **kwargs)
            (self.root / 'ip/controlled_fifo/rtl/fixture.ml').write_text('raced')
        with self.assertRaisesRegex(RuntimeError, 'inputs changed during build'):
            prepare_simulation(**dict(self.options, run=race))
        self.assertEqual(self.manifest_path.read_bytes(), old)
        self.assertTrue(checkout.drift(self.manifest, 'controlled-fifo'))
        self.prepare()
        self.assertEqual(checkout.drift(self.manifest, 'controlled-fifo'), [])

    def test_pt8_runner_executes_selected_binaries_in_explicit_persistent_root(self):
        import pt8_workbench_runner as runner
        import pt8_workloads as producer
        self.prepare()
        emitter = self.build / 'default' / checkout.TARGETS[2]
        inspector = self.generation / 'bin/hardcaml-asic-flow'
        self.executable(emitter, 'print("{}")\n')
        self.executable(inspector,
            'print(\'{"outcome":{"functional":"pass"},"source_digest":"fixture"}\')\n')
        output_root = self.directory / 'persistent-workloads'
        def simulate(output, policy, emitted, workload, *, capture_waveform):
            self.assertTrue(capture_waveform)
            (output / policy).mkdir()
            (output / policy / 'result.json').write_text('{}')
        # Keep this test in-process without leaking the historical producer's
        # global command/signal/environment seams into other tests.
        with patch.object(producer, 'simulate', simulate), \
             patch.object(producer, 'command'), \
             patch.object(runner, 'ROOT', runner.ROOT), \
             patch.object(runner, 'STORE', runner.STORE), \
             patch.dict(os.environ):
            for case in ('flops256', 'exact256'):
                output, reference, passed = runner.Runner(self.generation, emitter,
                    self.models, root=self.root, output_root=output_root).run(case, '34097', 'test')
                self.assertTrue(passed)
                self.assertEqual(output.parent, output_root)
                self.assertEqual(reference['source_digest'], 'fixture')
                emit = json.loads((output / 'emit/command.json').read_text())
                inspect = json.loads((output / 'inspect/command.json').read_text())
                self.assertEqual(emit['argv'][:2], [str(emitter), str(self.root)])
                self.assertEqual(inspect['argv'][0], str(inspector))
                self.assertEqual(inspect['exit_code'], 0)
        self.assertFalse((self.root / '.dev/asic-pt8-workbench').exists())

    def test_exec_retains_pid_signal_cancellation_without_terminal_events(self):
        self.prepare()
        request = self.request('cancel')
        child = subprocess.Popen(self.manifest['provider_command'] + self.run_args(request),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 8
            while not request.with_suffix('.argv.json').exists():
                if time.monotonic() >= deadline or child.poll() is not None:
                    self.fail('exec child did not start')
                time.sleep(.01)
            child.send_signal(signal.SIGTERM)
            out, err = child.communicate(timeout=5)
            self.assertEqual(child.returncode, -signal.SIGTERM)
            self.assertEqual((out, err), (b'', b''))
            self.assertFalse((self.directory / 'events').exists())
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()

    def test_pt8_cancellation_reaps_emitter_and_keeps_partial_events(self):
        marker = self.directory / 'emitter.pid'
        def build_waiting_emitter(*args, **kwargs):
            self.build_fake(*args, **kwargs)
            self.executable(self.build / 'default' / checkout.TARGETS[2],
                'import os, pathlib, time\n'
                f'pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n'
                'time.sleep(30)\n')
        self.options['run'] = build_waiting_emitter
        self.prepare()
        request = self.request('cancel-pt8', 'pt8-memory-workloads')
        child = subprocess.Popen(self.manifest['provider_command'] + self.run_args(request),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 8
            while not marker.exists():
                if time.monotonic() >= deadline or child.poll() is not None:
                    self.fail('PT8 emitter did not start')
                time.sleep(.01)
            emitter_pid = int(marker.read_text())
            child.send_signal(signal.SIGTERM)
            _, err = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 130, err.decode())
            with self.assertRaises(ProcessLookupError):
                os.kill(emitter_pid, 0)
            events = (self.directory / 'events').read_text()
            self.assertIn('Started', events)
            self.assertIn('Case_started', events)
            self.assertNotIn('Case_finished', events)
            self.assertNotIn('Finished', events)
            outcomes = list((self.manifest_path.parent / 'workloads').glob('*/outcome.json'))
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(json.loads(outcomes[0].read_text())['status'], 'cancelled')
        finally:
            if child.poll() is None:
                child.terminate()
                child.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
