"""Exercise the real Dune resolver without installing or compiling a provider."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import workbench_main as main


class DiscoveryTest(unittest.TestCase):
    def test_direct_build_and_overrides(self):
        with tempfile.TemporaryDirectory(prefix='dune discovery ') as temp:
            root = Path(temp) / 'example'
            scripts = root / 'scripts'
            scripts.mkdir(parents=True)
            shutil.copy(Path(__file__).with_name('dune-workspace.local'), scripts)
            (root / 'dune-project').write_text('(lang dune 3.17)\n')
            packages = ['fixture_asic', 'fixture_sdk']
            (root / 'dune').write_text(''.join(
                f'(rule (target {pkg}.txt) (action (copy %{{lib:{pkg}:marker}} %{{target}})))\n'
                for pkg in packages))
            switch = Path(temp) / 'switch/lib'
            local = Path(temp) / 'home/.local/lib'
            live = Path(temp) / 'live/lib'
            asic = root / '.dev/asic/generations/pinned'
            sdk = root / '.dev/provider-sdk-pinned'

            def provide(lib, pkg, label):
                directory = lib / pkg
                directory.mkdir(parents=True)
                (directory / 'META').write_text('version = "1"\n')
                (directory / 'marker').write_text(label)

            def build(override=None):
                env = dict(os.environ)
                for key in ('OCAMLPATH', 'OCAMLFIND_CONF', 'DUNE_WORKSPACE', 'INSIDE_DUNE'):
                    env.pop(key, None)
                if override:
                    env['OCAMLPATH'] = str(override)
                subprocess.run(['dune', 'build', '-j4', '--root', str(root), '.'],
                               cwd=root, env=env, check=True)
                return [(root / '_build/default' / (pkg + '.txt')).read_text() for pkg in packages]

            provide(switch, packages[0], 'switch')
            provide(local, packages[1], 'user')
            main.configure_dune(root, None, switch, local)
            self.assertEqual(build(), ['switch', 'user'])
            provide(asic / 'lib', packages[0], 'pinned')
            provide(sdk / 'lib', packages[1], 'sdk-pin')
            provide(root / '.dev/asic/current/lib', packages[0], 'floating')
            main.configure_dune(root, dict(asic_generation=asic, sdk_prefix=sdk), switch, local)
            self.assertEqual(build(), ['pinned', 'sdk-pin'])
            provide(live, packages[0], 'live')
            self.assertEqual(build(live), ['live', 'sdk-pin'])
            workspace = root / 'dune-workspace'
            workspace.unlink()
            workspace.write_text('(lang dune 3.17)\n')
            with self.assertRaisesRegex(RuntimeError, 'belongs to the user'):
                main.configure_dune(root, None, switch, local)
            self.assertEqual(workspace.read_text(), '(lang dune 3.17)\n')


if __name__ == '__main__':
    unittest.main()
