#!/usr/bin/env python3
"""Bind passing installed receipts, actual model sources and immutable attempt inventory."""
import argparse
import json
from pathlib import Path

import pt8_workloads as p
from pt8_workloads_acceptance import load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--acceptance', default='acceptance-04')
    parser.add_argument('--controls', default='controls-02')
    parser.add_argument('--capture', default='capture-02-nested')
    parser.add_argument('--preservation', default='preservation-final.json')
    parser.add_argument('--regressions')
    parser.add_argument('--producer-reuse')
    parser.add_argument('--expected-comparison-sha256')
    parser.add_argument('--discovery-alias')
    args = parser.parse_args()
    generation = args.generation.resolve(strict=True)
    acceptance = p.EVIDENCE / args.acceptance / 'assertions.json'
    controls = p.EVIDENCE / args.controls / 'assertions.json'
    assert load(acceptance)['pass'] and load(controls)['pass']
    assert not load(p.EVIDENCE / args.preservation)['failures']
    snapshot = p.EVIDENCE / args.capture / 'source-snapshot'
    provider_sources = {}
    for name in ('workload_result.ml', 'workload_result.mli', 'variant_comparison.ml',
                 'variant_comparison.mli', 'retained_file.ml', 'retained_file.mli'):
        path = Path('execution/results') / name
        provider_sources[str(path)] = {
            'captured_sha256': p.sha(snapshot / path),
            'current_sha256': p.sha(p.ROOT.parent / 'hardcaml_asic' / path)}
    if args.regressions:
        assert load(p.EVIDENCE / args.regressions / 'assertions.json')['pass']
        assert all(s['captured_sha256'] == s['current_sha256'] for s in provider_sources.values())
        assert args.expected_comparison_sha256, 'supply explicit reviewed comparison source hash'
        assert provider_sources['execution/results/variant_comparison.ml']['captured_sha256'] == args.expected_comparison_sha256
        assert provider_sources['execution/results/retained_file.ml']['captured_sha256'] == \
            '6f69c0bea1f987f0c48c908264d3ad195db5f49a07cd624ec32e5a0369729fcc'
    if args.discovery_alias:
        control = load(p.EVIDENCE / args.discovery_alias / 'assertions.json')
        assert control['pass'] and control['generation'] == str(generation)
    models = {}
    simulation = p.EVIDENCE / 'simulation-04'
    for policy in ('flops', 'exact', 'flops-ignored'):
        r = load(simulation / policy / 'result.json')
        bundle = Path(r['bundle'])
        manifest = load(bundle / 'manifest.json')
        for source in manifest['source_inputs']:
            assert p.sha(p.ROOT / source['path']) == source['sha256'], source
        if policy == 'exact':
            contract = manifest['macro_contract']['implementation_simulation']
            assert contract['defines'] == ['FUNCTIONAL']
            for ref in contract['models']:
                source = p.ROOT / '_flow_tools/pdk/ihp-sg13cmos5l' / ref.removeprefix('pdk_dir::')
                retained = simulation / 'exact' / source.name
                assert p.sha(source) == p.sha(retained)
                models[str(source)] = {'sha256': p.sha(source), 'retained': str(retained)}
    sources = list((p.ROOT / 'tooling_acceptance/workloads').glob('*'))
    sources += list((p.ROOT / 'tooling_acceptance/workloads/controls').glob('pt8_workloads*.py'))
    sources += [p.ROOT / 'docs/pt8_workloads_final.md']
    physical = p.ROOT / 'acceptance/sram/physical-p4'
    summary = load(physical / 'summary.json')
    assert summary['physical_acceptance'] is True
    executions = list(p.EVIDENCE.glob('simulation-*/*/execute/command.json'))
    commands = list(p.EVIDENCE.rglob('command.json'))
    inventory = {str(f.relative_to(p.EVIDENCE)): p.sha(f)
                 for f in sorted(p.EVIDENCE.rglob('*')) if f.is_file()}
    binaries = [generation / 'bin/hardcaml-asic-flow',
                generation / 'bin/hardcaml-asic-experimental-compare',
                p.BUILD / 'workload_emit.exe', p.BUILD / 'workload_public.exe']
    p.write(p.EVIDENCE / args.output, {
        'contract': 'example.pt8-workloads-final-receipt', 'schema_version': 1,
        'initial_pass': True,
        'corrected_reader_pass': bool(args.regressions),
        'independent_review': ('provider_review_corrections_retested; bounded_example_acceptance'
                               if args.regressions else 'requested_after_initial_pass_not_claimed'),
        'provider_generation': str(generation), 'provider_receipt': load(generation / 'receipt.json'),
        'reader_provider_generation': str(generation),
        'simulation_producer_generation': (load(p.EVIDENCE / args.producer_reuse)['simulation_producer_generation']
                                            if args.producer_reuse else str(generation)),
        'provider_receipt_sha256': p.sha(generation / 'receipt.json'),
        'provider_sources': provider_sources, 'binaries': {str(f): p.sha(f) for f in binaries},
        'consumer_sources': {str(f.relative_to(p.ROOT)): p.sha(f) for f in sources if f.is_file()},
        'stock_vendor_models': models,
        'passed_acceptance': str(acceptance), 'passed_controls': str(controls),
        'reader_regressions': (load(p.EVIDENCE / args.regressions / 'assertions.json')
                               if args.regressions else None),
        'discovery_alias_controls': (load(p.EVIDENCE / args.discovery_alias / 'assertions.json')
                                      if args.discovery_alias else None),
        'simulation_producer_reuse': (load(p.EVIDENCE / args.producer_reuse)
                                       if args.producer_reuse else None),
        'completed_simulator_processes_all_attempts': len(executions),
        'completed_simulator_attempt_receipts': [str(f.relative_to(p.EVIDENCE)) for f in executions],
        'commands': {str(f.relative_to(p.EVIDENCE)): load(f) for f in commands},
        'preservation': load(p.EVIDENCE / args.preservation),
        'retained_physical_context': {
            'summary_sha256': p.sha(physical / 'summary.json'),
            'bundle_sha256': p.sha(physical / 'bundle/manifest.json'),
            'run_id': summary['run_id'], 'bundle_identity': summary['bundle_identity'],
            'qualification': 'different historical consumer adapter/clock/settings; not matched A/B'},
        'eda_runs': 0, 'max_jobs': 6, 'simulator_concurrency': 1,
        'limits': {'operations': 4096, 'result_stimulus_trace_simulation_bytes_each': 1048576,
                   'artifact_bytes_each': 8388608, 'artifact_count': 32,
                   'workload_sources_bytes': 33554432, 'projection_bytes': 1048576,
                   'query_timeout_seconds': 180, 'capture_timeout_seconds': 1800},
        'unsupported': ['firmware size/fetch', 'physical area/speed A/B delta', 'timed SRAM/SDF',
                        'authenticated execution/P6', 'exhaustive memory proof'],
        'retained_attempt_inventory': inventory})


if __name__ == '__main__':
    main()
