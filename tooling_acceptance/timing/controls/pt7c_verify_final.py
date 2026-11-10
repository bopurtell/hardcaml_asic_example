#!/usr/bin/env python3
"""Independent assertions over provider facts, retained sources and launch receipts."""
import argparse
import json
from pathlib import Path
import re

from pt7c_probe import ROOT, digest


def load(path):
    return json.loads(path.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--attempt', required=True)
    p.add_argument('--public', type=Path, required=True)
    p.add_argument('--standalone', type=Path, required=True)
    a = p.parse_args()
    run = a.run.resolve(strict=True)
    output = ROOT / 'acceptance/pt7c' / a.attempt
    output.mkdir(exist_ok=False)
    record = load(run / 'run.json')
    assert record['status'] == 'completed' and record['completed_stage'] == 'synthesis'
    bundle = Path(record['bundle'])
    manifest = load(bundle / 'manifest.json')
    for row in manifest['files']:
        assert digest(bundle / row['path']) == row['sha256'], row['path']
    for row in manifest['source_inputs']:
        assert digest(ROOT / row['path']) == row['sha256'], row['path']
    assert manifest['identity'] == record['build_identity']
    view = load(a.public / 'inspect/stdout.log')
    assert load(a.standalone / 'stdout.log') == view['corners'][0]
    assert load(a.public / 'restore-inspect/stdout.log') == view
    companion = load(run / 'timing-intent/analysis.json')
    for row in companion['sources']:
        assert digest(run / row['path']) == row['sha256'], row['path']
    runtime = load(run / 'timing-intent/runtime-result.json')
    corner = runtime['executed_corners'][0]
    directory = run / 'timing-intent/corners' / corner
    audit = load(directory / 'audit.json')
    assert audit['schema'] == 2
    for row in audit['sources']:
        assert digest(directory / row['path']) == row['sha256'], row['path']
    assert (directory / 'top.sdc').read_bytes() == (bundle / 'constraints/top.sdc').read_bytes()
    assert (directory / 'native-producer.tcl').read_bytes() == (bundle / 'constraints/pt7-native-coverage.tcl').read_bytes()
    assert digest(directory / 'mapped.v') == runtime['synthesis']['netlist']['sha256']
    assert load(directory / 'process-result.json')['exit_code'] == 0
    transport = load(run / 'timing-intent/transport.json')
    assert transport['workers'] == 6 and transport['sta_threads'] == 1
    assert '--cpus=6' in transport['argv']
    assert '--cpus=6' in record['commands'][0]
    assert record['commands'][0][record['commands'][0].index('--to') + 1] == 'Yosys.Synthesis'
    log = (directory / 'sta.log').read_text()
    assert log.count('PT7_AUDIT_RECEIPT ') == 1
    assert log.count('HC_ASIC_TIMING_V1\t{"schema_version":1,"event":"begin"') == 1
    assert log.count('HC_ASIC_NATIVE_V2_COMPLETE') == 1 and log.count('PT7_AUDIT_COMPLETE') == 1
    assert log.index('PT7_AUDIT_RECEIPT ') < log.index('HC_ASIC_TIMING_V1\t') < log.index('HC_ASIC_NATIVE_V2_COMPLETE') < log.index('PT7_AUDIT_COMPLETE')
    assert view['corners'][0]['native_coverage']['native_design'] == manifest['top_module']
    assert load(directory / 'native-data.json')['schema'] == 2
    native_inputs = load(directory / 'native-inputs.json')
    assert native_inputs['PT7_CORNER_SCRIPT'] == str(directory / 'librelane-corner.tcl')
    assert digest(run / native_inputs['corner_script']['path']) == native_inputs['corner_script']['sha256']
    assert len(native_inputs['libraries']) == len([r for r in audit['sources'] if r['role'] == 'liberty'])
    slacks = {}
    for mode in ('min', 'max'):
        text = (directory / ('downstream_' + mode + '.rpt')).read_text()
        values = [float(x) for x in re.findall(r'^\s*([-+0-9.]+)\s+slack \(', text, re.M)]
        assert len(values) == 3
        assert all(x < 0 for x in values) if mode == 'min' else all(x > 0 for x in values)
        slacks[mode] = values
    # Prove preliminary failed companion and its advertised sources stayed intact.
    failed = ROOT / '.dev/asic-pt7c/probe-runs/20261028T164800799130Z_44ded577'
    old_companion = load(failed / 'timing-intent/analysis.json')
    for row in old_companion['sources']:
        assert digest(failed / row['path']) == row['sha256'], row['path']
    assert load(failed / 'run.json')['status'] == 'failed'
    assert load(failed / 'timing-intent/corners/nom_typ_1p20V_25C/process-result.json')['exit_code'] == 1
    # Verify every recorded outer command stream against its launch-time digest.
    command_receipts = 0
    for path in (ROOT / 'acceptance/pt7c').rglob('command.json'):
        receipt = load(path)
        for name, value in receipt['logs'].items():
            assert digest(path.parent / name) == value, str(path)
        command_receipts += 1
    run_hashes = {str(path.relative_to(run)): digest(path) for path in run.rglob('*') if path.is_file()}
    (output / 'run-files.json').write_text(json.dumps(run_hashes, indent=2) + '\n')
    summary = {
        'run': str(run), 'run_id': record['run_id'], 'build_identity': manifest['identity'],
        'manifest_sha256': digest(bundle / 'manifest.json'), 'audit_sha256': digest(directory / 'audit.json'),
        'native_sdc_sha256': digest(directory / 'native-state.sdc'),
        'emitted_sdc_sha256': digest(directory / 'top.sdc'), 'mapped_netlist_sha256': digest(directory / 'mapped.v'),
        'producer_sha256': digest(directory / 'native-producer.tcl'),
        'native_data_sha256': digest(directory / 'native-data.json'),
        'libraries': [row for row in audit['sources'] if row['role'] == 'liberty'],
        'producer': audit['producer'], 'runtime_image': transport['binding']['image_identity'],
        'requested_corners': runtime['requested_corners'], 'executed_corners': runtime['executed_corners'],
        'configuration_delta': load(run / 'timing-intent/configuration-delta.json'),
        'resolved_stages': view['corners'][0]['resolved']['stages'],
        'native_coverage': view['corners'][0]['native_coverage'], 'downstream_slacks_ns': slacks,
        'verified_companion_sources': len(companion['sources']), 'verified_audit_sources': len(audit['sources']),
        'verified_preliminary_failed_sources': len(old_companion['sources']),
        'verified_command_receipts': command_receipts, 'run_file_count': len(run_hashes),
        'exhaustive_exception_effect': 'unavailable', 'reset_effect': 'unavailable',
        'timing_closure': 'not_established; negative hold retained', 'pnr_allocation': 0,
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
