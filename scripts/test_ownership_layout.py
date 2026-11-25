"""Ownership-layout copy/import regressions: isolated fixtures, no builds or EDA."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/workbench'))
import workbench_dev as dev
import workbench_provider as router


class OwnershipLayout(unittest.TestCase):
    def test_private_publication_and_recovery_with_six_aliases(self):
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as directory:
            store = Path(directory)
            project = store / 'project'
            project.mkdir()
            generations = store / 'generations'
            receipts = store / 'receipts'
            receipts.mkdir()
            manifests = []
            for label in ('old', 'new'):
                generation = generations / label
                config = generation / 'config'
                config.mkdir(parents=True)
                hashes = {}
                for kind in dev.CONFIGS:
                    name = dev.config_name(kind)
                    if label == 'old':
                        name = dev.config_location.legacy_name(name)
                    data = (label + '-' + kind).encode()
                    path = config / name
                    path.write_bytes(data)
                    hashes[name] = router.sha(path)
                    if label == 'old':
                        for target in dev.config_location.candidate_paths(project, dev.config_name(kind)):
                            target.parent.mkdir(exist_ok=True)
                            target.write_bytes(data)
                manifests.append(dict(store=str(store), generation=str(generation), config_files=hashes))
            prior, new = manifests
            dev.select_generation(store, prior['generation'])
            expected = dev.project_config_hashes(prior)
            self.assertEqual(len(expected), 18)
            self.assertEqual(router.inventory(project, ('.',)), expected)
            receipt = receipts / 'new'
            receipt.mkdir()
            replace = dev.replace_regular

            # Crash on the third update, then recover from the journal's exact
            # paths (including the mixed directory/name aliases).
            class Crash(BaseException):
                pass

            calls = 0

            def interrupt(path, data):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise Crash()
                replace(path, data)

            with patch.object(dev, 'replace_regular', side_effect=interrupt):
                with self.assertRaises(Crash):
                    dev.publish(store, prior, new, receipt)
            self.assertTrue((store / 'publication.json').is_file())
            dev.recover_publication(store)
            self.assertEqual(router.inventory(project, ('.',)), expected)
            self.assertEqual((store / 'selected').resolve(), Path(prior['generation']))
            receipt = receipts / 'second-attempt'
            receipt.mkdir()
            with patch.object(dev, 'verify') as verify:
                dev.publish(store, prior, new, receipt)
                verify.assert_called_once_with(new, allow_pending=True)
            self.assertEqual(router.inventory(project, ('.',)), dev.project_config_hashes(new))
            self.assertEqual((store / 'selected').resolve(), Path(new['generation']))

    def test_nested_import_and_support_update_races(self):
        # Reuse the isolated migration-race fixture without the integrated suite's
        # setUpClass, which captures apps and builds a complete private project.
        from test_workbench_dev import Acceptance
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as directory:
            test = Acceptance('test_12_migration_atomic_noreplace_and_baseline_support_updates')
            test.evidence = Path(directory)
            test.test_12_migration_atomic_noreplace_and_baseline_support_updates()

    def test_active_source_and_suite_closure(self):
        # Check real current inventories without touching a development store.
        files = router.inventory(ROOT, router.SOURCE_FILES + router.SOURCE_DIRS)
        for suite in router.SUITES:
            self.assertLessEqual(router.inventory(ROOT, router.SUITE_PATHS[suite]).keys(), files.keys())
        for target in dev.TARGETS:
            self.assertIn(str(Path(target).with_suffix('.ml')), files)
        for scope in ('ip/controlled_fifo/verif/cyclesim', 'asics/fifo_demo/verif',
                      'asics/program_memory/verif', 'tooling_acceptance/timing/basic',
                      'tooling_acceptance/timing/fixture/verif',
                      'tooling_acceptance/timing/named_flow', 'tooling_acceptance/timing/physical',
                      'tooling_acceptance/variants/verif'):
            self.assertIn(scope + '/dune', files)
        self.assertFalse(any(name.startswith('acceptance/') for name in files))

    def test_copy_ignores_generated_and_retained_evidence(self):
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as directory:
            root = Path(directory) / 'owner'
            root.mkdir()
            for name in router.SOURCE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            for name in router.SOURCE_DIRS:
                path = root / name
                path.mkdir(parents=True, exist_ok=True)
                (path / 'authored.py').write_text('# independent authored source\n')
                for cache in ('__pycache__', '_build_local', '.dev'):
                    (path / cache).mkdir()
                    (path / cache / 'generated').touch()
            (root / 'acceptance').mkdir()
            (root / 'acceptance/history.json').write_text('immutable evidence')
            before = router.inventory(root, router.SOURCE_FILES + router.SOURCE_DIRS)
            destination = Path(directory) / 'copy'
            self.assertEqual(dev.copy_sources(root, destination), before)
            self.assertEqual(router.inventory(destination, router.SOURCE_FILES + router.SOURCE_DIRS), before)
            self.assertFalse((destination / 'acceptance').exists())
            self.assertFalse(list(destination.rglob('__pycache__')))

    def test_legacy_store_refused_before_mutation_even_with_import_flags(self):
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as directory:
            root = Path(directory)
            store = root / 'legacy'
            (store / 'project/lib').mkdir(parents=True)
            sentinel = store / 'project/lib/user.ml'
            sentinel.write_bytes(b'user edits and historical identity\0')
            before = {str(p.relative_to(store)): p.read_bytes() for p in store.rglob('*') if p.is_file()}
            with patch.object(dev, 'capture', side_effect=AssertionError('capture must not run')):
                with self.assertRaisesRegex(RuntimeError, 'explicitly create a new --store'):
                    dev.main(['--root', str(root), '--store', str(store), 'prepare', '--refresh',
                              '--import-missing-source', '--update-owned-support'])
            self.assertEqual({str(p.relative_to(store)): p.read_bytes()
                              for p in store.rglob('*') if p.is_file()}, before)
            self.assertEqual(sorted(p.name for p in store.iterdir()), ['project'])
            with self.assertRaisesRegex(RuntimeError, 'new --store'):
                dev.require_source_layout(root / 'no-old-directories', {'schema_version': 1})

    def test_independent_provider_import_closure(self):
        # Copy the same minimal hierarchy used by fresh captures, then import it
        # in a separate interpreter to catch accidental imports from the checkout.
        names = ('integration/workbench/memory_provider.py',
                 'integration/workbench/memory_runner.py', 'integration/workbench/workbench_paths.py',
                 'integration/workbench/workbench_provider.py', 'integration/workbench/wire.py',
                 'tooling_acceptance/workloads/support/memory_workload.py',
                 'tooling_acceptance/workloads/support/command_receipts.py', 'scripts/workbench_git.py')
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as directory:
            root = Path(directory)
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
            for name in ('memory_provider.py', 'workbench_provider.py'):
                result = subprocess.run([sys.executable, '-B', str(root / 'integration/workbench' / name), '--help'],
                    cwd=root, env=dict(os.environ, PYTHONPATH='', PYTHONDONTWRITEBYTECODE='1'),
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
