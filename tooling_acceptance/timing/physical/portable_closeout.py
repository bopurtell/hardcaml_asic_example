#!/usr/bin/env python3
"""Archive-only closeout; preserve execution provenance and all original bytes."""
import argparse
import json
from pathlib import Path
import shutil

from commands import ROOT, STORE, command, identity, inventory, sha, write_new

ARCHIVE_SOURCE_HASH = '4c86b6516f31b0c1c18a07364ab85b7c38a9122633debec2cafeac93befb415d'
EXECUTION = '4856e6af993642988c18c07f47a8c689'
REPORTS = ['40-openroad-checkantennas/reports/antenna.rpt',
           '40-openroad-checkantennas/reports/antenna_summary.rpt',
           '46-openroad-checkantennas-1/reports/antenna.rpt',
           '46-openroad-checkantennas-1/reports/antenna_summary.rpt',
           '62-magic-drc/reports/drc.magic.rpt',
           '66-netgen-lvs/reports/lvs.netgen.json',
           '66-netgen-lvs/reports/lvs.netgen.rpt']


def seal(root):
    return {'files': inventory(root), 'symlinks': {
        str(p.relative_to(root)): str(p.readlink()) for p in sorted(root.rglob('*')) if p.is_symlink()}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('snapshot', 'archive'))
    p.add_argument('--attempt', required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--generation', type=Path)
    p.add_argument('--snapshot', type=Path)
    a = p.parse_args()
    assert a.attempt and Path(a.attempt).name == a.attempt
    run = a.run.resolve(strict=True)
    assert run.is_relative_to(STORE / 'full-runs')
    output = STORE / 'evidence' / a.attempt
    output.mkdir(parents=True, exist_ok=False)
    baseline_public = STORE / 'evidence/full-public-01'
    if a.phase == 'snapshot':
        documentation = {}
        for name in ('docs/timing_physical_findings.md', 'docs/timing_physical_full_result.md', 'tooling_acceptance/timing/physical/README.md'):
            source = ROOT / name
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            assert sha(source) == sha(target)
            documentation[name] = identity(target)
        write_new(output / 'snapshot.json', {'run': str(run), 'run_before': seal(run),
            'original_public': inventory(baseline_public), 'documentation_before': documentation,
            'execution_provider': identity(STORE / 'provider/generations' / EXECUTION / 'receipt.json'),
            'execution_generation': EXECUTION,
            'original_run_record': identity(run / 'run.json'),
            'purpose': 'preserve pre-correction documentation and original actual execution; no EDA'})
        print(json.dumps({'snapshot': str(output / 'snapshot.json'), 'run_files': len(inventory(run))}))
        return
    assert a.generation and a.snapshot
    generation = a.generation.resolve(strict=True)
    assert generation.is_relative_to(STORE / 'provider/generations')
    snapshot = json.loads(a.snapshot.read_text())
    assert snapshot['run'] == str(run) and snapshot['run_before'] == seal(run)
    assert snapshot['original_public'] == inventory(baseline_public)
    source = generation / 'lib/hardcaml_asic/execution/archive/archive_service.ml'
    assert sha(source) == ARCHIVE_SOURCE_HASH
    # The isolated capture receipt binds the source snapshot. Retain the exact
    # installed archive source bytes with this supplemental reader identity.
    shutil.copyfile(source, output / 'archive_service.ml')
    assert sha(output / 'archive_service.ml') == ARCHIVE_SOURCE_HASH
    receipt = json.loads((generation / 'receipt.json').read_text())
    assert generation.name != EXECUTION
    provider = generation / 'bin/hardcaml-asic-flow'
    for label, arguments, expected in (
        ('inspect', ['timing-intent-inspect', run, '--kind', 'coarse_run', '--json'], (0, 1)),
        ('collect', ['collect', run, '--stdout', '--json'], (0,)),
        ('report', ['report', run, '--json'], (0,)),
        ('archive-list', ['archive', run, '--list'], (0,)),
        ('archive', ['archive', run, '--output', output / 'archive-output', '--json'], (0,))):
        code = command(output / label, [provider, *arguments], generation=generation, timeout=300)
        assert code in expected, (label, code)
        if label in ('inspect', 'collect', 'report'):
            value = json.loads((output / label / 'stdout.log').read_text())
            original = json.loads((baseline_public / label / 'stdout.log').read_text())
            assert value == original, f'corrected reader {label} differs from original execution view'
            if label in ('collect', 'report'):
                assert len(value['raw_artifacts']) == 423
        assert seal(run) == snapshot['run_before'], f'{label} modified actual run bytes'
    archive = output / 'archive-output'
    manifest = json.loads((archive / 'archive.json').read_text())
    report_inventory = manifest['verified']['authoritative_report_inventory']
    assert report_inventory['profile'] == 'librelane-native-direct-reports-v1'
    for name in REPORTS:
        assert 'project/runs/asic/' + name in manifest['members'], name
    write_new(output / 'identity-binding.json', {
        'status': 'published', 'run': str(run), 'run_id': manifest['run_id'],
        'build_identity': manifest['build_identity'], 'source_run_record': identity(run / 'run.json'),
        'execution_generation': EXECUTION, 'execution_provider': snapshot['execution_provider'],
        'archive_reader_generation': generation.name, 'archive_reader_provider': identity(generation / 'receipt.json'),
        'archive_reader_snapshot_sha256': receipt['snapshot_sha256'],
        'archive_source': identity(output / 'archive_service.ml'), 'expected_archive_source_sha256': ARCHIVE_SOURCE_HASH,
        'archive_files': {str(p.relative_to(archive)): identity(p) for p in sorted(archive.iterdir()) if p.is_file()},
        'all_seven_reports_selected': True, 'advertised_raw_artifacts': 423,
        'actual_run_bytes_unchanged': seal(run) == snapshot['run_before'],
        'original_public_and_archive_unchanged': inventory(baseline_public) == snapshot['original_public'],
        'new_eda_or_postcheck_execution': False,
        'full_attempts': 1, 'authoritative_report_inventory': report_inventory})
    print(json.dumps({'status': 'published', 'archive': str(archive), 'source_hash': ARCHIVE_SOURCE_HASH,
                      'reader_generation': generation.name, 'members': len(manifest['members']),
                      'raw_artifacts': 423, 'execution_generation': EXECUTION}))


if __name__ == '__main__':
    main()
