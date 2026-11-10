#!/usr/bin/env python3
"""Fresh ordinary coarse synthesis and public retained-source evidence acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('build', 'emit', 'run', 'public'))
    p.add_argument('--attempt', required=True)
    p.add_argument('--run', type=Path)
    a = p.parse_args()
    generation = (ROOT / '.dev/asic-pt7c/provider/current').resolve(strict=True)
    output = ROOT / 'acceptance/pt7c' / a.attempt
    output.mkdir(exist_ok=False)
    provider = generation / 'bin/hardcaml-asic-flow'

    def record(label, argv, expected=(0,), timeout=900):
        command = [sys.executable, '-B', str(ROOT / 'tooling_acceptance/timing/basic/record_command.py'),
                   '--generation', str(generation), '--timeout', str(timeout),
                   '--output', str(output / label), '--', *map(str, argv)]
        result = subprocess.run(command, cwd=ROOT)
        assert result.returncode in expected, (label, result.returncode)
        return output / label

    if a.phase == 'build':
        record('build', ['opam', 'exec', '--switch=5.2.0+ox', '--', 'flock',
                        '/tmp/opencode/example-pt7-build.lock', 'dune', 'build', '--build-dir',
                        '_build_pt7c', '-j6', 'tooling_acceptance/timing/basic/timing_cli.exe', 'acceptance/pt7c/native_reader.exe'])
    elif a.phase == 'emit':
        # No source/config migration is needed by the existing minimal emitter.
        bundle = ROOT / '.dev/asic-pt7c' / ('bundle-' + a.attempt)
        record('emit', [ROOT / '_build_pt7c/default/tooling_acceptance/timing/basic/timing_cli.exe', 'emit-scalar', ROOT, bundle])
        manifest = json.loads((bundle / 'manifest.json').read_text())
        for member in manifest['files']:
            assert sha(bundle / member['path']) == member['sha256'], member['path']
        assert manifest['timing_native_coverage']['producer'] == 'constraints/pt7-native-coverage.tcl'
        assert manifest['timing_native_coverage']['schema'] == 2
        assert manifest['timing_native_coverage']['profile'] == 'opensta-2.7-native-state-v2'
        (output / 'bundle.json').write_text(json.dumps({'path': str(bundle), 'identity': manifest['identity'],
            'manifest_sha256': sha(bundle / 'manifest.json'), 'provider_receipt_sha256': sha(generation / 'receipt.json')}, indent=2) + '\n')
    elif a.phase == 'run':
        assert a.run is not None, '--run names the emitted bundle for this phase'
        record('run', [provider, 'run', a.run.resolve(), '--stage', 'synthesis',
                       '--toolchain', ROOT / '_flow_tools', '--runs', ROOT / '.dev/asic-pt7c/runs', '--json'])
    else:
        run = a.run.resolve(strict=True)
        original = {str(path.relative_to(run)): sha(path) for path in run.rglob('*')
                    if path.is_file() and not path.is_symlink()}
        inspected = record('inspect', [provider, 'timing-intent-inspect', run, '--kind', 'coarse_run', '--json'], (1,))
        view = json.loads((inspected / 'stdout.log').read_text())
        assert view['status'] == 'completed' and view['verdict'] == 'unavailable'
        assert len(view['corners']) == 1 and view['requested_corners'] == view['executed_corners']
        audit = view['corners'][0]
        assert len(audit['resolved']['stages']) == 5
        native = audit['native_coverage']
        assert native['profile'] == 'opensta-2.7-native-state-v2'
        assert native['native_design'] == json.loads((run / 'project/manifest.json').read_text())['top_module']
        assert native['stored_exception_scope']['status'] == 'matched'
        assert native['stored_exception_scope']['relation_count'] == 6
        assert len(native['diagnostics']['categories']) == 7
        assert native['exhaustive_exception_effect'] == 'unavailable'
        corner_dir = run / 'timing-intent/corners' / view['executed_corners'][0]
        minimum = (corner_dir / 'downstream_min.rpt').read_text()
        maximum = (corner_dir / 'downstream_max.rpt').read_text()
        assert minimum.count('Startpoint:') == 3 and maximum.count('Startpoint:') == 3
        assert minimum.count('slack (VIOLATED)') == 3, 'negative hold witnesses must remain visible'
        record('collect', [provider, 'collect', run, '--stdout', '--json'])
        record('report', [provider, 'report', run, '--json'], (0, 1))
        record('archive-list', [provider, 'archive', run, '--list'])
        archive = output / 'archive-output'
        record('archive', [provider, 'archive', run, '--output', archive, '--json'])
        # Provider archives are portable source closures; extraction is a new copy.
        restore = output / 'restored'
        restore.mkdir()
        for path in archive.rglob('*.tar.gz'):
            with tarfile.open(path) as stream:
                stream.extractall(restore, filter='data')
        for source in (restore / 'bundle').rglob('*'):
            if source.is_file():
                destination = restore / 'project' / source.relative_to(restore / 'bundle')
                if not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
        for name in ('run.json', 'results.json', 'preflight.json'):
            if (archive / name).exists():
                shutil.copyfile(archive / name, restore / name)
        restored = record('restore-inspect', [provider, 'timing-intent-inspect', restore, '--kind', 'coarse_run', '--json'], (1,))
        restored_view = json.loads((restored / 'stdout.log').read_text())
        assert restored_view == view, 'restored retained-source evidence differs'
        record('restore-collect', [provider, 'collect', restore, '--stdout', '--json'])
        record('restore-report', [provider, 'report', restore, '--json'], (0, 1))
        (output / 'original-run-hashes.json').write_text(json.dumps(original, indent=2) + '\n')
        changed = [name for name, value in original.items() if sha(run / name) != value]
        assert not changed, changed
        (output / 'read-only-verification.json').write_text(json.dumps({'verified_files': len(original), 'changed': changed}, indent=2) + '\n')


if __name__ == '__main__':
    main()
