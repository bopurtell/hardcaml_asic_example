#!/usr/bin/env python3
"""New corrected final receipt; preserves and verifies the original PT8 histories."""
import hashlib
import json
from pathlib import Path
import stat

from pt8_acceptance import ROOT, EVIDENCE, sha, sources, write
from pt8_preservation import verify

EXPECTED = {
    'execution/results/variant_comparison.ml': '37d593d884f7d093ce3312dcce69bfedce03e6a2a4c1e4dada82bab0b93f2bed',
    'execution/results/resource_inspection_service.ml': '53bd488c040859cef6c6f7178ac7265f8d79bd6a6ba671b50122459654f46b1d',
    'execution/results/report_service.ml': '83e4981d97ce92fd257f3c6fdbe4424194ff852e9469187a44a54a41eb53b0b5',
    'execution/results/report_service.mli': '66a24e0b97b043fe1a88e55c9002ba801f5f3c5a137362a8ff4bc09b62da1aec',
    'execution/results/retained_file.ml': 'c858c5f4c772150095d3066e3831aac679d3ab158fe3abfff8e7aa8889a5ec39',
    'execution/results/retained_file.mli': 'b457319c617feb44511c737a244713e4c01e8a0d61a799ea062e4dba2e1e49cf',
    'execution/retained_file_stubs.c': '5247984585b41510e3ae301713e9b7d2956f5c378b256ec683d3667bd23d09b0',
    'execution/results/evidence_json.ml': '2fc179c30abfa0ce4b4a1eaf0885da9d944b3e13ed1a6609699424991caed6bc',
    'execution/results/evidence_json.mli': '693cc1807e723ff1e6a04011bdb7227673ebe4cc34de731f16c09f8ebe57432f',
    'execution/archive/archive_service.ml': 'dab674a84fa07d8cdf4ae16594d7016eee37b129e0a83c84ed37c342f52aef2d',
    'execution/dune': 'f1833995d985df483a057141bb7fbf8a254179f1291d05f9777900da384dcc40',
    'test/variant_comparison/admission.py': 'b3992afa4300f7f506629d5fc3adc37005ba8ad4090155ea6aab869fb739b573',
}


def load(path):
    return json.loads(path.read_text())


def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if stat.S_ISREG(p.lstat().st_mode)}


