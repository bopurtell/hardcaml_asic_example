#!/usr/bin/env python3
"""Run prebuilt private PT8 daemon/client in the foreground; no automatic restart."""
import argparse
import json
import os
from pathlib import Path
import sys
from workbench_paths import ROOT
from workbench_provider import SOURCE_LAYOUT


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('mode', choices=['daemon', 'client'])
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path,
                        help='independent discovery/state under this session (default: session)')
    args, extra = parser.parse_known_args()
    session = args.session.resolve(strict=True)
    runtime = args.runtime_root.resolve(strict=True) if args.runtime_root else session
    if not runtime.is_relative_to(session):
        parser.error('runtime-root must be inside the selected private session')
    manifest = json.loads((session / 'manifest.json').read_text())
    if manifest.get('source_layout') != SOURCE_LAYOUT:
        parser.error('legacy source layout: explicitly create a new --store with scripts/workbench_dev.py '
                     'for the migrated ownership layout; existing sessions/history remain unchanged')
    if 'private_source_root' in manifest:
        generation = Path(manifest['generation'])
        os.environ['OCAMLPATH'] = str(generation / 'lib')
        os.environ['HARDCAML_ASIC_GENERATION'] = str(generation)
        os.environ['PATH'] = str(generation / 'bin') + ':' + os.environ['PATH']
        os.environ['PT8_PROJECT_ROOT'] = manifest['private_source_root']
    os.environ['PT8_REAL_DUNE'] = manifest['real_dune']
    os.environ['PATH'] = str(session / 'tool-bin') + ':' + os.environ['PATH']
    build = Path(manifest['wb_build_root']) / 'default'
    if args.mode == 'daemon':
        for name in ('discovery', 'state'):
            (runtime / name).mkdir(exist_ok=True)
        command = [str(build / 'daemon/main.exe'), '--port', '0',
            '--discovery-dir', str(runtime / 'discovery'), '--state-dir', str(runtime / 'state')]
    else:
        from wire import parse, record
        metadata = dict(parse((runtime / 'discovery/daemon.sexp').read_text()))
        endpoint = metadata['endpoint']
        command = [str(build / 'terminal/main.exe'), '--connect', endpoint,
            '--project-root', manifest['project_root']]
    extra = extra[1:] if extra[:1] == ['--'] else extra
    command += extra
    os.environ['XDG_STATE_HOME'] = str(runtime / 'client-state')
    os.execv(command[0], command)


if __name__ == '__main__':
    main()
