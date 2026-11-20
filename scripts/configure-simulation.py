#!/usr/bin/env python3
"""Prepare this project's two simulation suites for native silver --standalone."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile

sys.dont_write_bytecode = True
from workbench_main import ROOT, bounded_build, config_location, lock, regular, sexp
from checkout_setup import prepare_simulation
from checkout_provider import validate_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, default=Path(os.environ.get('TOOLCHAIN') or ROOT / '_flow_tools'))
    parser.add_argument('--refresh', action='store_true', help='rebuild an existing native setup')
    args = parser.parse_args()
    name = 'hardcaml-workbench-simulation.sexp'
    store = ROOT / '.dev/workbench-main'
    manifest = store / 'simulation/manifest.json'
    python = Path(sys.executable).resolve()
    fields = [('schema_version', 1), ('provider_executable', python),
              ('provider_args', ['-B', ROOT / 'integration/workbench/checkout_provider.py',
                                 '--manifest', manifest]),
              ('discovery_timeout_seconds', 30), ('run_timeout_seconds', 600)]
    contents = (sexp(fields) + '\n').encode()
    with lock(ROOT.parent / '.workbench-example-build.lock'):
        existing = config_location.copies(ROOT, name)
        if existing and any(data != contents for data in existing.values()):
            if args.refresh:
                raise RuntimeError('existing simulation configuration uses another provider')
            print('Keeping existing Silver simulation configuration.')
            return
        if manifest.exists():
            prior = json.loads(regular(manifest))
            if not prior.get('installed_package') or prior.get('project_root') != str(ROOT):
                if existing and not args.refresh:
                    print('Keeping existing prepared Silver simulation configuration.')
                    return
                raise RuntimeError('manifest belongs to a prepared installation; use scripts/silver.py build/publish')
            if existing and not args.refresh:
                validate_manifest(prior, 'discover')
                print('Silver simulation configuration is ready.')
                return
        switch = Path(subprocess.check_output(['opam', 'var', 'prefix'], text=True).strip())
        prefix = Path(os.environ.get('HARDCAML_ASIC_GENERATION') or switch)
        silver = shutil.which('silver')
        paths = [os.environ.get('OCAMLPATH', '')]
        if silver:
            paths.append(str(Path(silver).parent.parent / 'lib'))
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'OPAMROOT', 'OPAMSWITCH') if k in os.environ}
        env.update(OCAMLPATH=os.pathsep.join(filter(None, paths)),
                   PATH=str(switch / 'bin') + os.pathsep + env['PATH'])
        prepare_simulation(project_root=ROOT, build_dir='_build_simulation',
                           asic_generation=prefix, model_root=args.toolchain.resolve() /
                           'pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog',
                           run=bounded_build, environment=env, python=python, installed_package=True)
        if not existing:
            directory = ROOT / '.workbench'
            directory.mkdir(exist_ok=True)
            with NamedTemporaryFile(dir=directory) as temp:
                temp.write(contents)
                temp.flush()
                if config_location.copies(ROOT, name):
                    raise RuntimeError('simulation configuration appeared during setup')
                os.link(temp.name, directory / name)
        print('Configured Silver simulation:', config_location.selected(ROOT, name))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f'configure-simulation: {error}')
