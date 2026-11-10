#!/usr/bin/env python3
"""Independent assertions over actual public full evidence and native sources."""
import argparse
import json
from pathlib import Path

from commands import STORE, identity, sha, write_new


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--public', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run, public = a.run.resolve(strict=True), a.public.resolve(strict=True)
    assert run.is_relative_to(STORE) and public.is_relative_to(STORE)
    assert a.output.resolve().is_relative_to(STORE)
    view = json.loads((public / 'inspect/stdout.log').read_text())
    report = json.loads((public / 'report/stdout.log').read_text())
    collected = json.loads((public / 'collect/stdout.log').read_text())
    assert report['timing_intent'] == collected['timing_intent'] == view
    assert json.loads((public / 'report-exit.json').read_text())['exit_code'] == 0
    assert view['status'] == 'completed' and view['stage'] == 'post_pnr'
    expected = ['nom_fast_1p32V_m40C', 'nom_slow_1p08V_125C', 'nom_typ_1p20V_25C']
    assert view['configured_corners'] == view['requested_corners'] == view['executed_corners'] == expected
    assert view['equivalent_corners'] == [] and view['qualification_corner_coverage'] == 'complete'
    assert view['all_corner_timing_goal'] == 'pass' and view['verdict'] == 'unavailable'
    for ref in view['sources']:
        assert sha(run / ref['path']) == ref['sha256'], ref['path']
    record = json.loads((run / 'run.json').read_text())
    assert record['resource_limits'] == {'container_cpus': 6, 'sta_workers': 1, 'tool_workers': 6}
    assert record['implementation_process']['succeeded']
    assert all(c['status'] == 'removed-or-absent' for c in record['container_cleanup'])
    effective = json.loads((run / 'timing-intent/effective-config.json').read_text())
    assert effective['STA_THREADS'] == effective['OPENROAD_THREADS'] == 1
    terminal = json.loads((run / 'timing-intent/transport-result.json').read_text())
    assert terminal['succeeded'] and terminal['cleanup_error'] is None
    state = run / view['implementation']['state']['path']
    assert state.name == 'state_in.json' and state.parent.name == '55-openroad-stapostpnr'
    assert json.loads(state.read_text()) == json.loads((run / 'timing-intent/corners/state_in.json').read_text())
    corners = []
    stage_inventory = None
    for row in view['corners']:
        corner = row['corner']
        evidence, timing = row['evidence'], row['timing']
        assert evidence['provenance']['schema'] == 3 and evidence['provenance']['stage'] == 'post_pnr'
        stages = evidence['resolved']['stages']
        assert len(stages) == len({s['cell'] for s in stages}) == 5
        topology = evidence['resolved']['physical_topology']
        assert set(topology['sequential_inventory']) == {s['cell'] for s in stages}
        if stage_inventory is None:
            stage_inventory = stages
        else:
            assert stage_inventory == stages
        native = evidence['native_coverage']
        assert native['stored_exception_scope']['status'] == 'matched'
        assert native['stored_exception_scope']['relation_count'] == 6
        # Native CTS adds one combinational clock-load output endpoint; it is
        # not an architectural register and is retained in the native inventory.
        expected_endpoints = {s['data_pin'] for s in stages} | {s['async_pin'] for s in stages} | {
            'uo_out[0]', 'uo_out[1]', 'clkload0/Y'}
        assert native['endpoints']['count'] == 13
        assert set(native['endpoints']['pins']) == expected_endpoints
        assert len(native['diagnostics']['categories']) == 7
        assert all(not c['groups'] for c in native['diagnostics']['categories'])
        assert native['exhaustive_exception_effect'] == 'unavailable'
        assert all(timing[key] == 'pass' for key in ('setup_goal', 'hold_goal', 'electrical_goal', 'annotation_goal'))
        metrics = {m['key']: m for m in timing['metrics']}
        assert all(m['availability'] == 'available' for m in metrics.values())
        for key in ('setup_slack', 'hold_slack'):
            assert metrics[key]['value'] >= 0 and metrics[key]['unit'] == 'ns'
        for key in ('setup_violations', 'hold_violations', 'max_slew_violations', 'max_cap_violations'):
            assert metrics[key]['value'] == 0 and metrics[key]['unit'] == 'count'
        directory = run / 'timing-intent/corners' / corner
        process = json.loads((directory / 'process-result.json').read_text())
        assert process['exit_code'] == 0 and process['argv'][:3] == ['sta', '-threads', '1']
        clocks = json.loads((directory / 'clock-state.json').read_text())
        assert clocks == {'schema': 1, 'all_propagated': 1, 'clocks': ['clk']}
        assert row['inputs']['environment']['OPENLANE_SDC_IDEAL_CLOCKS'] == '0'
        spef = next(r for r in row['inputs']['associations'] if r['role'] == 'spef')
        assert sha(run / spef['retained']['path']) == spef['retained']['sha256']
        for mode in ('min', 'max'):
            raw = (directory / ('downstream_' + mode + '.rpt')).read_text()
            assert raw.count('Startpoint:') == 3 and raw.count('slack (MET)') == 3
        corners.append({'corner': corner, 'metrics': {k: v['value'] for k, v in metrics.items()},
                        'timing': timing, 'spef': spef, 'clock_state': clocks,
                        'downstream_min': identity(directory / 'downstream_min.rpt'),
                        'downstream_max': identity(directory / 'downstream_max.rpt')})
    checks = collected['postchecks']
    assert len(checks) == 1 and checks[0]['status'] == 'completed'
    check = checks[0]
    assert check['checks'] == {'gate_level': 'pass', 'precheck': 'pass'}
    check_files = list((run / 'checks').glob('*/postcheck.json'))
    assert len(check_files) == 1
    directory = check_files[0].parent
    assert 'checks=512' in (directory / 'postcheck.log').read_text()
    assert check['tools']['replay_profile'] == 'cmos5l_physical_timing_used_cells_v1'
    models = json.loads((directory / 'replay-models.json').read_text())
    netlist = run / view['implementation']['netlist']['path']
    assert models['netlist_sha256'] == sha(netlist) == check['inputs']['netlist_sha256']
    assert models['claim'] == 'zero_delay_digital_functional_only_not_vendor_timing_or_sdf_conformance'
    for name, digest in check['artifacts'].items():
        assert sha(directory / name) == digest
    hops = {}
    paths = []
    for trace in view['corners'][0]['evidence']['resolved']['physical_topology']['traces']:
        paths.append({'label': trace['label'], 'root': trace['root'], 'sink': trace['sink'], 'hops': len(trace['hops'])})
        for hop in trace['hops']:
            hops[hop['cell']] = hop
    result = {'native_and_public_assertions': 'passed', 'run_id': record['run_id'],
        'build_identity': record['build_identity'], 'full_attempts': 1,
        'stage_inventory': stage_inventory, 'sequential_count': 5, 'corners': corners,
        'qualified_transform_inventory': list(hops.values()), 'checked_paths': paths,
        'physical_chain': view['physical_chain'], 'selected_implementation_input': view['implementation'],
        'normal_postcheck': identity(check_files[0]), 'postcheck_checks': check['checks'],
        'functional_observations': 512, 'physical_checks': collected['checks'],
        'public_report_exit_code': 0, 'archive_full_replay': 'pending_seven_report_omission_fix'}
    write_new(a.output, result)
    print(json.dumps({'native_and_public_assertions': 'passed', 'sequential_count': 5,
        'corners': [{'corner': c['corner'], 'metrics': c['metrics']} for c in corners],
        'postcheck_checks': check['checks'], 'qualified_unique_transforms': len(hops),
        'maximum_checked_hops': max(p['hops'] for p in paths)}, indent=2))


if __name__ == '__main__':
    main()
