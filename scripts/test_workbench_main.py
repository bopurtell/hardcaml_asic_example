#!/usr/bin/env python3
"""Launcher lifecycle checks with inert files; no native server/build/EDA required."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('workbench_main', HERE / 'workbench_main.py')
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)


class MainTest(unittest.TestCase):
    def setUp(self):
        # All disposable fixture data stays under persistent project-local storage.
        parent = HERE.parent / '.dev'
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='main-launcher-test-', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'checkout'
        self.root.mkdir()
        self.store = main.paths(self.root)
        self.file(self.root / 'dune-project', b'(lang dune 3.22)')
        self.asic = self.root / '.dev/provider'
        self.sdk = self.root / '.dev/sdk'
        (self.sdk / 'lib').mkdir(parents=True)
        self.file(self.asic / 'bin/hardcaml-asic-flow', b'provider', executable=True)
        self.file(self.asic / 'receipt.json', b'{}')
        self.wb = self.root / '.dev/wb-build'
        for owner in ('daemon', 'terminal'):
            self.file(self.wb / 'default' / owner / 'main.exe', owner.encode(), executable=True)
        for target in main.TARGETS:
            self.file(self.root / '_build/default' / target, target.encode(), executable=True)
        self.file(self.root / 'integration/workbench/checkout_provider.py', b'# simulation helper')
        self.manifest = self.store / 'simulation/manifest.json'
        self.file(self.manifest, json.dumps(dict(project_root=str(self.root), asic_generation=str(self.asic))).encode())
        # Router inventory behavior is independently covered by agent2. Keep the
        # launcher fixtures inert while asserting that the readiness fence is used.
        validator_patch = patch('checkout_provider.validate_manifest')
        self.validator = validator_patch.start()
        self.addCleanup(validator_patch.stop)
        self.sim = self.store / 'simulation/configuration.sexp'
        self.file(self.sim, (main.sexp([('schema_version', 1), ('provider_executable', '/usr/bin/python3'),
            ('provider_args', [str(self.root / 'integration/workbench/checkout_provider.py'), '--manifest', str(self.manifest)]),
            ('discovery_timeout_seconds', 30), ('run_timeout_seconds', 600)]) + '\n').encode())
        self.originals = {}
        for kind in main.KINDS:
            data = ('original-' + kind).encode()
            self.file(main.companion(self.root, kind), data)
            self.originals[kind] = data
        self.args = argparse.Namespace(update=False, build=False, asic_generation=self.asic,
            sdk_prefix=self.sdk, wb_build_root=self.wb, simulation_config=self.sim,
            expected_daemon_sha256=None, expected_client_sha256=None)

    def file(self, path, data, executable=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if executable:
            path.chmod(0o755)

    def prepare(self):
        with patch.object(main.subprocess, 'Popen', side_effect=AssertionError('unexpected process')), \
             patch.object(main.subprocess, 'run', side_effect=AssertionError('unexpected build')):
            return main.prepare(self.args, self.root, self.store)

    def publish(self):
        with patch.object(main, 'root_users', return_value=[]):
            return main.publish(self.root, self.store)

    def test_prepare_actual_checkout_no_copy_no_publish_no_process_and_cwd_independent(self):
        cwd = Path.cwd()
        try:
            os.chdir('/')
            value = self.prepare()
        finally:
            os.chdir(cwd)
        self.assertEqual(value['project_root'], str(self.root))
        self.assertFalse((self.store / 'project').exists())
        for kind in main.KINDS:
            self.assertEqual(main.companion(self.root, kind).read_bytes(), self.originals[kind])
        fields = dict(main.parse((Path(value['selection']) / 'config/hardcaml-workbench-asic.sexp').read_text()))
        self.assertEqual(fields['project_executable'], str(self.root / '_build/default' / main.TARGETS[0]))
        self.assertEqual(fields['provider_executable'], str(self.asic / 'bin/hardcaml-asic-flow'))
        self.assertTrue(fields['results_root'].startswith(str(self.root / '_flow_results/workbench')))

    def test_clean_environment_without_captured_caps_or_repository_context(self):
        env = main.environment(self.root, self.store, self.asic, self.sdk, dict(
            PATH='/unrecognized/captured/tool-bin:/another/private/prefix/bin:/usr/bin',
            GIT_DIR='wrong', GIT_WORK_TREE='wrong', GIT_COMMON_DIR='wrong',
            GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='x', GIT_CONFIG_VALUE_0='y',
            PT8_PROJECT_ROOT='copied', HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT='6', OMP_NUM_THREADS='96',
            SSH_AUTH_SOCK='/temporary/agent', TMUX='/temporary/tmux'))
        for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_CONFIG_COUNT',
                     'GIT_CONFIG_KEY_0', 'GIT_CONFIG_VALUE_0', 'PT8_PROJECT_ROOT', 'HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT'):
            self.assertNotIn(name, env)
        self.assertEqual(env['OCAMLPATH'], str(self.asic / 'lib') + ':' + str(self.sdk / 'lib'))
        self.assertEqual(env['OMP_NUM_THREADS'], '1')
        self.assertEqual(env['TMPDIR'], str(self.store / 'tmp'))
        self.assertNotIn('/unrecognized', env['PATH'])
        self.assertNotIn('/another', env['PATH'])
        self.assertNotIn('SSH_AUTH_SOCK', env)
        self.assertNotIn('TMUX', env)
        tools = main.selected_tools(env)
        self.assertEqual(tools['dune'], str((main.SWITCH_BIN / 'dune').resolve()))
        self.assertEqual(tools['git'], str(Path('/usr/bin/git').resolve()))

    def test_publication_exact_backups_and_unknown_edit_guard(self):
        self.prepare()
        result = self.publish()
        for kind in main.KINDS:
            self.assertEqual((Path(result['backup']) / main.companion(self.root, kind).name).read_bytes(), self.originals[kind])
        main.verify_install(self.root, self.store, published=True)
        self.file(main.companion(self.root, 'asic'), b'user edit')
        with self.assertRaisesRegex(RuntimeError, 'unknown root companion edit'):
            self.publish()
        self.assertEqual(main.companion(self.root, 'asic').read_bytes(), b'user edit')

    def test_baseline_edit_before_first_publish_is_not_adopted(self):
        self.prepare()
        self.file(main.companion(self.root, 'simulation'), b'concurrent owner edit')
        with self.assertRaisesRegex(RuntimeError, 'unknown root companion edit'):
            self.publish()

    def test_publication_dry_run_does_not_publish_or_create_backups(self):
        self.prepare()
        with patch.object(main, 'root_users', return_value=[]):
            result = main.publish(self.root, self.store, dry_run=True)
        self.assertTrue(result['ready'])
        self.assertFalse(result['published'])
        self.assertFalse((self.store / 'publications').exists())
        for kind in main.KINDS:
            self.assertEqual(main.companion(self.root, kind).read_bytes(), self.originals[kind])

    def test_rollback_after_partial_publication(self):
        self.prepare()
        original = main.write
        def fail(path, data):
            if path == main.companion(self.root, 'preparation') and data != self.originals['preparation']:
                raise OSError('injected publication failure')
            return original(path, data)
        with patch.object(main, 'write', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'injected publication'):
                self.publish()
        for kind in main.KINDS:
            self.assertEqual(main.companion(self.root, kind).read_bytes(), self.originals[kind])
        self.assertFalse((self.store / 'publication-pending.json').exists())

    def test_active_owner_lock_blocks_updates_and_build(self):
        self.prepare()
        with main.lock(self.store / 'discovery/lifetime.lock'):
            with self.assertRaisesRegex(RuntimeError, 'main daemon owns'):
                self.prepare()
            with self.assertRaisesRegex(RuntimeError, 'main daemon owns'):
                self.publish()

    def test_root_user_blocks_publication_without_touching_companions(self):
        self.prepare()
        with patch.object(main, 'root_users', return_value=['123']):
            with self.assertRaisesRegex(RuntimeError, 'PIDs: 123'):
                main.publish(self.root, self.store)
        for kind in main.KINDS:
            self.assertEqual(main.companion(self.root, kind).read_bytes(), self.originals[kind])

    def test_stale_simulation_blocks_publication(self):
        self.prepare()
        self.validator.side_effect = ValueError('stale source; explicitly rebuild')
        with self.assertRaisesRegex(ValueError, 'stale source'):
            self.publish()
        for kind in main.KINDS:
            self.assertEqual(main.companion(self.root, kind).read_bytes(), self.originals[kind])

    def test_client_never_spawns_daemon_when_not_running(self):
        self.prepare()
        self.publish()
        with patch.object(main.subprocess, 'call', side_effect=AssertionError('unexpected spawn')):
            with self.assertRaisesRegex(RuntimeError, 'not running'):
                main.main(['--root', str(self.root), 'client'])

    def test_repeated_prepare_and_explicit_app_update(self):
        first = self.prepare()
        self.file(self.wb / 'default/daemon/main.exe', b'new reviewed daemon', executable=True)
        self.assertEqual(self.prepare(), first)
        self.args.update = True
        self.args.expected_daemon_sha256 = main.sha(b'wrong')
        with self.assertRaisesRegex(RuntimeError, 'unexpected prebuilt app hash'):
            self.prepare()
        self.assertEqual(main.metadata(self.store), first)
        self.args.expected_daemon_sha256 = main.sha(b'new reviewed daemon')
        second = self.prepare()
        self.assertNotEqual(first['selection'], second['selection'])
        self.assertTrue(Path(first['apps']['daemon']['path']).exists())

    def test_foreign_manifest_and_symlink_config_rejected(self):
        self.file(self.manifest, b'{"project_root":"/some/copied/project"}')
        with self.assertRaisesRegex(RuntimeError, 'actual checkout root'):
            self.prepare()
        target = self.sim.with_name('real.sexp')
        self.sim.rename(target)
        self.sim.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, 'regular file'):
            self.prepare()

    def test_build_explicit_two_jobs_and_no_provider_refresh(self):
        tools = dict(paths=main.selected_tools(main.environment(self.root, self.store, self.asic, self.sdk)))
        with patch('checkout_setup.prepare_simulation') as prepare, patch.object(main, 'verify_tools', return_value=tools):
            main.build(self.root, self.store, self.asic, self.sdk)
        kwargs = prepare.call_args.kwargs
        self.assertEqual(kwargs['project_root'], self.root)
        self.assertEqual(kwargs['build_dir'], self.root / '_build')
        self.assertEqual(kwargs['asic_generation'], self.asic)
        self.assertIs(kwargs['run'], main.bounded_build)
        self.assertNotIn('HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT', kwargs['environment'])
        self.assertEqual(kwargs['dune'], str((main.SWITCH_BIN / 'dune').resolve()))
        self.assertEqual(kwargs['python'], str(Path('/usr/bin/python3').resolve()))

    def test_prepare_generates_config_from_companion_helper_manifest(self):
        self.sim.unlink()
        self.args.simulation_config = None
        command = ['/usr/bin/python3', '-B', str(self.root / 'integration/workbench/checkout_provider.py'),
                   '--manifest', str(self.manifest)]
        self.file(self.manifest, json.dumps(dict(project_root=str(self.root),
                  provider_command=command, asic_generation=str(self.asic))).encode())
        value = self.prepare()
        self.assertEqual(value['simulation_manifest'], str(self.manifest))
        fields = dict(main.parse(self.sim.read_text()))
        self.assertEqual(fields['provider_args'], command[1:])

    def test_daemon_command_uses_available_port_and_normal_persistent_state(self):
        self.prepare()
        self.publish()
        with patch.object(main, 'run_owned', return_value=0) as run, patch.object(main, 'verify_tools'):
            self.assertEqual(main.main(['--root', str(self.root), 'daemon']), 0)
        argv, cwd, env = run.call_args.args
        self.assertEqual(main.option(argv, '--port'), '0')
        self.assertEqual(main.option(argv, '--state-dir'), str(self.store / 'state'))
        self.assertEqual(main.option(argv, '--discovery-dir'), str(self.store / 'discovery'))
        self.assertEqual(cwd, self.root)
        self.assertNotIn('HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT', env)
        for name in ('state', 'discovery', 'tmp'):
            self.assertTrue((self.store / name).is_dir())
            self.assertEqual((self.store / name).stat().st_mode & 0o777, 0o700)

    def test_process_preflight_distinguishes_separate_session_and_root_workspace(self):
        proc = self.root / 'proc'
        proc.mkdir()
        other = self.root / 'separate-checkout'
        other.mkdir()
        state = other / 'state'
        state.mkdir()
        pid = proc / '123'
        pid.mkdir()
        (pid / 'cwd').symlink_to(other, target_is_directory=True)
        self.file(pid / 'cmdline', b'/arbitrary/renamed/app.exe\0--state-dir\0' + os.fsencode(state) + b'\0')
        self.file(pid / 'environ', b'GIT_WORK_TREE=/different/checkout\0')
        self.file(state / 'workspace-scope.sexp', b'((project_key /different/checkout))')
        with main.lock(state / 'lifetime.lock'):
            self.assertEqual(main.root_users(self.root, proc=proc), [])
            self.file(state / 'workspace-scope.sexp', ('((project_key "' + str(self.root) + '"))').encode())
            self.assertEqual(main.root_users(self.root, proc=proc), ['123 (root workspace registry)'])
        self.assertIn('uncertain', main.root_users(self.root, proc=proc)[0])
        self.file(pid / 'cmdline', b'/installed/client.exe\0--project-root\0' + os.fsencode(self.root) + b'\0')
        self.assertEqual(main.root_users(self.root, proc=proc), ['123'])

    def test_subprocess_tool_resolution_is_pinned_even_with_inherited_shims(self):
        env = main.environment(self.root, self.store, self.asic, self.sdk,
                               dict(PATH='/unknown/shims', GIT_DIR='/wrong'))
        result = main.verify_tools(self.root, env)
        self.assertEqual(result['paths']['git'], str(Path('/usr/bin/git').resolve()))
        self.assertGreaterEqual(tuple(map(int, result['versions']['dune'].split('.')[:2])), (3, 22))


if __name__ == '__main__':
    unittest.main()
