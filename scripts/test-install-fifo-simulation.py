#!/usr/bin/env python3
"""Installer transaction checks; all publication is confined to private directories."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'installer', Path(__file__).with_name('install-fifo-simulation.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fifo-native-install-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.provider = self.root / 'prebuilt-provider'
        self.simulator = self.root / 'prebuilt-simulator'
        for binary in (self.provider, self.simulator):
            binary.write_bytes(b'fake verified executable\n')
            binary.chmod(0o755)
        self.args = ['--provider', str(self.provider), '--simulator', str(self.simulator)]
        self.config = self.root / 'hardcaml-workbench-simulation.sexp'

    def install(self, args=None):
        with contextlib.redirect_stdout(io.StringIO()):
            installer.main(self.args if args is None else args, root=self.root)
        return json.loads((self.root / '.dev/fifo-simulation-install.json').read_text())

    def test_native_generation_and_owned_upgrade_preserve_old_bytes(self):
        first = self.install()
        generation = Path(first['generation'])
        original = {p.name: p.read_bytes() for p in generation.iterdir()}
        self.assertEqual(set(original), {'test_provider.exe', 'fifo_sim.exe'})
        # Parse with the independent reference codec.
        from wire import parse, record
        fields = record(parse(self.config.read_text()), [
            'schema_version', 'provider_executable', 'provider_args',
            'discovery_timeout_seconds', 'run_timeout_seconds'])
        self.assertEqual(fields['provider_executable'], str(generation / 'test_provider.exe'))
        self.assertEqual(fields['provider_args'], [])
        self.assertEqual(first['config_sha256'], hashlib.sha256(self.config.read_bytes()).hexdigest())
        self.provider.write_bytes(b'new provider\n')
        second = self.install()
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertEqual(original, {p.name: p.read_bytes() for p in generation.iterdir()})
        self.assertEqual((Path(second['generation']) / 'test_provider.exe').read_bytes(), b'new provider\n')

    def test_unowned_or_edited_config_refused_before_build(self):
        for owned in (False, True):
            if owned:
                self.config.unlink()
                self.install()
            self.config.write_text('unrelated or edited\n')
            with patch.object(installer.subprocess, 'run') as build:
                with self.assertRaisesRegex(RuntimeError, 'Refusing to overwrite'):
                    self.install(['--build'])
                build.assert_not_called()
            self.assertEqual(self.config.read_text(), 'unrelated or edited\n')

    def test_owned_python_generation_migrates_without_stale_companions(self):
        legacy = self.root / '.dev/fifo-simulation/legacy'
        legacy.mkdir(parents=True)
        for name in ('provider.py', 'wire.py', 'fifo_sim.exe'):
            (legacy / name).write_bytes(b'legacy bytes\n')
        self.config.write_text('owned Python configuration\n')
        manifest = self.root / '.dev/fifo-simulation-install.json'
        manifest.write_text(json.dumps({
            'generation': str(legacy),
            'config_sha256': hashlib.sha256(self.config.read_bytes()).hexdigest(),
        }))
        installed = Path(self.install()['generation'])
        self.assertEqual({p.name for p in installed.iterdir()}, {'test_provider.exe', 'fifo_sim.exe'})
        self.assertNotIn('python', self.config.read_text().lower())
        self.assertEqual({p.name: p.read_bytes() for p in legacy.iterdir()},
                         {name: b'legacy bytes\n' for name in ('provider.py', 'wire.py', 'fifo_sim.exe')})

    def test_requires_both_prebuilt_executables_and_bounded_jobs(self):
        for args in ([], ['--simulator', str(self.simulator)],
                     self.args + ['--jobs', '7'], self.args + ['--build']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.install(args)
        self.assertFalse((self.root / '.dev').exists())
        self.provider.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'not an executable file'):
            self.install()
        self.assertFalse((self.root / '.dev').exists())

    def test_explicit_build_targets_and_budget(self):
        build_dir = self.root / 'build'
        outputs = build_dir / 'default/ip/controlled_fifo/verif/simulation'
        outputs.mkdir(parents=True)
        for name in ('test_provider.exe', 'fifo_sim.exe'):
            target = outputs / name
            target.write_bytes(b'built executable\n')
            target.chmod(0o755)
        with patch.object(installer.subprocess, 'run') as build:
            self.install(['--build', '--build-dir', str(build_dir), '--jobs', '3',
                          '--with-switch', str(self.provider)])
        command = build.call_args.args[0]
        self.assertIn('-j3', command)
        self.assertEqual(command[-2:], ['ip/controlled_fifo/verif/simulation/test_provider.exe',
                                       'ip/controlled_fifo/verif/simulation/fifo_sim.exe'])
        build.assert_called_once()

    def test_config_race_does_not_replace_concurrent_edit(self):
        copy = installer.shutil.copy2

        def racing_copy(source, target):
            result = copy(source, target)
            self.config.write_text('concurrent edit\n')
            return result

        with patch.object(installer.shutil, 'copy2', side_effect=racing_copy):
            with self.assertRaisesRegex(RuntimeError, 'configuration changed'):
                self.install()
        self.assertEqual(self.config.read_text(), 'concurrent edit\n')
        self.assertFalse((self.root / '.dev/fifo-simulation-install.json').exists())

    def edited_owned(self):
        installed = self.install()
        manifest = self.root / '.dev/fifo-simulation-install.json'
        ownership = manifest.read_bytes()
        self.config.write_bytes(b'  \n' + self.config.read_bytes() + b'\n')
        edited = self.config.read_bytes()
        args = self.args + ['--adopt-config-sha256', hashlib.sha256(edited).hexdigest()]
        return installed, ownership, edited, args

    def test_adoption_exact_hash_and_ownership_required_before_build_or_copy(self):
        self.config.write_text('unowned configuration\n')
        expected = hashlib.sha256(self.config.read_bytes()).hexdigest()
        with patch.object(installer.subprocess, 'run') as build, patch.object(installer.shutil, 'copy2') as copy:
            for checksum, diagnostic in (('0' * 64, 'SHA256'), (expected, 'existing ownership')):
                with self.assertRaisesRegex(RuntimeError, diagnostic):
                    self.install(['--build', '--adopt-config-sha256', checksum])
            build.assert_not_called()
            copy.assert_not_called()
        self.assertFalse((self.root / '.dev').exists())
        self.config.unlink()
        self.edited_owned()
        with patch.object(installer.subprocess, 'run') as build, patch.object(installer.shutil, 'copy2') as copy:
            with self.assertRaisesRegex(RuntimeError, 'SHA256'):
                self.install(['--build', '--adopt-config-sha256', '0' * 64])
            build.assert_not_called()
            copy.assert_not_called()

    def test_valid_adoption_backs_up_exact_bytes_and_preserves_timeouts(self):
        previous, ownership, edited, args = self.edited_owned()
        from wire import sexp
        fields = installer.config_fields(edited)
        fields['discovery_timeout_seconds'] = '12'
        fields['run_timeout_seconds'] = '321'
        self.config.write_text(sexp(list(fields.items())))
        edited = self.config.read_bytes()
        args[-1] = hashlib.sha256(edited).hexdigest()
        installed = self.install(args)
        receipt = Path(installed['receipt'])
        self.assertEqual((receipt / 'previous-configuration.sexp').read_bytes(), edited)
        self.assertEqual((receipt / 'previous-ownership.json').read_bytes(), ownership)
        self.assertEqual((receipt / 'configuration.sexp').read_bytes(), self.config.read_bytes())
        self.assertEqual(json.loads((receipt / 'ownership.json').read_text()), installed)
        evidence = json.loads((receipt / 'receipt.json').read_text())
        self.assertEqual(evidence['status'], 'published')
        self.assertEqual(evidence['adoption_sha256'], args[-1])
        self.assertEqual(evidence['previous_ownership_sha256'], hashlib.sha256(ownership).hexdigest())
        fields = installer.config_fields(self.config.read_bytes())
        self.assertEqual(fields['discovery_timeout_seconds'], '12')
        self.assertEqual(fields['run_timeout_seconds'], '321')
        self.assertTrue(Path(previous['generation']).is_dir())

    def test_adoption_refuses_unrelated_config_bad_timeouts_and_changed_provenance(self):
        previous, ownership, edited, args = self.edited_owned()
        from wire import sexp
        original = installer.config_fields(edited)
        for key, value, diagnostic in (
                ('provider_executable', '/unrelated/provider', 'unrelated provider'),
                ('run_timeout_seconds', '0', 'timeout'),
                ('surprise', 'field', 'unexpected record')):
            fields = dict(original)
            fields[key] = value
            self.config.write_text(sexp(list(fields.items())))
            args[-1] = hashlib.sha256(self.config.read_bytes()).hexdigest()
            with self.assertRaisesRegex((RuntimeError, ValueError), diagnostic):
                self.install(args)
        self.config.write_bytes(edited)
        args[-1] = hashlib.sha256(edited).hexdigest()
        (Path(previous['generation']) / 'fifo_sim.exe').write_bytes(b'changed\n')
        with self.assertRaisesRegex(RuntimeError, 'provenance mismatch'):
            self.install(args)

    def test_backup_failure_does_not_publish_config_or_ownership(self):
        previous, ownership, edited, args = self.edited_owned()
        write = installer.durable_write

        def fail_backup(path, contents):
            if path.name == 'previous-ownership.json':
                raise OSError('injected backup failure')
            return write(path, contents)

        with patch.object(installer, 'durable_write', side_effect=fail_backup):
            with self.assertRaisesRegex(OSError, 'backup failure'):
                self.install(args)
        self.assertEqual(self.config.read_bytes(), edited)
        self.assertEqual((self.root / '.dev/fifo-simulation-install.json').read_bytes(), ownership)

    def test_adopt_edited_legacy_python_install(self):
        from wire import sexp
        legacy = self.root / '.dev/fifo-simulation/legacy'
        legacy.mkdir(parents=True)
        for name in ('provider.py', 'wire.py', 'fifo_sim.exe'):
            (legacy / name).write_bytes(b'original Python generation\n')
        original = (sexp([
            ('schema_version', 1), ('provider_executable', '/usr/bin/python3'),
            ('provider_args', [str(legacy / 'provider.py')]),
            ('discovery_timeout_seconds', 10), ('run_timeout_seconds', 120)]) + '\n').encode()
        (legacy / 'configuration.sexp').write_bytes(original)
        self.config.write_bytes(original + b'\n')
        ownership = dict(generation=str(legacy), config_sha256=hashlib.sha256(original).hexdigest(),
                         sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in legacy.iterdir()})
        (self.root / '.dev/fifo-simulation-install.json').write_text(json.dumps(ownership))
        installed = self.install(self.args + [
            '--adopt-config-sha256', hashlib.sha256(self.config.read_bytes()).hexdigest()])
        fields = installer.config_fields(self.config.read_bytes())
        self.assertEqual(fields['provider_executable'], str(Path(installed['generation']) / 'test_provider.exe'))
        self.assertEqual(fields['provider_args'], [])
        self.assertEqual((fields['discovery_timeout_seconds'], fields['run_timeout_seconds']), ('10', '120'))
        self.assertEqual((legacy / 'configuration.sexp').read_bytes(), original)

    def test_interrupted_publication_retains_prepared_recovery_receipt(self):
        previous, ownership, edited, args = self.edited_owned()
        manifest = self.root / '.dev/fifo-simulation-install.json'
        replace = installer.os.replace

        def fail_ownership(source, target):
            if target == manifest:
                raise OSError('injected ownership publication failure')
            return replace(source, target)

        with patch.object(installer.os, 'replace', side_effect=fail_ownership):
            with self.assertRaisesRegex(OSError, 'publication failure'):
                self.install(args)
        receipts = self.root / '.dev/fifo-simulation-receipts'
        prepared = [path for path in receipts.iterdir()
                    if json.loads((path / 'receipt.json').read_text())['status'] == 'prepared']
        self.assertEqual(len(prepared), 1)
        self.assertEqual((prepared[0] / 'previous-configuration.sexp').read_bytes(), edited)
        self.assertEqual((prepared[0] / 'previous-ownership.json').read_bytes(), ownership)
        self.assertEqual((prepared[0] / 'configuration.sexp').read_bytes(), self.config.read_bytes())
        self.assertEqual(manifest.read_bytes(), ownership)
        # An interrupted publication is never silently treated as an owned install.
        with self.assertRaisesRegex(RuntimeError, 'Refusing to overwrite'):
            self.install()


if __name__ == '__main__':
    unittest.main()
