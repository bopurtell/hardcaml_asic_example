"""Exercise the normal/prepared simulation setup boundary without real builds."""
import importlib.util
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
        self.config = self.root / '.workbench/hardcaml-workbench-simulation.sexp'
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

    def test_check_validates_existing_normal_manifest_without_building(self):
        value = self.write_manifest(installed=True)
        setup.main([])
        self.mocks['validate_manifest'].assert_called_once_with(value, 'discover')
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
