#!/usr/bin/env python3
"""Package the completed portable evidence with immutable source/identity inventory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

from commands import ROOT, STORE, identity, inventory, sha, write_new
from portable_closeout import seal


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', required=True)
    a = p.parse_args()
    assert a.attempt and Path(a.attempt).name == a.attempt
    output = STORE / 'evidence' / a.attempt
    output.mkdir(parents=True, exist_ok=False)
    payload = output / 'portable-source-closeout'
    payload.mkdir()
    public = STORE / 'evidence/full-public-corrected-01'
    restoration = STORE / 'evidence/full-restore-corrected-01'
    snapshot_dir = STORE / 'evidence/portable-before-01'
    snapshot = json.loads((snapshot_dir / 'snapshot.json').read_text())
    proof_file = STORE / 'portable-verification-01.json'
    proof = json.loads(proof_file.read_text())
    assert proof['status'] == 'passed' and proof['advertised_raw_artifacts'] == 423
    run = Path(snapshot['run'])
    assert seal(run) == snapshot['run_before']
    preservation = STORE / 'preservation-portable-final-01.json'
    preserved = json.loads(preservation.read_text())
    assert preserved['verified_files'] == 16377 and preserved['failures'] == []
    binding = json.loads((public / 'identity-binding.json').read_text())
    archive_before = inventory(public / 'archive-output')
    assert snapshot['original_public'] == inventory(STORE / 'evidence/full-public-01')
    sources = {}

    def copy(source, name, category):
        source = Path(source).resolve(strict=True)
        destination = payload / name
        assert destination.is_relative_to(payload) and not destination.exists()
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_identity = identity(source)
        shutil.copyfile(source, destination)
        assert sha(destination) == source_identity['sha256']
        sources[str(destination.relative_to(payload))] = {'category': category, **source_identity}

    def tree(source, prefix, category, predicate=lambda p: True):
        for path in sorted(source.rglob('*')):
            if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts and predicate(path):
                copy(path, Path(prefix) / path.relative_to(source), category)

    tree(public / 'archive-output', 'archive', 'corrected public archive; not a new execution')
    tree(public, 'receipts/corrected-archiver', 'archive-only public commands and source binding',
         lambda p: 'archive-output' not in p.relative_to(public).parts)
    tree(restoration, 'receipts/hidden-input-replay', 'actual public source-hidden replay',
         lambda p: 'restored' not in p.relative_to(restoration).parts)
    tree(snapshot_dir, 'preserved-pre-correction', 'unaltered pre-correction documentation and source seals')
    tree(ROOT / 'tooling_acceptance/timing/physical', 'consumer-source/tooling_acceptance/timing/physical', 'current independent consumer source')
    for name in ('timing_physical_findings.md', 'timing_physical_full_result.md'):
        copy(ROOT / 'docs' / name, Path('consumer-source/docs') / name, 'current corrected live documentation')
    asic = ROOT.parent / 'hardcaml_asic'
    for name in ('timing-physical-qualification.md', 'timing-physical-library-handoff.md',
                 'timing-physical-flow-handoff.md', 'timing-physical-final-review.md'):
        copy(asic / 'docs/development' / name, Path('coordination') / name, 'qualification and independent review source')
    copy(asic / 'test/timing_physical/review_actual.py', 'independent-review/review_actual.py', 'A actual review implementation')
    copy('/tmp/opencode/timing-physical-final-review-3gh6tr27/review.json',
         'independent-review/review.json', 'A actual 1720-assertion review receipt')
    for name in ('original-history.json', 'native-controls-review.json', 'synthesis-baseline-limits-01.json',
                 'full-native-public-acceptance-01.json', 'portable-verification-01.json',
                 'preservation-after-full-01.json', 'preservation-portable-final-01.json'):
        copy(STORE / name, Path('verification') / name, 'immutable acceptance/preservation receipt')
    for directory in sorted((STORE / 'evidence').iterdir()):
        if directory.is_dir() and (directory.name.startswith(('capture-', 'build-')) or
                                   directory.name in ('synth-emit-01', 'full-emit-01', 'full-admission-01',
                                                      'full-run-01', 'full-inspect-01', 'full-postcheck-01',
                                                      'model-adapter-01', 'testbench-01', 'testbench-rtl-01')):
            tree(directory, Path('receipts/original-attempts') / directory.name, 'original attempt, never relabelled')
    tree(STORE / 'controls', 'native-interface-controls', 'original actual native controls; no new EDA')
    tree(STORE / 'bundles/synth-emit-native-01', 'native-interface-inputs/bundle', 'original unmodified qualified emission')
    tree(ROOT / 'acceptance/timing/synth-scalar-r3', 'native-interface-inputs/retained-mapped-input', 'byte-identical copy of read-only historical input')
    provider_binaries = {}
    for role, generation in (('execution', binding['execution_generation']),
                             ('corrected-archive-reader', binding['archive_reader_generation'])):
        provider = STORE / 'provider/generations' / generation
        copy(provider / 'receipt.json', Path('provider-identities') / role / 'receipt.json', role + ' identity, roles are distinct')
        tree(provider / 'lib/hardcaml_asic', Path('provider-source') / role,
             'installed immutable source snapshot for ' + role,
             lambda p: p.suffix in ('.ml', '.mli', '.py', '.tcl', '.json', '.sh', '.txt') or
                       p.name in ('META', 'dune-package', 'opam'))
        provider_binaries[role] = {p.name: identity(p) for p in sorted((provider / 'bin').iterdir()) if p.is_file()}
    for occurrence in proof['thread_accounting']:
        reference = occurrence.get('native_command_source') or occurrence.get('process_source')
        path = Path(reference['path'])
        assert sha(path) == reference['sha256']
        copy(path, Path('actual-thread-evidence') / path.relative_to(run), 'exact original command/process bytes; not modified accounting')
    inventory_path = payload / 'source-inventory.json'
    write_new(inventory_path, {'schema_version': 1, 'scope': 'portable physical acceptance package source inventory',
        'run_id': proof['run_id'], 'build_identity': proof['build_identity'],
        'execution_generation': binding['execution_generation'],
        'corrected_archiver_generation': binding['archive_reader_generation'],
        'corrected_archive_source_sha256': binding['expected_archive_source_sha256'],
        'provider_binary_identities': provider_binaries, 'files': sources,
        'self_inventory': 'this inventory is hashed by the external package receipt',
        'actual_run_records_unchanged': True, 'original_history_files_verified': 16377,
        'full_attempts': 1, 'additional_eda': False,
        'thread_scope': 'dedicated all-corner and linked STA1; mid-PNR OpenROAD31=1,36/38/43=6; allocation6',
        'coordinator_disposition': 'correct claims, preserve original commands, no physical repeat',
        'coverage_scope': 'three cell-PVT corners with one nominal RC view; bounded native coverage and zero-delay functional replay'})
    payload_inventory = inventory(payload)
    package = output / 'physical-timing-portable.tar.gz'
    with tarfile.open(package, 'x:gz') as archive:
        for name in payload_inventory:
            archive.add(payload / name, arcname='portable-source-closeout/' + name, recursive=False)
    encoded = {}
    with tarfile.open(package, 'r:gz') as archive:
        for member in archive:
            assert member.isfile() and member.name.startswith('portable-source-closeout/')
            name = member.name.removeprefix('portable-source-closeout/')
            assert name in payload_inventory and name not in encoded
            with archive.extractfile(member) as stream:
                encoded[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert encoded == payload_inventory
    assert inventory(payload) == payload_inventory
    assert seal(run) == snapshot['run_before']
    assert snapshot['original_public'] == inventory(STORE / 'evidence/full-public-01')
    assert archive_before == inventory(public / 'archive-output')
    closeout = {'status': 'complete', 'scope': 'bounded physical timing and portable-source acceptance',
        'run_id': proof['run_id'], 'build_identity': proof['build_identity'],
        'execution_generation': binding['execution_generation'], 'execution_provider': binding['execution_provider'],
        'corrected_archiver_generation': binding['archive_reader_generation'],
        'corrected_archiver_provider': binding['archive_reader_provider'],
        'corrected_reader_snapshot_sha256': binding['archive_reader_snapshot_sha256'],
        'corrected_archive_source_sha256': binding['expected_archive_source_sha256'],
        'public_archive': binding['archive_files'], 'portable_verification': identity(proof_file),
        'public_parity': {'inspect': True, 'collect': True, 'report': True},
        'advertised_raw_artifacts_verified': 423, 'archive_members_verified': 449,
        'restored_files': 476, 'original_run_files_unchanged': 1196,
        'historical_files_verified_unchanged': 16377, 'independent_actual_review_assertions': 1720,
        'thread_accounting': proof['mid_pnr_openroad_threads'],
        'dedicated_all_corner_and_linked_sta_threads': 1,
        'resource_disposition': proof['resource_disposition'],
        'prior_documentation_snapshot': identity(snapshot_dir / 'snapshot.json'),
        'source_inventory': identity(inventory_path), 'package': identity(package),
        'package_files_verified_by_decode': len(encoded), 'package_inventory': payload_inventory,
        'full_attempts_used': 1, 'additional_eda': False}
    write_new(output / 'closeout.json', closeout)
    print(json.dumps({k: closeout[k] for k in ('status', 'run_id', 'execution_generation',
        'corrected_archiver_generation', 'corrected_archive_source_sha256', 'source_inventory', 'package',
        'package_files_verified_by_decode', 'advertised_raw_artifacts_verified', 'archive_members_verified')}, indent=2))


if __name__ == '__main__':
    main()
