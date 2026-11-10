#!/usr/bin/env python3
"""Verify every restored advertised byte and bind actual resource accounting."""
import argparse
import json
from pathlib import Path

from commands import ROOT, STORE, identity, inventory, sha, write_new
from portable_closeout import seal


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--public', type=Path, required=True)
    p.add_argument('--restoration', type=Path, required=True)
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    public, restoration = a.public.resolve(strict=True), a.restoration.resolve(strict=True)
    assert public.is_relative_to(STORE) and restoration.is_relative_to(STORE)
    assert a.output.resolve().is_relative_to(STORE)
    snapshot = json.loads(a.snapshot.read_text())
    run = Path(snapshot['run'])
    before = snapshot['run_before']
    assert seal(run) == before
    assert inventory(STORE / 'evidence/full-public-01') == snapshot['original_public']
    restored = restoration / 'restored'
    replay = json.loads((restoration / 'summary.json').read_text())
    assert replay['status'] == 'passed' and all(replay['parity'].values())
    assert replay['original_example_and_pdk_hidden'] and replay['original_asic_source_hidden']
    artifact_paths = None
    for label in ('inspect', 'collect', 'report'):
        actual = json.loads((restoration / label / 'stdout.log').read_text())
        original = json.loads((STORE / 'evidence/full-public-01' / label / 'stdout.log').read_text())
        assert actual == original
        if label in ('collect', 'report'):
            assert len(actual['raw_artifacts']) == len(set(actual['raw_artifacts'])) == 423
            artifact_paths = actual['raw_artifacts']
    archive = public / 'archive-output'
    manifest = json.loads((archive / 'archive.json').read_text())
    assert len(manifest['members']) == 449
    verified = {}
    for name in manifest['members']:
        path = restored / name
        assert path.resolve(strict=True).is_relative_to(restored)
        assert sha(path) == before['files'][name], name
        verified[name] = identity(path)
    for name in artifact_paths:
        assert sha(restored / name) == before['files'][name], name
    bundle_manifest = json.loads((restored / 'project/manifest.json').read_text())
    for row in bundle_manifest['files']:
        assert sha(restored / 'project' / row['path']) == row['sha256']
    assert sha(archive / 'input-bundle.tar.gz') == manifest['input_bundle']['sha256']
    assert sha(restored / 'run.json') == snapshot['original_run_record']['sha256']
    threads = []
    flow = run / 'project/runs/asic'
    for directory, expected in (('31-openroad-stamidpnr', 1), ('36-openroad-stamidpnr-1', 6),
                                 ('38-openroad-stamidpnr-2', 6), ('43-openroad-stamidpnr-3', 6)):
        source = flow / directory / 'COMMANDS'
        raw = source.read_text()
        assert raw.startswith(f'openroad -exit -threads {expected} ')
        assert sha(source) == before['files'][str(source.relative_to(run))]
        threads.append({'stage': directory, 'tool': 'OpenROAD', 'requested_threads': expected,
                        'native_command_source': identity(source), 'native_command': raw.rstrip()})
    for directory in ('12-openroad-staprepnr', '55-openroad-stapostpnr'):
        source = flow / directory / 'COMMANDS'
        sta = [line for line in source.read_text().splitlines() if line.startswith('sta ')]
        assert len(sta) == 3 and all(line.startswith('sta -threads 1 ') for line in sta)
        threads.append({'stage': directory, 'tool': 'dedicated all-corner OpenSTA',
                        'requested_threads': 1, 'actual_corner_processes': 3,
                        'native_command_source': identity(source)})
    for corner in ('nom_fast_1p32V_m40C', 'nom_typ_1p20V_25C', 'nom_slow_1p08V_125C'):
        source = run / 'timing-intent/corners' / corner / 'process-result.json'
        process = json.loads(source.read_text())
        assert process['argv'][:3] == ['sta', '-threads', '1'] and process['exit_code'] == 0
        threads.append({'stage': 'linked extracted STA', 'corner': corner, 'tool': 'OpenSTA',
                        'requested_threads': 1, 'process_source': identity(source)})
    review = Path('/tmp/opencode/timing-physical-final-review-3gh6tr27/review.json')
    actual_review = json.loads(review.read_text())
    assert actual_review['assertions'] == 1720 and actual_review['run_id'] == manifest['run_id']
    assert seal(run) == before
    write_new(a.output, {'status': 'passed', 'scope': 'bounded_physical_timing_and_portable_source_closeout',
        'run_id': manifest['run_id'], 'build_identity': manifest['build_identity'],
        'archive_identity_binding': identity(public / 'identity-binding.json'),
        'restoration_summary': identity(restoration / 'summary.json'),
        'public_responses_equal_to_original_execution': True, 'advertised_raw_artifacts': 423,
        'advertised_source_bytes_match_original': True, 'archive_members': 449,
        'restored_files': replay['files'], 'verified_members': verified,
        'thread_accounting': threads,
        'resource_disposition': 'coordinator accepts mid-PNR steps36/38/43 OpenROAD6 within allocation6; no physical repeat',
        'dedicated_all_corner_sta_threads': 1, 'linked_sta_threads': 1,
        'mid_pnr_openroad_threads': {'31': 1, '36': 6, '38': 6, '43': 6},
        'independent_actual_review': identity(review), 'independent_actual_review_assertions': 1720,
        'run_bytes_unchanged': True, 'original_archive_and_public_evidence_unchanged': True,
        'execution_provider_unchanged': snapshot['execution_provider'],
        'full_attempts_used': 1, 'additional_eda': False,
        'critical_inputs': {name: identity(restored / name) for name in (
            'project/manifest.json', 'project/constraints/top.sdc',
            'project/runs/asic/final/nl/tt_um_pt7_timing.nl.v')},
        'archive_files': {str(f.relative_to(archive)): identity(f) for f in sorted(archive.iterdir()) if f.is_file()}})
    print(json.dumps({'status': 'passed', 'raw_artifacts': 423, 'verified_archive_members': 449,
                      'restored_files': replay['files'], 'unchanged_run_files': len(before['files']),
                      'reports_sha256': sha(archive / 'reports.tar.gz'),
                      'input_bundle_sha256': sha(archive / 'input-bundle.tar.gz')}, indent=2))


if __name__ == '__main__':
    main()
