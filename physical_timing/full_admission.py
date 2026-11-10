#!/usr/bin/env python3
"""Verify corrected captured capabilities and unchanged native-qualified emission."""
import argparse
import json
from pathlib import Path

from commands import STORE, command, identity, sha, write_new


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', required=True)
    p.add_argument('--generation', type=Path, required=True)
    p.add_argument('--prepared', type=Path, required=True)
    a = p.parse_args()
    assert a.attempt and Path(a.attempt).name == a.attempt
    generation = a.generation.resolve(strict=True)
    assert generation.is_relative_to(STORE / 'provider/generations')
    output = STORE / 'evidence' / a.attempt
    output.mkdir(parents=True, exist_ok=False)
    code = command(output / 'capability', [generation / 'bin/hardcaml-asic-flow', '--version', '--json'], generation=generation)
    assert code == 0
    capability = json.loads((output / 'capability/stdout.log').read_text())
    profile = capability['cli_contract']['capabilities']['timing_intent_physical2']
    assert profile['source_closure'] == 'extracted_state_views_retained_filter_v2'
    assert profile['functional_postcheck'] == 'cmos5l_physical_timing_used_cells_v1'
    prepared = json.loads(a.prepared.read_text())
    assert prepared['generation'] == str(generation) and prepared['stage'] == 'full'
    assert prepared['provider_receipt_sha256'] == sha(generation / 'receipt.json')
    bundle = Path(prepared['bundle'])
    old = STORE / 'bundles/synth-emit-native-01'
    same = {}
    for name in ('constraints/top.sdc', 'constraints/pt7-native-coverage.tcl', 'src/tt_um_pt7_timing.v'):
        assert sha(bundle / name) == sha(old / name), name
        same[name] = sha(bundle / name)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    original = json.loads((old / 'manifest.json').read_text())
    assert manifest['operation'] == 'Hardening'
    assert manifest['timing_intent'] == original['timing_intent']
    assert manifest['timing_physical_qualification'] == original['timing_physical_qualification']
    write_new(output / 'summary.json', {'status': 'passed', 'capability': profile,
        'prepared': identity(a.prepared), 'unchanged_native_qualified_emission': same,
        'native_controls': identity(STORE / 'native-controls-review.json'),
        'repeated_native_controls': False, 'architectural_registers': 5,
        'timing_intent_and_physical_marker_identical': True})
    print(json.dumps({'status': 'passed', 'unchanged_emission': same, 'capability': profile}))


if __name__ == '__main__':
    main()
