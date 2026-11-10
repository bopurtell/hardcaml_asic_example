#!/usr/bin/env python3
"""Check public all-configured synthesis evidence; no local STA interpretation."""
import argparse
import json
from pathlib import Path

from commands import STORE, sha, write_new


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inspection', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--run', type=Path)
    a = p.parse_args()
    view = json.loads(a.inspection.read_text())
    result = {k: view[k] for k in ('status', 'stage', 'configured_corners', 'requested_corners',
              'executed_corners', 'equivalent_corners', 'qualification_corner_coverage', 'all_corner_timing_goal')}
    expected = ['nom_fast_1p32V_m40C', 'nom_slow_1p08V_125C', 'nom_typ_1p20V_25C']
    assert view['status'] == 'completed' and view['stage'] == 'synthesized_netlist'
    assert view['configured_corners'] == view['requested_corners'] == view['executed_corners'] == expected
    assert view['equivalent_corners'] == [] and view['qualification_corner_coverage'] == 'complete'
    assert view['all_corner_timing_goal'] == 'fail', 'baseline negative hold must remain visible'
    run = a.run.resolve(strict=True) if a.run else None
    if run:
        record = json.loads((run / 'run.json').read_text())
        assert record['resource_limits'] == {'container_cpus': 6, 'sta_workers': 1, 'tool_workers': 6}
        assert all(c['status'] == 'removed-or-absent' for c in record['container_cleanup'])
        assert record['implementation_process']['succeeded']
        argv = record['implementation_process']['argv']
        assert argv[argv.index('--jobs') + 1] == '6'
        for flag in ('OPENROAD_THREADS=6', 'STA_THREADS=1', 'KLAYOUT_DRC_THREADS=6', 'KLAYOUT_XOR_THREADS=6'):
            assert flag in argv
        effective = json.loads((run / 'timing-intent/effective-config.json').read_text())
        assert effective['STA_THREADS'] == effective['OPENROAD_THREADS'] == 1
        terminal = json.loads((run / 'timing-intent/transport-result.json').read_text())
        assert terminal['succeeded'] and terminal['cleanup_error'] is None
        result['limits_and_cleanup'] = 'verified_implementation6_linked_sta1'
    expected_hashes = {'nom_fast_1p32V_m40C': 'af12d75a72d19648fa690027d29843fbae550aa91f4e40dd3339c7116d6e425d',
                       'nom_slow_1p08V_125C': '3ee222c580ba33acb2131ac2bf224ff8ee9700751835b73aaec72b670bb31d3c',
                       'nom_typ_1p20V_25C': '34163f3e7de9f854afac57332ba06f1739b78e7ac35660a8a5ddd39c570124ad'}
    result['corners'] = []
    for row in view.get('corners', []):
        evidence = row.get('evidence', {})
        corner = row['corner']
        stages = evidence['resolved']['stages']
        assert len(stages) == len({s['cell'] for s in stages}) == 5
        assert all(s['master'] == 'sg13cmos5l_dfrbpq_1' for s in stages)
        assert set(evidence['resolved']['physical_topology']['sequential_inventory']) == {s['cell'] for s in stages}
        native = evidence['native_coverage']
        assert native['profile'] == 'opensta-2.7-native-state-v2'
        assert native['stored_exception_scope']['status'] == 'matched'
        assert native['stored_exception_scope']['relation_count'] == 6
        assert native['endpoints']['count'] == 12
        categories = native['diagnostics']['categories']
        assert len(categories) == 7 and all(not c['groups'] for c in categories)
        assert native['exhaustive_exception_effect'] == 'unavailable'
        timing = row['timing']
        metrics = {m['key']: m for m in timing['metrics']}
        assert all(m['availability'] == 'available' for m in metrics.values())
        assert metrics['setup_slack']['value'] > 0 and metrics['hold_slack']['value'] < 0
        assert metrics['setup_violations']['value'] == 0 and metrics['hold_violations']['value'] > 0
        assert metrics['max_slew_violations']['value'] == metrics['max_cap_violations']['value'] == 0
        assert timing['setup_goal'] == timing['electrical_goal'] == 'pass' and timing['hold_goal'] == 'fail'
        libs = [r for r in row['inputs']['associations'] if r['role'] == 'liberty']
        assert len(libs) == 2 and libs[0]['retained']['sha256'] == expected_hashes[corner]
        assert 'stdcell' in libs[0]['original_path'] and '_io_' in libs[1]['original_path']
        sources = []
        if run:
            for source in view['sources']:
                assert sha(run / source['path']) == source['sha256']
            directory = run / 'timing-intent/corners' / corner
            process = json.loads((directory / 'process-result.json').read_text())
            assert process['exit_code'] == 0 and process['argv'][:3] == ['sta', '-threads', '1']
            for mode in ('min', 'max'):
                report = directory / ('downstream_' + mode + '.rpt')
                assert report.read_text().count('Startpoint:') == 3
                sources.append({'path': str(report), 'sha256': sha(report)})
            assert row['inputs']['environment']['OPENLANE_SDC_IDEAL_CLOCKS'] == '1'
        result['corners'].append({'corner': corner, 'stages': stages,
             'sequential_count': 5, 'native_relations': 6, 'native_endpoints': 12,
             'diagnostic_categories': 7, 'diagnostic_groups': 0,
             'libraries': libs, 'timing': timing, 'downstream_reports': sources})
    result['baseline_assertions'] = 'passed'
    result['closure'] = 'failed_hold_not_qualified'
    output = a.output.resolve()
    assert output.is_relative_to(STORE)
    write_new(output, result)
    print(json.dumps({'baseline_assertions': 'passed', 'corners': [
        {'corner': row['corner'], 'metrics': {m['key']: m['value'] for m in row['timing']['metrics']}}
        for row in result['corners']]}, indent=2))


if __name__ == '__main__':
    main()
