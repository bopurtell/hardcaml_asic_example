#!/usr/bin/env python3
"""Seal actual named acceptance: association, native witnesses and resource receipts."""
import argparse
import json
from pathlib import Path
import re
import stat

from pt7named_acceptance import EVIDENCE, ROOT, inventory, sha, write_new


def load(path):
    return json.loads(path.read_text())


def ref(path):
    return {'path': str(path), 'sha256': sha(path)}


def witness_lines(path):
    # Quote native report values for this acceptance receipt only. Provider owns
    # all timing interpretation; these bounded witnesses are not timing closure.
    return [{'line': index, 'text': line.strip(), 'slack': match.group(1),
             'native_result': match.group(2)}
            for index, line in enumerate(path.read_text().splitlines(), 1)
            if (match := re.search(r'([-+0-9.]+)\s+slack \((MET|VIOLATED)\)', line))]


def profile_result(profile, execution, preparation, public_dir, preflight, run_dir):
    record = load(execution)
    prepared = load(preparation)
    view = load(public_dir / 'inspect/stdout.log')
    report = load(public_dir / 'report/stdout.log')
    sources = load(public_dir / 'sources/stdout.log')
    assert report['timing_intent'] == view and sources == view['sources']
    assert record['status'] == 'completed' and record['exit_code'] == 0
    assert len(record['occurrences']) == len(record['artifacts']) == 1
    occurrence = record['occurrences'][0]
    assert occurrence['status'] == 'completed' and occurrence['action_key'] == 'implementation.synthesis'
    assert record['plan'] == {'schema_version': 4, 'initial_boundary': None, 'stages': ['synthesis']}
    assert record['methodology']['plan_identity'] == prepared['plan_identity']
    assert record['methodology']['bundle_identity'] == prepared['bundle_identity']
    assert inventory(Path(prepared['bundle'])) == prepared['bundle_inventory']
    assert sha(Path(prepared['plan_file'])) == prepared['plan_sha256']
    assert load(Path(record['methodology']['snapshot_path'])) == load(Path(prepared['plan_file']))

    expectation = record['timing_intent']
    analysis = Path(expectation['directory'])
    publication = load(Path(expectation['publication']))
    checkpoint = Path(record['artifacts'][0]['path'])
    checkpoint_manifest = load(checkpoint / 'manifest.json')
    assert publication['checkpoint'] == record['artifacts'][0]
    assert publication['expectation'] == expectation
    assert publication['occurrence']['status'] == 'running'
    assert publication['occurrence']['occurrence_id'] == occurrence['occurrence_id']
    assert publication['request']['operation'] == 'execute_segment'
    assert publication['request']['boundary'] == 'synthesis'
    assert load(analysis / 'request.json')['state_path'] == str(checkpoint / 'state.json')
    assert load(analysis / 'corners/state_in.json') == load(checkpoint / 'state.json')
    checkpoint_rows = [row for row in publication['sources']
                       if row['path'].startswith(str(checkpoint) + '/')]
    assert len(checkpoint_rows) == len(checkpoint_manifest['files']) + 1
    for row in checkpoint_rows:
        assert sha(Path(row['path'])) == row['sha256'], row['path']

    by_path = {row['path']: row for row in sources}
    assert len(by_path) == len(sources)
    for row in sources:
        assert sha(Path(row['path'])) == row['sha256'], row['path']
    for path, member in checkpoint_manifest['external'].items():
        if not path.startswith('/nix/store/'):
            assert by_path[path]['sha256'] == member['sha256'], path
    aliases = publication['external_aliases']
    assert len(aliases) == 1062
    for row in aliases:
        path = Path(row['path'])
        assert str(path.resolve(strict=True)) == row['target']
        assert path.stat().st_size == row['bytes']
        assert sha(path) == row['sha256'] == by_path[str(path)]['sha256']
        assert checkpoint_manifest['external'][str(path)]['sha256'] == row['sha256']
    gds = ROOT / '_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_io/gds/sg13cmos5l_io.gds'
    assert gds.stat().st_size == 67485696 and str(gds) in by_path
    pdk_rows = [row for row in sources if row['path'].startswith(str(ROOT / '_flow_tools/pdk/ihp-sg13cmos5l') + '/')]
    assert len(pdk_rows) == 1486

    # Explicitly selected metadata directory: exact expectation equality establishes
    # association; no recency or directory-name selection is used.
    early_rows = []
    for name in ('operation.json', 'preflight.json', 'prepared.json'):
        path = preflight / name
        early = load(path)
        assert early['timing_intent'] == expectation
        assert early['request']['timing_intent'] == expectation
        assert early['request']['workspace'] == str(execution.parent)
        snapshot_ref = early['timing_intent_snapshot']
        assert early['request']['timing_intent_snapshot'] == snapshot_ref
        snapshot = Path(snapshot_ref['path'])
        assert sha(snapshot) == snapshot_ref['sha256'] and load(snapshot) == expectation
        assert stat.S_IMODE(snapshot.stat().st_mode) == 0o400
        assert snapshot.stat().st_mtime_ns <= (preflight / 'probe-1.json').stat().st_mtime_ns
        early_rows.append(ref(path))
    assert load(preflight / 'operation.json')['request']['probe_timeout_seconds'] == 20
    assert load(preflight / 'operation.json')['request']['timeout_seconds'] == 600

    launch_rows = []
    for path in sorted(preflight.glob('probe-*.json')):
        probe = load(path)
        assert probe['succeeded'] and probe['cleanup_error'] is None
        argv = probe['argv']
        container = len(argv) > 1 and argv[1] == 'run'
        if container:
            assert argv.count('--cpus=6') == 1
        launch_rows.append({**ref(path), 'phase': 'preflight_probe',
                            'timeout_seconds': 20, 'container_cpu_limit': 6 if container else None,
                            'host_thread_environment': 'OMP/OPENBLAS/MKL=1' if not container else None})
    for path in sorted(execution.parent.glob('*-transport.json')):
        launch = load(path)
        assert launch['argv'].count('--cpus=6') == 1
        launch_rows.append({**ref(path), 'phase': 'publication_validation' if path.name.startswith('validate-') else 'synthesis',
                            'container_cpu_limit': 6, 'workers': 6, 'timeout_seconds': 600})
    transport = load(analysis / 'transport.json')
    terminal = load(analysis / 'transport-result.json')
    assert transport['workers'] == 6 and transport['sta_threads'] == 1
    assert transport['argv'].count('--cpus=6') == 1
    assert terminal['succeeded'] and terminal['code'] == 0 and terminal['cleanup_error'] is None
    launch_rows.append({**ref(analysis / 'transport.json'), 'phase': 'linked_sta',
                        'container_cpu_limit': 6, 'workers': 6, 'sta_threads': 1,
                        'timeout_seconds': transport['timeout_seconds'], 'terminal': ref(analysis / 'transport-result.json')})

    assert view['status'] == 'completed' and view['verdict'] == 'unavailable'
    assert view['requested_corners'] == view['executed_corners'] == ['nom_typ_1p20V_25C']
    audit = view['corners'][0]
    assert audit['schema'] == 2 and audit['native_coverage']['profile'] == 'opensta-2.7-native-state-v2'
    corner = analysis / 'corners' / view['executed_corners'][0]
    native_inputs = load(corner / 'native-inputs.json')
    libs = native_inputs['libraries']
    assert len(libs) == 2
    for index, library in enumerate(libs):
        path = Path(library['actual_path'])
        assert path == corner / f'library-{index}.lib'
        assert sha(path) == library['retained']['sha256']
    process = load(corner / 'process-result.json')
    assert process['exit_code'] == 0 and process['argv'][:3] == ['sta', '-threads', '1']
    version = load(corner / 'version-process.json')
    assert version['exit_code'] == 0 and version['argv'] == ['sta', '-version']
    assert (corner / 'producer-version.txt').read_text().strip() == '2.7.0'
    minimum = witness_lines(corner / 'downstream_min.rpt')
    maximum = witness_lines(corner / 'downstream_max.rpt')
    assert len(minimum) == len(maximum) == 3
    assert all(float(row['slack']) < 0 and row['native_result'] == 'VIOLATED' for row in minimum)
    assert all(row['native_result'] == 'MET' for row in maximum)
    return {'profile': profile, 'execution': ref(execution), 'attempt_id': record['attempt_id'],
            'preparation': ref(preparation), 'plan_identity': prepared['plan_identity'],
            'bundle_identity': prepared['bundle_identity'], 'checkpoint': record['artifacts'][0],
            'checkpoint_before_sta_sources': checkpoint_rows, 'checkpoint_unchanged_after_sta': True,
            'native_step_input_is_published_state': True, 'early_metadata': early_rows,
            'early_snapshot': snapshot_ref, 'publication': ref(Path(expectation['publication'])),
            'analysis': ref(analysis / 'analysis.json'), 'sources': ref(public_dir / 'sources/stdout.log'),
            'verified_source_count': len(sources), 'full_pdk_source_count': len(pdk_rows),
            'declared_alias_count': len(aliases), 'large_gds': by_path[str(gds)],
            'native_process': ref(corner / 'process-result.json'), 'version_process': ref(corner / 'version-process.json'),
            'opensta_version': '2.7.0', 'libraries_in_native_order': libs,
            'corner': view['executed_corners'][0], 'configured_corners': view['original_corners'],
            'bounded_hold_witnesses': minimum, 'bounded_setup_witnesses': maximum,
            'witness_units': 'ns; native Liberty time_unit=1ns',
            'downstream_min': ref(corner / 'downstream_min.rpt'), 'downstream_max': ref(corner / 'downstream_max.rpt'),
            'report_inspect_equal': True, 'public_source_inventory_equal': True, 'launches': launch_rows,
            'run_command': ref(run_dir / 'stages/command.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    for profile in ('area', 'delay'):
        for argument in ('execution', 'preparation', 'public', 'preflight', 'run'):
            parser.add_argument(f'--{profile}-{argument}', type=Path, required=True)
    parser.add_argument('--negatives', type=Path, required=True)
    args = parser.parse_args()
    output = EVIDENCE / args.attempt
    output.mkdir(exist_ok=False)
    results = [profile_result(profile, *(getattr(args, f'{profile}_{field}').resolve(strict=True)
                for field in ('execution', 'preparation', 'public', 'preflight', 'run')))
               for profile in ('area', 'delay')]
    assert results[0]['attempt_id'] != results[1]['attempt_id']
    assert results[0]['bundle_identity'] != results[1]['bundle_identity']
    assert results[0]['checkpoint']['identity'] != results[1]['checkpoint']['identity']
    negatives = load(args.negatives)
    assert negatives['original_sources_unchanged']
    assert len(negatives['controls']) == 6
    commands = [load(Path(row['run_command']['path'])) for row in results]
    write_new(output / 'acceptance.json', {
        'status': 'actual_bounded_named_synthesis_accepted', 'profiles': results,
        'negative_controls': ref(args.negatives.resolve()), 'native_synthesis_runs': 2,
        'native_linked_sta_runs': 2, 'pnr_runs': 0, 'global_allocation_jobs': 6,
        'run_elapsed_seconds': [row['elapsed_seconds'] for row in commands],
        'read_only_public_queries': True, 'closure_scope': 'path_bound',
        'negative_hold_preserved': True, 'timing_closure': 'not_established',
        'exhaustive_exception_effect': 'unavailable', 'named_archive_relocation': 'unsupported'})


if __name__ == '__main__':
    main()
