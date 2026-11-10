#!/usr/bin/env python3
"""Seal C's final source/evidence and independently check preserved source bytes."""
import json
from pathlib import Path

from pt8_acceptance import ROOT, EVIDENCE, sha, sources, write
from pt8_preservation import verify


def load(path):
    return json.loads(path.read_text())


def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not p.is_symlink()}


def main():
    output = EVIDENCE / 'final-source'
    output.mkdir()
    sources(output)
    generation_record = load(EVIDENCE / 'capture-01-nested/generation.json')
    generation = Path(generation_record['generation'])
    assert sha(generation / 'receipt.json') == generation_record['receipt_sha256']
    captured = EVIDENCE / 'capture-01-nested'
    captured_inventory = load(captured / 'source-snapshot.json')
    assert inventory(captured / 'source-snapshot') == captured_inventory
    baseline = load(EVIDENCE / 'preservation-before.json')
    preserved = verify(baseline)
    assert not preserved['failures']
    matrix = EVIDENCE / 'matrix-03'
    commands = [load(p) for p in sorted(matrix.glob('*/command.json'))]
    readonly = [load(p) for p in sorted(matrix.glob('*/readonly.json'))]
    assert len(commands) == len(readonly) == 26
    assert sum(c['exit_code'] == 2 for c in commands) == 6
    assert all(r['process_count'] == 1 and not r['write_syscalls'] and
               r['tool_subprocesses'] == r['renderer_subprocesses'] == 0 for r in readonly)
    valid = load(EVIDENCE / 'functional-01/valid/command.json')
    ignored = load(EVIDENCE / 'functional-01/ignored-depth/command.json')
    assert valid['exit_code'] == 0 and ignored['exit_code'] == 1
    assert load(EVIDENCE / 'functional-01/allocation.json')['functional_simulations'] == 6
    summary = {}
    for path in sorted(matrix.glob('*.json')):
        value = load(path)
        if value.get('contract') != 'hardcaml-asic.variant-comparison':
            continue
        summary[path.stem] = {
            'comparison_digest': value['comparison_digest'],
            'sides': {side: {'source_digest': value[side]['source_digest'],
                     'hardware_metadata_status': value[side]['hardware_metadata_status']}
                     for side in ('left', 'right')},
            'metrics': [{key: m[key] for key in ('metric_id', 'comparison', 'right_minus_left', 'reasons')}
                        for m in value['metrics']]}
    write(output / 'comparison-summary.json', summary)
    emitted = {}
    for label in ('flops128', 'flops256', 'exact256', 'delay256', 'ignored128'):
        response = load(EVIDENCE / 'emit-04' / label / 'stdout.log')
        bundle = Path(response['bundle'])
        manifest = load(bundle / 'manifest.json')
        for row in manifest['files']:
            assert sha(bundle / row['path']) == row['sha256']
        for row in manifest['source_inputs']:
            assert sha(bundle / row['copy']) == row['sha256']
            assert sha(ROOT / row['path']) == row['sha256'], 'final declared consumer source changed'
        emitted[label] = {'bundle': str(bundle), 'bundle_identity': response['bundle_identity'],
                          'files': inventory(bundle)}
    owned_docs = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'docs').glob('pt8*.md'))}
    write(EVIDENCE / 'final-seal.json', {
        'status': 'accepted_bounded_independent_pt8_example',
        'provider': generation_record, 'provider_receipt': load(generation / 'receipt.json'),
        'provider_installed_files': inventory(generation),
        'capture_source_inventory_sha256': sha(captured / 'source-snapshot.json'),
        'consumer_source_inventory_sha256': sha(output / 'consumer-source.json'),
        'consumer_docs': owned_docs, 'emitted_bundles': emitted,
        'preservation': preserved, 'matrix_assertions': load(matrix / 'assertions.json')['count'],
        'traced_comparison_commands': len(commands), 'negative_rejections': 6,
        'functional_simulations': 6, 'eda_runs': 0,
        'exact_methodology_plan': 'unsupported; retained production finding',
        'evidence_files': inventory(EVIDENCE),
        'provenance_scope': 'captured source observations; not compiled-source/P6 attestation'})


if __name__ == '__main__':
    main()
