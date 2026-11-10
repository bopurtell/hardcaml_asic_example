#!/usr/bin/env python3
"""Independent read-only R4 replay using B's existing pinned corrected helpers."""
import argparse
import json
from pathlib import Path

from pt7named_acceptance import EVIDENCE, ROOT, command, sha, write_new

ASIC = ROOT.parent / 'hardcaml_asic'
GENERATION = ROOT / '.dev/asic-pt7named/provider/generations/ce6be246fafa4d0dbe1dd00da980482b'
B_REPLAY = Path('/tmp/opencode/pt7-r4-real-reader-replay-mt6ieg_5')


def load(path):
    return json.loads(path.read_text())


def reference(path):
    return {'path': str(path), 'sha256': sha(path)}


def observed(path):
    before = path.stat()
    digest = sha(path)
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    return {'target': str(path.resolve(strict=True)), 'sha256': digest, 'bytes': after.st_size,
            'dev': after.st_dev, 'ino': after.st_ino, 'mtime_ns': after.st_mtime_ns, 'ctime_ns': after.st_ctime_ns}


def tree(root):
    return {str(path.relative_to(root)): observed(path) for path in sorted(root.rglob('*')) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    output = EVIDENCE / args.attempt
    output.mkdir(exist_ok=False)
    binaries = B_REPLAY / 'reader/_build/default/bin'
    expected_binaries = load(B_REPLAY / 'reader-binaries.json')
    binary_refs = {name: reference(binaries / name) for name in expected_binaries}
    assert {name: row['sha256'] for name, row in binary_refs.items()} == expected_binaries
    tested = load(B_REPLAY / 'tested-source-receipt.json')
    source_refs = {name: reference(ASIC / name) for name in tested['sha256']}
    assert {name: row['sha256'] for name, row in source_refs.items()} == tested['sha256']
    write_new(output / 'reader-identities-before.json', {
        'binaries': binary_refs, 'sources': source_refs,
        'b_tested_receipt': reference(B_REPLAY / 'tested-source-receipt.json'),
        'b_replay_summary': reference(B_REPLAY / 'summary.json'),
        'identity_scope': 'actual existing executable/source SHA256s matched to B receipt; no new build or compiled-source authentication',
        'consumer_script': reference(Path(__file__).resolve())})
    runtime = load(B_REPLAY / 'runtime-source-comparison.json')
    runtime_comparison = []
    for row in runtime:
        path = row['path']
        current = sha(ASIC / path)
        executed = sha(GENERATION / 'lib/hardcaml_asic' / path)
        assert current == executed == row['current_sha256']
        runtime_comparison.append({'path': path, 'current_sha256': current,
                                   'original_executed_provider_source_sha256': executed})
    write_new(output / 'runtime-source-comparison.json', runtime_comparison)
    provider_before = observed(GENERATION / 'receipt.json')
    # Protect all earlier example receipt files, not just the two public views.
    old_evidence = {str(path.relative_to(EVIDENCE)): observed(path)
                    for path in sorted(EVIDENCE.rglob('*'))
                    if path.is_file() and not path.is_relative_to(output)}
    write_new(output / 'earlier-evidence-before.json', old_evidence)
    results = []
    for profile, workspace, attempt in (
        ('area', 'area-run-final-04', 'cb5e7cd92dbf43b4a6c00a74b61c6d72'),
        ('delay', 'delay-run-final-03', '9374823306a64897959e1b2295f52c84')):
        folder = output / profile
        folder.mkdir()
        root = ROOT / '.dev/asic-pt7named/workspaces' / workspace
        execution = root / f'execution-{attempt}.json'
        original = EVIDENCE / f'{profile}-public-final-03'
        old_inspect = load(original / 'inspect/stdout.log')
        old_report = load(original / 'report/stdout.log')
        before = tree(root)
        source_before = {row['path']: observed(Path(row['path'])) for row in old_inspect['sources']}
        write_new(folder / 'run-before.json', before)
        write_new(folder / 'sources-before.json', source_before)
        inspected = command(folder, 'inspect', [binaries / 'flow_cli.exe', 'timing-intent-inspect',
                            execution, '--kind', 'execution', '--json'], expected=(1,), timeout=180)
        reported = command(folder, 'report', [binaries / 'flow_cli.exe', 'report', execution,
                           '--json'], timeout=180)
        source_file = command(folder, 'sources', [binaries / 'api.exe', 'sources', execution], timeout=180)
        view, report, sources = load(inspected), load(reported), load(source_file)
        assert view == old_inspect
        assert report == old_report and report['timing_intent'] == view
        assert sources == view['sources'] == load(original / 'sources/stdout.log')
        assert len(sources) == 1584 and len(view['association']['external_aliases']) == 1062
        assert view['status'] == 'completed' and view['verdict'] == 'unavailable'
        native = view['corners'][0]['native_coverage']
        assert native['stored_exception_scope']['relation_count'] == 6
        assert len(native['diagnostics']['categories']) == 7 and native['endpoints']['count'] == 12
        manifest = load(root / 'project/manifest.json')
        pins = [row for row in manifest['target']['external_references']
                if row['source'] == 'Support_tools' and row['role'] == 'Floorplan_def']
        assert len(pins) == 1
        pin = pins[0]
        staged = root / 'project/tt' / pin['path']
        assert sha(staged) == pin['sha256'] == 'b46d9a0ee8352160e48dbc8312f092f985629061df736c7f46d58686535a76f4'
        after = tree(root)
        source_after = {row['path']: observed(Path(row['path'])) for row in sources}
        assert before == after and source_before == source_after
        assert len(before) == 168
        write_new(folder / 'run-after.json', after)
        write_new(folder / 'sources-after.json', source_after)
        results.append({'profile': profile, 'execution': reference(execution), 'attempt_id': attempt,
            'original_execution_generation': GENERATION.name, 'corrected_reader_generation': 'B pinned R4 helper, not an execution provider capture',
            'inspection_json_exactly_original': True, 'entire_report_json_exactly_original': True,
            'source_api_exactly_original': True, 'inspect_exit': 1, 'report_exit': 0, 'source_api_exit': 0,
            'run_files_unchanged': len(before), 'sources_unchanged': len(sources), 'aliases': 1062,
            'floorplan_frozen_pin': {'path': str(staged), 'sha256': pin['sha256']},
            'inspection': reference(inspected), 'report': reference(reported), 'source_api': reference(source_file)})
    old_after = {name: observed(EVIDENCE / name) for name in old_evidence}
    assert old_after == old_evidence
    write_new(output / 'earlier-evidence-after.json', old_after)
    assert observed(GENERATION / 'receipt.json') == provider_before
    binary_after = {name: reference(binaries / name) for name in expected_binaries}
    source_after = {name: reference(ASIC / name) for name in tested['sha256']}
    assert binary_after == binary_refs and source_after == source_refs
    write_new(output / 'reader-identities-after.json', {'binaries': binary_after, 'sources': source_after})
    write_new(output / 'summary.json', {'status': 'corrected_R4_reader_independently_qualified',
        'original_execution_provider': reference(GENERATION / 'receipt.json'), 'profiles': results,
        'runtime_sources_equal_original_provider': len(runtime_comparison),
        'earlier_example_evidence_files_unchanged': len(old_evidence),
        'original_provider_receipt_unchanged': True, 'native_runs_launched': 0,
        'builds_launched': 0, 'provider_captures_launched': 0,
        'native_timing_and_checkpoint_identity': 'unchanged; original native-closeout-final-03 remains authoritative',
        'closure_scope': 'path_bound', 'timing_closure': 'not_established'})


if __name__ == '__main__':
    main()