def main():
    output = EVIDENCE / 'final-corrected-source'
    output.mkdir()
    sources(output)
    captured = EVIDENCE / 'capture-corrected-01-nested'
    provider = load(captured / 'generation.json')
    generation = Path(provider['generation'])
    assert sha(generation / 'receipt.json') == provider['receipt_sha256']
    captured_files = load(captured / 'source-snapshot.json')
    assert inventory(captured / 'source-snapshot') == captured_files
    for name, expected in EXPECTED.items():
        assert captured_files[name] == expected, (name, captured_files[name])

    # Actual constructor + factory + oracle source hashes, not a metadata claim.
    construction = ROOT / 'tooling_acceptance/variants/variant_memory.ml'
    oracle = ROOT / 'tooling_acceptance/variants/verif/conformance.ml'
    previous = EVIDENCE / 'build-05/consumer-source'
    assert sha(construction) == sha(previous / 'variants/variant_memory.ml')
    assert sha(oracle) == sha(previous / 'variants/test/conformance.ml')
    simulated = EVIDENCE / 'consumer-before-pin-descriptions/consumer-source/variants/variant_memory.ml'
    final_raw = construction.read_bytes()
    start = final_raw.index(b'\n      ~pinout:')
    end = final_raw.index(b'\n      ~policy', start)
    without_pin_descriptions = final_raw[:start] + final_raw[end:]
    assert without_pin_descriptions == simulated.read_bytes()
    assert sha(oracle) == sha(EVIDENCE / 'consumer-before-pin-descriptions/consumer-source/variants/test/conformance.ml')
    constructor_check = {
        'variant_memory_sha256': sha(construction), 'conformance_sha256': sha(oracle),
        'same_as_original_final_build': True,
        'simulated_source_sha256': sha(simulated),
        'final_source_without_pin_descriptions_sha256': hashlib.sha256(without_pin_descriptions).hexdigest(),
        'only_since_simulation_difference': 'required TT pin descriptions, outside RAM/factory behavior',
        'functional_simulations_reused': 6, 'additional_functional_simulations': 0}

    matrix = EVIDENCE / 'matrix-corrected-01'
    assertions = load(matrix / 'assertions.json')
    assert assertions['count'] == 204
    matrix_commands = [load(p) for p in matrix.glob('*/command.json')]
    matrix_readonly = [load(p) for p in matrix.glob('*/readonly.json')]
    assert len(matrix_commands) == len(matrix_readonly) == 26
    controls_dir = EVIDENCE / 'controls-corrected-04'
    controls = load(controls_dir / 'controls.json')
    assert controls['status'] == 'passed' and controls['case_count'] == 18
    control_commands = [load(p) for p in controls_dir.glob('*/command.json')]
    control_readonly = [load(p) for p in controls_dir.glob('*/readonly.json')]
    assert len(control_commands) == len(control_readonly)
    for result in matrix_readonly + control_readonly:
        assert result['process_count'] == 1 and not result['write_syscalls']
        assert result['tool_subprocesses'] == result['renderer_subprocesses'] == 0
    for result in control_readonly:
        assert not result['network_syscalls']
    for cmd in matrix_commands + control_commands:
        assert cmd['generation'] == str(generation)
        assert cmd['provider_receipt_sha256'] == provider['receipt_sha256']
    comparison_digests = {}
    for label in ('named-area-delay', 'physical-self', 'synthesis-physical'):
        comparison_digests[label] = load(matrix / (label + '.json'))['comparison_digest']
    assert comparison_digests['physical-self'] == controls['final_physical_comparison_digest']
    response_sizes = {str(p.relative_to(EVIDENCE)): p.stat().st_size
                      for directory in (matrix, controls_dir)
                      for p in directory.glob('*/stdout.log')}
    assert max(response_sizes.values()) <= 1024 * 1024

    emitted = {}
    for label in ('flops128', 'flops256', 'exact256', 'delay256', 'ignored128'):
        response = load(EVIDENCE / 'emit-corrected-01' / label / 'stdout.log')
        bundle = Path(response['bundle'])
        manifest = load(bundle / 'manifest.json')
        for row in manifest['files']:
            assert sha(bundle / row['path']) == row['sha256']
        for row in manifest['source_inputs']:
            assert sha(ROOT / row['path']) == sha(bundle / row['copy']) == row['sha256']
        emitted[label] = {'bundle': str(bundle), 'identity': response['bundle_identity'],
                          'inventory': inventory(bundle)}

    # Original final receipt, source snapshots, matrix histories and installed
    # generation remain immutable. This is separate from the large history seal.
    old = load(EVIDENCE / 'final-seal.json')
    for name, expected in old['evidence_files'].items():
        assert sha(EVIDENCE / name) == expected, ('original PT8 evidence changed', name)
    old_generation = Path(old['provider']['generation'])
    for name, expected in old['provider_installed_files'].items():
        assert sha(old_generation / name) == expected, ('original generation changed', name)
    for name, expected in old['consumer_docs'].items():
        assert sha(ROOT / name) == expected, ('original sealed doc changed', name)

    # Exactly one final full rehash of the pre-existing history baseline.
    preserved = verify(load(EVIDENCE / 'preservation-before.json'))
    assert not preserved['failures']
    write(EVIDENCE / 'preservation-corrected-final.json', preserved)
    write(EVIDENCE / 'final-corrected-seal.json', {
        'status': 'accepted_corrected_installed_pt8_r1_r4',
        'provider': provider, 'provider_receipt': load(generation / 'receipt.json'),
        'reviewed_source_hashes': EXPECTED, 'captured_source_inventory_sha256': sha(captured / 'source-snapshot.json'),
        'installed_files': inventory(generation),
        # These are the original corrected-run binaries, not current launch targets.
        'public_adapter_executables': {str(p.relative_to(ROOT)): sha(p) for p in
             (ROOT / '_build_pt8/default/variants/variant_cli.exe', ROOT / '_build_pt8/default/variants/review_api.exe')},
        'constructor_unchanged': constructor_check, 'emitted_bundles': emitted,
        'matrix_assertions': 204, 'targeted_cases': 18,
        'matrix_traced_invocations': len(matrix_commands), 'control_traced_invocations': len(control_commands),
        'comparison_digests': comparison_digests, 'limits': controls['limits'],
        'maximum_success_stdout_bytes': max(response_sizes.values()),
        'success_stdout_sizes': response_sizes,
        'retained_failure_attempts': ['controls-corrected-01', 'controls-corrected-02', 'controls-corrected-03'],
        'preservation': preserved, 'original_pt8_evidence_files_verified': len(old['evidence_files']),
        'original_generation_unchanged': str(old_generation),
        'original_final_receipt_sha256': sha(EVIDENCE / 'final-seal.json'),
        'consumer_source_inventory_sha256': sha(output / 'consumer-source.json'),
        'corrected_docs': {str(p.relative_to(ROOT)): sha(p) for p in (ROOT / 'docs').glob('pt8_corrected*.md')},
        'eda_runs': 0, 'additional_functional_simulations': 0, 'total_functional_simulations': 6,
        'exact_methodology_plan': 'pre-existing unsupported named-macro boundary; not a new PT8 defect; not enabled',
        'provenance_scope': 'captured bytes and source observations, not compiled-source/P6 attestation',
        'evidence_files': inventory(EVIDENCE)})
    print(json.dumps({'provider': provider, 'constructor': constructor_check,
          'comparison_digests': comparison_digests,
          'matrix_traced_invocations': len(matrix_commands),
          'control_traced_invocations': len(control_commands),
          'maximum_success_stdout_bytes': max(response_sizes.values()),
          'preservation': preserved,
          'corrected_final_receipt_sha256': sha(EVIDENCE / 'final-corrected-seal.json')}, indent=2))


if __name__ == '__main__':
    main()
