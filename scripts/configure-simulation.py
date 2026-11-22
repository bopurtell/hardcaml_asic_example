#!/usr/bin/env python3
"""Prepare this project's two simulation suites for native silver --standalone."""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from tempfile import NamedTemporaryFile

sys.dont_write_bytecode = True
from workbench_main import ROOT, bounded_build, config_location, lock, regular, sexp, simulation_fields
from checkout_setup import prepare_simulation
from checkout_provider import PREPARE, REFRESH, validate_manifest


def update_parallel_runs(root, name, existing, fields, count):
    if count is None or fields.get('max_parallel_runs') == str(count):
        return
    # Changing two mirrored configs cannot be published atomically. Leave them
    # alone rather than exposing a conflicting pair to a newly opened Silver.
    if len(existing) != 1:
        raise RuntimeError('cannot change max_parallel_runs with two configuration copies; keep one copy first')
    path = next(iter(existing))
    contents = (sexp(list(dict(fields, max_parallel_runs=count).items())) + '\n').encode()
    temp_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
            temp_path = Path(temp.name)
            os.fchmod(temp.fileno(), stat.S_IMODE(path.lstat().st_mode))
            temp.write(contents)
        if config_location.copies(root, name) != existing:
            raise RuntimeError('simulation configuration changed during setup')
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, default=os.environ.get('TOOLCHAIN') or None)
    parser.add_argument('--refresh', action='store_true', help='rebuild an existing native setup')
    parser.add_argument('--max-parallel-runs', type=int, choices=range(1, 9),
                        help='set the number of simultaneous simulation attempts (default: 1)')
    args = parser.parse_args(argv)
    name = 'hardcaml-workbench-simulation.sexp'
    store = ROOT / '.dev/workbench-main'
    manifest = store / 'simulation/manifest.json'
    python = Path(sys.executable).resolve()
    provider_args = ['-B', str(ROOT / 'integration/workbench/checkout_provider.py'),
                     '--manifest', str(manifest)]
    with lock(ROOT.parent / '.workbench-example-build.lock'):
        existing = config_location.copies(ROOT, name)
        prior = None
        if manifest.exists():
            prior = json.loads(regular(manifest))
        if (os.path.lexists(store / 'install.json')
                or prior is not None and (
                    not prior.get('installed_package') or prior.get('project_root') != str(ROOT))):
            if existing and not args.refresh and args.max_parallel_runs is None:
                print('Keeping existing prepared Silver simulation configuration.')
                return
            raise RuntimeError('simulation setup belongs to a prepared installation; run ' + PREPARE)
        if existing:
            data = next(iter(existing.values()))
            fields = simulation_fields(data)
            if fields['provider_args'] != provider_args:
                if args.refresh or args.max_parallel_runs is not None:
                    raise RuntimeError('existing simulation configuration uses another provider')
                print('Keeping existing Silver simulation configuration.')
                return
            python = Path(fields['provider_executable'])
            if fields['schema_version'] != '1' or not python.is_absolute() or not os.access(python, os.X_OK):
                raise RuntimeError('existing simulation configuration requires an absolute executable and schema 1')
            for field, limit in (('discovery_timeout_seconds', 60), ('run_timeout_seconds', 86400)):
                timeout = fields[field]
                if not isinstance(timeout, str) or not timeout.isdecimal() or not 1 <= int(timeout) <= limit:
                    raise RuntimeError('invalid simulation timeout: ' + field)
            if not args.refresh:
                if prior is None:
                    raise RuntimeError('missing simulation manifest; run ' + REFRESH)
                validate_manifest(prior, 'discover')
                update_parallel_runs(ROOT, name, existing, fields, args.max_parallel_runs)
                print('Silver simulation configuration is ready.')
                return
        switch = Path(subprocess.check_output(['opam', 'var', 'prefix'], text=True).strip())
        prefix = Path(os.environ.get('HARDCAML_ASIC_GENERATION') or
                      (prior['asic_generation'] if prior is not None else switch))
        toolchain = args.toolchain or ROOT / '_flow_tools'
        model_root = (Path(prior['model_root']) if prior is not None and args.toolchain is None else
                      toolchain / 'pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog')
        silver = shutil.which('silver')
        paths = [os.environ.get('OCAMLPATH', '')]
        if silver:
            paths.append(str(Path(silver).parent.parent / 'lib'))
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'OPAMROOT', 'OPAMSWITCH') if k in os.environ}
        env.update(OCAMLPATH=os.pathsep.join(filter(None, paths)),
                   PATH=str(switch / 'bin') + os.pathsep + env['PATH'])
        prepare_simulation(project_root=ROOT, build_dir='_build_simulation',
                           asic_generation=prefix, model_root=model_root,
                           run=bounded_build, environment=env, python=python, installed_package=True)
        if existing:
            update_parallel_runs(ROOT, name, existing, fields, args.max_parallel_runs)
        else:
            fields = [('schema_version', 1), ('provider_executable', python),
                      ('provider_args', provider_args), ('discovery_timeout_seconds', 30),
                      ('run_timeout_seconds', 600)]
            if args.max_parallel_runs is not None:
                fields.append(('max_parallel_runs', args.max_parallel_runs))
            contents = (sexp(fields) + '\n').encode()
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
