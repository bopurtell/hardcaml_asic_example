"""Exercise the normal/prepared simulation setup boundary without real builds."""
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'configure_simulation', Path(__file__).with_name('configure-simulation.py'))
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
validate_manifest = setup.validate_manifest


class ConfigureSimulation(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / 'checkout'
        self.store = self.root / '.dev/workbench-main'
        self.manifest = self.store / 'simulation/manifest.json'
        self.manifest.parent.mkdir(parents=True)
        self.config = self.root / '.silver/silver-simulation.sexp'
        self.config.parent.mkdir()
        self.interpreter = Path(sys.executable).resolve().with_name('python3')
        if not self.interpreter.is_file():
            self.interpreter = Path(sys.executable).resolve()
        self.write_config()
        self.mocks = self.enterContext(patch.multiple(
            setup, ROOT=self.root, prepare_simulation=unittest.mock.DEFAULT,
            validate_manifest=unittest.mock.DEFAULT))
        self.build = self.mocks['prepare_simulation']
        self.enterContext(patch.dict(setup.os.environ, {'PATH': '/usr/bin'}, clear=True))
        self.enterContext(patch.object(setup.subprocess, 'check_output', return_value='/current-switch\n'))

    def write_config(self, script=None):
        fields = [('schema_version', 1), ('provider_executable', str(self.interpreter)),
                  ('provider_args', ['-B', str(script or self.root / 'integration/workbench/checkout_provider.py'),
                                     '--manifest', str(self.manifest)]),
                  ('discovery_timeout_seconds', 45), ('run_timeout_seconds', 900)]
        # Semantic equality of provider args, rather than matching whole file bytes.
        self.config.write_text('\n' + setup.sexp(fields) + '\n')

    def write_manifest(self, *, installed):
        value = dict(project_root=str(self.root), installed_package=installed,
                     asic_generation='/selected-generation', model_root='/selected-models')
        self.manifest.write_text(json.dumps(value))
        return value

    def test_refresh_migrates_old_catalog_preserving_companion_and_selected_runtime(self):
        original = self.config.read_bytes()
        prior = self.write_manifest(installed=True)
        prior.update(checkout_layout='checkout-v1', source_layout='ownership-v1')
        for key in ('suite_sources', 'suite_targets', 'suite_executables', 'target_hashes',
                    'provider_commands'):
            prior[key] = {'controlled-fifo': {}, 'pt8-memory-workloads': {}}
        self.manifest.write_text(json.dumps(prior))
        self.mocks['validate_manifest'].side_effect = validate_manifest
        with self.assertRaisesRegex(ValueError, r'suite catalog has changed;.*--refresh'):
            setup.main([])
        self.build.assert_not_called()
        setup.main(['--refresh'])
        self.mocks['validate_manifest'].assert_called_once_with(prior, 'discover')
        kwargs = self.build.call_args.kwargs
        self.assertEqual(kwargs['python'], self.interpreter)
        self.assertEqual(kwargs['asic_generation'], Path('/selected-generation'))
        self.assertEqual(kwargs['model_root'], Path('/selected-models'))
        self.assertEqual(self.config.read_bytes(), original)

    def test_check_requires_explicit_refresh_when_manifest_is_missing(self):
        with self.assertRaisesRegex(RuntimeError, '--refresh'):
            setup.main([])
        self.build.assert_not_called()
        setup.main(['--refresh'])
        self.build.assert_called_once()

    def test_sdk_discovery_uses_project_environment_not_application_prefix(self):
        foreign = self.root / 'foreign-app/bin'
        foreign.mkdir(parents=True)
        for name in ('silver', 'ag'):
            launcher = foreign / name
            launcher.write_text('#!/bin/sh\nexit 0\n')
            launcher.chmod(0o755)
        with patch.dict(setup.os.environ, {'PATH': str(foreign) + ':/usr/bin',
                                          'OCAMLPATH': '/project-sdk/lib'}):
            setup.main(['--refresh'])
        env = self.build.call_args.kwargs['environment']
        self.assertEqual(env['OCAMLPATH'], '/project-sdk/lib')
        self.assertTrue(env['PATH'].startswith('/current-switch/bin:'))

    def test_check_validates_existing_normal_manifest_without_building(self):
        value = self.write_manifest(installed=True)
        setup.main([])
        self.mocks['validate_manifest'].assert_called_once_with(value, 'discover')
        self.build.assert_not_called()

    def test_parallelism_opt_in_updates_existing_config_without_building(self):
        self.write_manifest(installed=True)
        original = setup.simulation_fields(self.config.read_bytes())
        setup.main(['--max-parallel-runs', '2'])
        self.assertEqual(setup.simulation_fields(self.config.read_bytes()),
                         dict(original, max_parallel_runs='2'))
        current = self.config.read_bytes()
        setup.main([])
        self.assertEqual(self.config.read_bytes(), current)
        setup.main(['--max-parallel-runs', '1'])
        self.assertEqual(setup.simulation_fields(self.config.read_bytes()),
                         dict(original, max_parallel_runs='1'))
        self.build.assert_not_called()

    def test_parallelism_opt_in_is_bounded(self):
        for value in ('0', '9', '2.5'):
            with (self.subTest(value=value), redirect_stderr(io.StringIO()),
                  self.assertRaises(SystemExit) as error):
                setup.main(['--max-parallel-runs', value])
            self.assertEqual(error.exception.code, 2)
        original = self.config.read_bytes()
        for value in (0, 9, ['2']):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '1 to 8'):
                setup.simulation_fields(
                    (setup.sexp([*setup.simulation_fields(original).items(),
                                ('max_parallel_runs', value)]) + '\n').encode())

    def test_parallelism_opt_in_can_publish_new_or_refresh_existing(self):
        self.config.unlink()
        setup.main(['--max-parallel-runs', '2'])
        self.assertEqual(setup.simulation_fields(self.config.read_bytes())['max_parallel_runs'], '2')
        original = self.config.read_bytes()
        self.write_manifest(installed=True)
        setup.main(['--refresh'])
        self.assertEqual(self.config.read_bytes(), original)
        setup.main(['--refresh', '--max-parallel-runs', '8'])
        self.assertEqual(setup.simulation_fields(self.config.read_bytes())['max_parallel_runs'], '8')
        self.assertEqual(self.build.call_count, 3)

    def test_parallelism_preserves_mirrored_and_foreign_configs(self):
        self.write_manifest(installed=True)
        original = self.config.read_bytes()
        paths = setup.config_location.candidate_paths(self.root, self.config.name)
        for other in paths[1:]:
            other.parent.mkdir(exist_ok=True)
            other.write_bytes(original)
        with self.assertRaisesRegex(RuntimeError, 'multiple configuration copies'):
            setup.main(['--max-parallel-runs', '2'])
        with self.assertRaisesRegex(RuntimeError, 'multiple configuration copies'):
            setup.main(['--refresh', '--max-parallel-runs', '2'])
        self.assertEqual([path.read_bytes() for path in paths], [original] * 6)
        for other in paths[1:]:
            other.unlink()
        self.write_config(self.root / 'custom_provider.py')
        with self.assertRaisesRegex(RuntimeError, 'another provider'):
            setup.main(['--max-parallel-runs', '2'])
        self.build.assert_not_called()

    def test_normal_refresh_refuses_prepared_or_foreign_config(self):
        self.write_manifest(installed=False)
        with self.assertRaisesRegex(RuntimeError, 'scripts/silver.py build'):
            setup.main(['--refresh'])
        self.manifest.unlink()
        (self.store / 'install.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'scripts/silver.py build'):
            setup.main(['--refresh'])
        (self.store / 'install.json').unlink()
        self.write_config(self.root / 'custom_provider.py')
        with self.assertRaisesRegex(RuntimeError, 'another provider'):
            setup.main(['--refresh'])
        self.build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
