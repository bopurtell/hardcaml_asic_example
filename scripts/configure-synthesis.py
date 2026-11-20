#!/usr/bin/env python3
"""Configure Silver synthesis against the selected opam switch and provisioned tools."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'integration/workbench'))
import config_location
from wire import sexp

TARGET = 'asics/fifo_demo/cli/project.exe'


def publish(root, filename, fields):
    # Recheck both supported locations after the build. Link complete bytes
    # into place exclusively so concurrent setup cannot replace a user's file.
    if config_location.copies(root, filename):
        return
    directory = root / '.workbench'
    directory.mkdir(exist_ok=True)
    with NamedTemporaryFile(dir=directory) as pending:
        pending.write((sexp(fields) + '\n').encode())
        pending.flush()
        try:
            os.link(pending.name, directory / filename)
        except FileExistsError:
            config_location.copies(root, filename)
            return
    print('Created', directory / filename)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path,
                        default=os.environ.get('TOOLCHAIN') or str(ROOT / '_flow_tools'))
    tools = parser.parse_args().toolchain.resolve()
    results = ROOT / '_flow_results/workbench'
    executable = ROOT / '_build/default' / TARGET
    configs = {
        'hardcaml-workbench-asic.sexp': [
            ('schema_version', 1), ('project_executable', executable),
            ('results_root', results / 'asic'), ('toolchain', tools),
            ('python', [tools / '.venv/bin/python']), ('support_tools', [tools / 'tt']),
            ('pdk_root', [tools / 'pdk']), ('stage_timeout_seconds', [3600])],
        'hardcaml-workbench-preparation.sexp': [
            ('schema_version', 1), ('build_target', TARGET),
            ('results_root', results / 'preparation'), ('timeout_seconds', 600)],
    }
    missing = [name for name in configs if not config_location.copies(ROOT, name)]
    if not missing:
        print('Keeping existing Silver synthesis and preparation configurations.')
        return
    if 'hardcaml-workbench-asic.sexp' in missing:
        subprocess.run(['opam', 'exec', '--', 'dune', 'build', '--root', str(ROOT),
                        '--build-dir', '_build', '-j', '2', TARGET], check=True)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError(f'Dune did not produce executable {executable}')
    for name in missing:
        publish(ROOT, name, configs[name])


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except (OSError, RuntimeError) as error:
        sys.exit(f'configure-synthesis: {error}')
