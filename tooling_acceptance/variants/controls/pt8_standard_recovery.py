#!/usr/bin/env python3
"""Retain read-only live failure recovery and source-only captured-driver repro."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT.parent / 'hardcaml_workbench/demo/synthetic_flow'))
from http_client import Client, field, parse
from pt8_acceptance import write, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    args = parser.parse_args()
    session = args.session.resolve(strict=True)
    output = ROOT / '.dev/asic-pt8-workbench' / ('recovery-investigation-' + uuid.uuid4().hex)
    output.mkdir()
    manifest = json.loads((session / 'manifest.json').read_text())
    metadata = dict(parse((session / 'discovery/daemon.sexp').read_text()))
    http = Client(metadata['endpoint'], manifest['project_root'])
    snapshot = http.raw('/api/v1/snapshot', [['instance_id', http.instance]])
    write(output / 'live-snapshot.json', snapshot)
    write(output / 'live-asic.json', http.rpc('Get', wait=False))
    jobs = field(snapshot, 'jobs')
    for job in jobs:
        jid = field(job, 'id')
        log = http.raw('/api/v1/read-log', [['instance_id', http.instance], ['job', jid],
            ['offset', 0], ['max_records', 100], ['max_bytes', 65536]])
        write(output / (jid + '.json'), {'job': job, 'log': log})
    write(output / 'http.json', http.history)
    binary = session / 'provider/project.exe'
    argv = [str(binary), 'flow', 'plan', '--flow', 'standard', '--profile', 'balanced',
            '--endpoint', 'synthesis', '--source-root', manifest['project_root'], '--json']
    result = subprocess.run(argv, cwd=manifest['project_root'], capture_output=True, timeout=120)
    (output / 'repro.stdout').write_bytes(result.stdout)
    (output / 'repro.stderr').write_bytes(result.stderr)
    write(output / 'repro.json', {'argv': argv, 'cwd': manifest['project_root'],
        'exit_code': result.returncode, 'binary_sha256': sha(binary), 'eda_allocation': 0})
    assert result.returncode != 0
    print(output)


if __name__ == '__main__':
    main()
