#!/usr/bin/env python3
"""Independent assertions over installed public comparisons, not a comparison engine."""
import argparse
import json
from pathlib import Path
import shutil

from pt8_acceptance import ROOT, EVIDENCE, compare, write, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', required=True, type=Path)
    parser.add_argument('--emission', required=True, type=Path)
    args = parser.parse_args()
    assert Path(args.attempt).name == args.attempt
    output = EVIDENCE / args.attempt
    output.mkdir()
    generation = args.generation.resolve(strict=True)
    bundles = {name: Path(json.loads((args.emission / name / 'stdout.log').read_text())['bundle'])
               for name in ('flops128', 'flops256', 'exact256', 'delay256', 'ignored128')}
    assertions = []

    def check(label, condition):
        assert condition, label
        assertions.append(label)

    def pair(label, lk, left, rk, right, axis):
        value = compare(output, label, generation, lk, left, rk, right, axis)
        write(output / (label + '.json'), value)
        check(label + ': workload unavailable', value['workload']['status'] == 'unavailable')
        check(label + ': no winner', 'winner' not in value and 'score' not in value)
        check(label + ': complete bounded result', value['truncated'] is False)
        for m in value['metrics']:
            if m['comparison'] != 'comparable':
                check(label + ': no ineligible delta ' + m['metric_id'], m['right_minus_left'] is None)
        return value

    def state(value, key):
        return next(row['state'] for row in value['differences'] if row['domain'] == key)

    hardware = pair('hardware', 'bundle', bundles['flops128'], 'bundle', bundles['flops256'], 'hardware')
    check('hardware declaration differs', state(hardware, 'hardware_declaration') == 'different')
    check('actual hardware differs', state(hardware, 'hardware') == 'different')
    check('actual contracts differ', state(hardware, 'resource_contracts') == 'different')
    policy = pair('policy', 'bundle', bundles['flops256'], 'bundle', bundles['exact256'], 'resource_policy')
    check('policy declaration equal', state(policy, 'hardware_declaration') == 'equal')
    check('policy contracts equal', state(policy, 'resource_contracts') == 'equal')
    check('policy differs', state(policy, 'resource_policy') == 'different')
    profile = pair('profile', 'bundle', bundles['flops256'], 'bundle', bundles['delay256'], 'flow_configuration')
    check('profile declaration equal', state(profile, 'hardware_declaration') == 'equal')
    check('profile hardware equal', state(profile, 'hardware') == 'equal')
    check('backend settings differ', state(profile, 'flow_configuration') == 'different')
    ignored = pair('ignored-integrity-only', 'bundle', bundles['flops128'], 'bundle', bundles['ignored128'], 'hardware')
    check('ignored declaration valid and equal', state(ignored, 'hardware_declaration') == 'equal')
    check('ignored actual contracts differ despite valid declaration', state(ignored, 'resource_contracts') == 'different')

    named = ROOT / '.dev/asic-pt7named/workspaces'
    area = named / 'area-run-final-04/execution-cb5e7cd92dbf43b4a6c00a74b61c6d72.json'
    delay = named / 'delay-run-final-03/execution-9374823306a64897959e1b2295f52c84.json'
    physical = ROOT / '.dev/asic-timing-physical/full-runs/20261029T075052976305Z_23a6954b'
    synthesis = ROOT / '.dev/asic-timing-physical/synthesis-runs/20261029T070532999179Z_4821044b'
    historical = pair('named-area-delay', 'execution', area, 'execution', delay, 'flow_configuration')
    for side in ('left', 'right'):
        check('historical parameters unavailable ' + side,
              historical[side]['hardware_variant'] is None and
              historical[side]['hardware_metadata_status'] == 'unavailable')
    check('same netlist remains same hardware', state(historical, 'hardware') == 'equal')
    check('same output different attempt identities',
          historical['left']['identities'] != historical['right']['identities'])
    self_value = pair('physical-self', 'coarse_run', physical, 'coarse_run', physical, 'descriptive')
    check('physical acceptance retained', self_value['left']['outcomes']['acceptance'] == 'pass')
    check('physical metadata unavailable', self_value['left']['hardware_metadata_status'] == 'unavailable')
    check('exhaustive coverage not promoted',
          self_value['left']['outcomes']['timing'].get('exhaustive_coverage') != 'pass')
    self_native = [m for m in self_value['metrics'] if m['metric_id'].startswith('native/')]
    check('18 authoritative native self metrics', len(self_native) == 18)
    check('self native deltas exact zero', all(m['comparison'] == 'comparable' and
          m['right_minus_left'] == 0 for m in self_native))
    cross = pair('synthesis-physical', 'coarse_run', synthesis, 'coarse_run', physical, 'descriptive')
    check('cross environment retained', state(cross, 'environment') in ('equal', 'different', 'unavailable'))
    check('cross timing context retained', state(cross, 'timing_environment') in ('equal', 'different', 'unavailable'))
    check('cross no causal timing delta', all(m['right_minus_left'] is None for m in cross['metrics']))
    native = [m for m in cross['metrics'] if m['metric_id'].startswith('native/')]
    check('18 authoritative whole-design native cross metrics', len(native) == 18)
    check('synthesis/physical native metrics confounded', all(m['comparison'] == 'confounded' for m in native))
    for m in native:
        if m['left'] is not None and m['right'] is not None:
            check('distinct stages retained ' + m['metric_id'], m['left']['stage'] != m['right']['stage'])
            check('same explicit corner retained ' + m['metric_id'],
                  m['left']['scope']['corner'] == m['right']['scope']['corner'])
            check('model and RC controls retained ' + m['metric_id'],
                  'libraries' in cross['left']['metric_contexts'][m['left']['controls_digest']]
                  and 'rc' in cross['right']['metric_contexts'][m['right']['controls_digest']])
            check('stage/RC confounding reasons retained ' + m['metric_id'],
                  any('stage' in reason for reason in m['reasons']) and
                  any('rc' in reason for reason in m['reasons']))
    pair('named-physical', 'execution', area, 'coarse_run', physical, 'descriptive')

    # Copies only: sources and claim substitution must reject in both public paths.
    negatives = output / 'negative-copies'
    negatives.mkdir()
    source_copy = negatives / 'source-mutation'
    shutil.copytree(bundles['flops128'], source_copy, symlinks=False)
    pair('source-copy-control', 'bundle', source_copy, 'bundle', bundles['flops128'], 'hardware')
    source = source_copy / 'inputs/tooling_acceptance/variants/variant_memory.ml'
    original = sha(source)
    with source.open('a') as stream:
        stream.write('\n(* deliberate retained-source corruption *)\n')
    check('source mutation changed bytes', sha(source) != original)
    compare(output, 'source-corruption', generation, 'bundle', source_copy,
            'bundle', bundles['flops256'], 'hardware', (2,))
    claim_copy = negatives / 'rebound-claim'
    shutil.copytree(bundles['flops128'], claim_copy, symlinks=False)
    pair('claim-copy-control', 'bundle', claim_copy, 'bundle', bundles['flops128'], 'hardware')
    manifest_path = claim_copy / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    donor = json.loads((bundles['flops256'] / 'manifest.json').read_text())
    manifest['hardware_variant'] = donor['hardware_variant']
    manifest_path.write_text(json.dumps(manifest))
    compare(output, 'rebound-claim', generation, 'bundle', claim_copy,
            'bundle', bundles['flops256'], 'hardware', (2,))
    execution_directory = negatives / 'rebound-execution'
    execution_directory.mkdir()
    execution_copy = execution_directory / area.name
    execution = json.loads(area.read_text())
    donor_execution = json.loads(delay.read_text())
    # Full valid donor claim, wrong attempt association; no historical mutation.
    execution['methodology'] = donor_execution['methodology']
    write(execution_copy, execution)
    compare(output, 'rebound-attempt', generation, 'execution', execution_copy,
            'execution', delay, 'flow_configuration', (2,))
    write(output / 'assertions.json', {'assertions': assertions, 'count': len(assertions),
          'eda_runs': 0, 'comparisons_are_read_only': True,
          'integrity_is_not_semantic_conformance': True})


if __name__ == '__main__':
    main()
