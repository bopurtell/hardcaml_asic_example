#!/usr/bin/env python3
"""Restore ordinary archive and replay public readers with original inputs hidden."""
import argparse
import json
from pathlib import Path
import shutil
import tarfile

from commands import ROOT, STORE, command, inventory, sha, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--public', type=Path, required=True)
    args = parser.parse_args()
    if not args.attempt or Path(args.attempt).name != args.attempt:
        parser.error('attempt must be a single directory name')
    generation = args.generation.resolve(strict=True)
    public = args.public.resolve(strict=True)
    assert generation.is_relative_to(STORE / 'provider/generations')
    assert public.is_relative_to(STORE)
    output = STORE / 'evidence' / args.attempt
    output.mkdir(parents=True, exist_ok=False)
    archive = public / 'archive-output'
    archived = inventory(archive)
    restored = output / 'restored'
    restored.mkdir()
    for path in sorted(archive.rglob('*.tar.gz')):
        with tarfile.open(path) as stream:
            stream.extractall(restored, filter='data')
    # Archive members use bundle/; the coarse reader's immutable staged bundle
    # is project/. Materialize identical archived bytes, never rerender them.
    for path in (restored / 'bundle').rglob('*'):
        if path.is_file():
            destination = restored / 'project' / path.relative_to(restored / 'bundle')
            if destination.exists():
                assert sha(destination) == sha(path)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
    for name in ('run.json', 'preflight.json', 'results.json'):
        source = archive / name
        if source.exists() and not (restored / name).exists():
            shutil.copyfile(source, restored / name)
    # Public archives store postcheck records as loose files, alongside reports
    # tar members under checks/<id>/. Reassemble those exact archived bytes at
    # the original run-relative location before invoking the normal readers.
    check_dirs = sorted(p for p in (restored / 'checks').glob('*') if p.is_dir())
    for source in sorted(archive.glob('postcheck*.json')):
        if source.name == 'postcheck.json':
            assert len(check_dirs) == 1, 'single archived postcheck must have one retained check directory'
            directory = check_dirs[0]
        else:
            check_id = source.name.removeprefix('postcheck-').removesuffix('.json')
            directory = restored / 'checks' / check_id
            assert directory in check_dirs, 'postcheck record has no matching retained directory'
        destination = directory / 'postcheck.json'
        assert not destination.exists()
        shutil.copyfile(source, destination)
    before = inventory(restored)
    prefix = ['bwrap', '--ro-bind', '/', '/', '--unshare-user', '--unshare-pid',
              '--unshare-net', '--die-with-parent', '--tmpfs', str(ROOT),
              '--tmpfs', str(ROOT.parent / 'hardcaml_asic'),
              '--ro-bind', str(generation), str(generation),
              '--ro-bind', str(restored), str(restored), '--chdir', '/tmp', '--']
    parity = {}
    for label, arguments in (
            ('inspect', ['timing-intent-inspect', restored, '--kind', 'coarse_run', '--json']),
            ('collect', ['collect', restored, '--stdout', '--json']),
            ('report', ['report', restored, '--json'])):
        argv = prefix + [str(generation / 'bin/hardcaml-asic-flow'), *map(str, arguments)]
        code = command(output / label, argv, generation=generation, timeout=180)
        assert code in ((0, 1) if label in ('inspect', 'report') else (0,)), (label, code)
        baseline = json.loads((public / label / 'stdout.log').read_text())
        actual = json.loads((output / label / 'stdout.log').read_text())
        parity[label] = actual == baseline
    assert inventory(archive) == archived
    assert inventory(restored) == before
    passed = all(parity.values())
    write_new(output / 'summary.json', {'status': 'passed' if passed else 'failed', 'restored': str(restored),
              'files': len(before), 'archive_inventory': archived,
              'original_example_and_pdk_hidden': True, 'original_asic_source_hidden': True,
              'restored_readonly': True, 'public_inspect_collect_report_equal': passed, 'parity': parity})
    print(json.dumps({'status': 'passed' if passed else 'failed', 'restored': str(restored),
                      'files': len(before), 'parity': parity}))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
