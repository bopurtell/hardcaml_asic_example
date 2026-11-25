"""Standalone integration regression: the configured FIFO CLI picks up an appended target."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/workbench'))
from wire import parse


class ConfiguredChipDispatch(unittest.TestCase):
    def test_catalog_append(self):
        with tempfile.TemporaryDirectory(prefix='configured-chip-') as tmp:
            root = Path(tmp)
            for name in ('asics', 'ip', 'integration', 'scripts'):
                shutil.copytree(ROOT / name, root / name)
            for name in ('README.md', 'asic-dependency.json', 'dune-project',
                         'hardcaml-asic-targets.json'):
                shutil.copyfile(ROOT / name, root / name)
            # Use the same optional local library overlay as the source checkout.
            conf = Path('.dev/dune/findlib.conf')
            if (ROOT / conf).exists():
                (root / conf).parent.mkdir(parents=True)
                shutil.copyfile(ROOT / conf, root / conf)
                shutil.copyfile(ROOT / 'dune-workspace', root / 'dune-workspace')
            catalog = root / 'hardcaml-asic-targets.json'
            manifest = json.loads(catalog.read_text())
            for row in manifest['targets']:
                directory = Path(row['executable']).parts[0]
                if not (root / directory).exists():
                    shutil.copytree(ROOT / directory, root / directory)

            def run(*args):
                return subprocess.check_output(args, cwd=root, text=True)

            run(sys.executable, '-B', 'scripts/configure-synthesis.py')
            config = root / '.silver/silver-asic.sexp'
            cli = Path(dict(parse(config.read_text()))['project_executable'])
            self.assertEqual(cli.parent, root / '_build/default/asics/fifo_demo/cli')

            # Plans read HEAD and working-tree status for provenance. Give them
            # a private index and this fixture's work tree, without a test commit.
            git_dir = run('git', '-C', ROOT, 'rev-parse', '--absolute-git-dir').strip()
            index = root / '.fixture-index'
            shutil.copyfile(Path(git_dir) / 'index', index)
            env = dict(os.environ, GIT_DIR=git_dir, GIT_WORK_TREE=str(root),
                       GIT_INDEX_FILE=str(index), GIT_OPTIONAL_LOCKS='0')

            def query(exe, *args):
                return json.loads(subprocess.check_output([exe, *args, '--json'], cwd=root, env=env))

            def chips():
                result = query(cli, 'chip', 'list')
                self.assertEqual(result['default_chip'], 'controlled_fifo')
                rows = {chip['id']: chip for chip in result['chips']}
                self.assertEqual(len(rows), len(result['chips']))
                return rows

            before = chips()
            budget = before['sram_budget']
            self.assertEqual(budget['default_variant'], 'two_slot')
            self.assertEqual({v['id'] for v in budget['variants']}, {'two_slot', 'three_slot'})

            chip = 'dispatchprobe'
            target = f'asic_{chip}/project.exe'
            rendered = json.loads(run('hardcaml-asic-starter', 'render-target', '--name', chip))
            for item in rendered['files']:
                path = root / item['path']
                self.assertTrue(path.resolve().is_relative_to(root / f'asic_{chip}'))
                path.parent.mkdir(exist_ok=True, parents=True)
                with path.open('x') as f:
                    f.write(item['contents'])
            manifest['targets'].append({'id': chip, 'executable': target})
            catalog.write_text(json.dumps(manifest))
            run('dune', 'build', '--root', '.', '--build-dir', '_build', target)
            after = chips()
            added = after.pop(chip)
            self.assertEqual(after, before)
            self.assertEqual(added['default_variant'], 'default')
            selected = ['--chip', chip, '--variant', 'default']
            direct = root / '_build/default' / target
            for args in [('flow', 'list'), ('flow', 'plan', '--flow', 'standard',
                                           '--profile', 'balanced', '--endpoint', 'synthesis')]:
                actual = query(cli, *args, *selected)
                self.assertEqual(actual, query(direct, *args, *selected))
            self.assertEqual(json.loads(actual['bundle_manifest'])['top_module'], 'tt_um_dispatchprobe')
            args = ('flow', 'plan', '--endpoint', 'synthesis')
            default = query(cli, *args)
            self.assertEqual(default, query(cli, *args, '--chip', 'controlled_fifo', '--variant', 'default'))
            self.assertEqual(default['project_name'], 'controlled_fifo')
            self.assertEqual(json.loads(default['bundle_manifest'])['top_module'], 'tt_um_controlled_fifo')
            self.assertFalse((root / '_flow_results').exists())


if __name__ == '__main__':
    unittest.main()
