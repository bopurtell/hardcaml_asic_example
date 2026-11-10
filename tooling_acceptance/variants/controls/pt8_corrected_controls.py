#!/usr/bin/env python3
"""Actual installed R1-R4 admission controls on disposable retained-run copies."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import threading

from pt8_acceptance import ROOT, EVIDENCE, command, compare, sha, write

PHYSICAL = ROOT / '.dev/asic-timing-physical/full-runs/20261029T075052976305Z_23a6954b'
LIMIT = 32 * 1024 * 1024


def on_open(path, mutate, run):
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    assert fd >= 0
    assert libc.inotify_add_watch(fd, os.fsencode(path), 0x20) >= 0
    completed = threading.Event()
    errors = []

    def worker():
        try:
            if select.select([fd], [], [], 180)[0]:
                os.read(fd, 65536)
                mutate()
                completed.set()
        except BaseException as error:
            errors.append(repr(error))

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        result = run()
    finally:
        thread.join()
        os.close(fd)
    assert completed.is_set() and not errors, (completed.is_set(), errors)
    return result


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
    api = ROOT / '_build_pt8/default/tooling_acceptance/variants/variant_cli.exe'
    review = ROOT / '_build_pt8/default/tooling_acceptance/variants/review_api.exe'
    cli = generation / 'bin/hardcaml-asic-flow'
    copies = output / 'copies'
    copies.mkdir()
    left, right = copies / 'left-actual-physical', copies / 'right-actual-physical'
    shutil.copytree(PHYSICAL, left, symlinks=True)
    shutil.copytree(PHYSICAL, right, symlinks=True)
    checks = []

    def record(label, **facts):
        checks.append(dict(case=label, **facts))
        write(output / ('case-%02d.json' % len(checks)), checks[-1])

    def pair(label, expected=(0,)):
        result = compare(output, label, generation, 'coarse_run', left,
                         'coarse_run', left, 'descriptive', expected, timeout=180)
        if result:
            write(output / (label + '.json'), result)
        return result

    def diagnostics(label, tokens, suffixes=('cli', 'api')):
        messages = {}
        for suffix in suffixes:
            directory = output / (label + '-' + suffix)
            message = (directory / 'stderr.log').read_text()
            assert any(token.lower() in message.lower() for token in tokens), message
            assert not (directory / 'stdout.log').read_bytes(), 'invalid query must not emit success JSON'
            messages[suffix] = message.strip()
        record(label, diagnostics=messages, intended_diagnostic_reached=True)

    baseline = pair('actual-copy-clean')
    native = [m for m in baseline['metrics'] if m['metric_id'].startswith('native/')]
    assert len(native) == 18 and all(m['comparison'] == 'comparable' for m in native)
    assert baseline['left']['verified_bundle_sources']
    record('actual-copy-clean', native_metrics=18, retained_original=str(PHYSICAL))
    manifest_path = left / 'project/manifest.json'
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    member = left / 'project' / manifest['source_inputs'][0]['copy']
    assert member.is_file() and not member.is_symlink()
    original = member.read_bytes()
    original_hash = sha(member)
    member.write_bytes(original + b'\n(* corrupted actual declared input *)\n')
    pair('actual-input-corrupt', (2,))
    diagnostics('actual-input-corrupt', ('bundle member hash mismatch',))
    member.unlink()
    pair('actual-input-missing', (2,))
    diagnostics('actual-input-missing', ('No such file', 'missing'))
    member.write_bytes(original)
    assert sha(member) == original_hash

    results = left / 'results.json'
    if not results.exists():
        # The original accepted run has no stored results.json. Capture the
        # actual public report projection and store it only on this disposable
        # copy; no measurement/outcome is invented or edited.
        reported = command(output, 'actual-public-results-capture', [review, 'report', left],
                           generation, trace=True, timeout=180)
        projection = json.loads(reported.read_text())
        results.write_text(json.dumps(projection['results'], separators=(',', ':')) + '\n')
        baseline = pair('actual-stored-results-clean')
        record('actual-public-results-capture', original_stored_results='absent',
               materialized_on_copy_only=True, public_projection_sha256=sha(reported))
    assert results.is_file() and not results.is_symlink()
    results_raw = results.read_bytes()
    (output / 'original-results.json').write_bytes(results_raw)
    results_value = json.loads(results_raw)
    for kind in ('fifo', 'symlink', 'directory', 'oversize'):
        results.unlink()
        if kind == 'fifo':
            os.mkfifo(results)
        elif kind == 'symlink':
            results.symlink_to(output / 'original-results.json')
        elif kind == 'directory':
            results.mkdir()
        else:
            with results.open('wb') as stream:
                stream.truncate(LIMIT + 1)
        label = 'actual-results-' + kind
        pair(label, (2,))
        expected = {'fifo': ('must be a regular file',),
                    'symlink': ('retained_open', 'Too many levels'),
                    'directory': ('in_channel_of_descr : Invalid argument', 'must be a regular file'),
                    'oversize': ('byte bound exceeded',)}[kind]
        diagnostics(label, expected)
        # Actual Report_service consumes the same unsafe path, independently of
        # comparison admission. No consumer-side file precheck replaces it.
        command(output, label + '-report', [review, 'report', left], generation,
                (2,), trace=True, timeout=180)
        message = (output / (label + '-report/stderr.log')).read_text()
        assert any(token.lower() in message.lower() for token in expected), message
        if kind == 'directory':
            results.rmdir()
        else:
            results.unlink()
        results.write_bytes(results_raw)

    # Exact inclusive file limit: valid stored JSON padded with whitespace still
    # reaches real report/compare consumers; +1 was rejected above before parsing.
    padded = results_raw.rstrip() + b' ' * (LIMIT - len(results_raw.rstrip()))
    results.write_bytes(padded)
    boundary = pair('actual-results-exact-32mib')
    assert boundary['metrics'] == baseline['metrics']
    assert any(row['path'] == str(results) and row['bytes'] == LIMIT
               for row in boundary['left']['consulted_metadata'])
    record('actual-results-exact-32mib', accepted_bytes=LIMIT, sha256=sha(results))
    results.write_bytes(results_raw)

    # Stable raw-only changes alter source generation, without changing metrics.
    stable = pair('actual-results-stable-raw')
    reformatted = (json.dumps(results_value, indent=4) + '\n').encode()
    assert hashlib.sha256(reformatted).hexdigest() != sha(results)
    results.write_bytes(reformatted)
    changed = pair('actual-results-reformatted')
    assert changed['metrics'] == stable['metrics']
    assert changed['comparison_digest'] != stable['comparison_digest']
    assert changed['left']['source_digest'] != stable['left']['source_digest']
    record('actual-results-reformatted', old_raw_sha256=hashlib.sha256(results_raw).hexdigest(),
           new_raw_sha256=sha(results), identical_metrics=True,
           old_comparison_digest=stable['comparison_digest'],
           new_comparison_digest=changed['comparison_digest'])
    results.write_bytes(results_raw)

    # Inotify synchronizes each mutation to real descriptor opens. Watching the
    # other copy's manifest guarantees the entire left capture has completed.
    for suffix in ('cli', 'api'):
        results.write_bytes(results_raw)
        label = 'actual-raw-generation-race-' + suffix
        argv = ([cli, 'compare', '--left-kind', 'coarse_run', '--left', left,
                 '--right-kind', 'coarse_run', '--right', right, '--axis', 'descriptive', '--json']
                if suffix == 'cli' else [api, 'compare', 'coarse_run', left, 'coarse_run', right, 'descriptive'])
        on_open(right / 'project/manifest.json', lambda: results.write_bytes(reformatted),
                lambda: command(output, label, argv, generation, (2,), trace=True, timeout=180))
        message = (output / label / 'stderr.log').read_text()
        assert 'comparison source generation changed' in message, message
        record(label, mutation_completed=True, diagnostic=message.strip(),
               old_raw_sha256=hashlib.sha256(results_raw).hexdigest(), new_raw_sha256=sha(results))
        results.write_bytes(results_raw)
        label = 'actual-open-fifo-race-' + suffix
        same_argv = ([cli, 'compare', '--left-kind', 'coarse_run', '--left', left,
                     '--right-kind', 'coarse_run', '--right', left, '--axis', 'descriptive', '--json']
                    if suffix == 'cli' else [api, 'compare', 'coarse_run', left, 'coarse_run', left, 'descriptive'])

        def replace_fifo():
            results.unlink()
            os.mkfifo(results)

        on_open(results, replace_fifo,
                lambda: command(output, label, same_argv, generation, (2,), trace=True, timeout=180))
        message = (output / label / 'stderr.log').read_text()
        assert 'regular file' in message or 'changed during read' in message, message
        record(label, mutation_completed=True, diagnostic=message.strip(), nonblocking=True)
        results.unlink()
        results.write_bytes(results_raw)

    # Archive raw admission uses an actual, otherwise intact historical copy.
    # Only negative malformed fields are injected; no hardware claim is accepted
    # or attached to historical evidence. The baseline remains true absence.
    command(output, 'archive-actual-clean', [review, 'archive-inspect', left], generation,
            trace=True, timeout=180)
    run_path = left / 'run.json'
    run_raw = run_path.read_bytes()
    run_record = json.loads(run_raw)
    old_identity = manifest['identity']
    emitted = json.loads((args.emission / 'flops128/stdout.log').read_text())
    donor = json.loads((Path(emitted['bundle']) / 'manifest.json').read_text())['hardware_variant']
    donor_raw = json.dumps(donor, separators=(',', ':'))
    base_raw = json.dumps(manifest, separators=(',', ':'))
    identity_prefix = '"identity":"' + old_identity + '",'
    assert base_raw.startswith('{' + identity_prefix)
    unsigned = '{' + base_raw[len('{' + identity_prefix):]
    # Last-wins semantic outer payload is identity-bound while original duplicate
    # syntax is retained; validation must reach raw duplicate-key admission.
    bound_identity = hashlib.sha256((unsigned[:-1] + ',"hardware_variant":' + donor_raw + '}').encode()).hexdigest()
    for label, injected in (
            ('archive-duplicate-optional', '"hardware_variant":null,"hardware_variant":' + donor_raw),
            ('archive-escaped-optional', '"\\u0068ardware_variant":null,"hardware_variant":' + donor_raw),
            ('archive-duplicate-assignment', '"hardware_variant":' + donor_raw.replace('"depth":128', '"depth":256,"depth":128')),
            ('archive-escaped-assignment', '"hardware_variant":' + donor_raw.replace('"depth":128', '"\\u0064epth":256,"depth":128'))):
        malformed = base_raw[:-1] + ',' + injected + '}'
        assert malformed != base_raw and json.loads(malformed)['hardware_variant'] == donor
        malformed = malformed.replace(old_identity, bound_identity, 1)
        manifest_path.write_text(malformed)
        changed_record = dict(run_record, build_identity=bound_identity, manifest_sha256=sha(manifest_path))
        run_path.write_text(json.dumps(changed_record, separators=(',', ':')))
        command(output, label, [review, 'archive-inspect', left], generation, (2,), trace=True, timeout=180)
        message = (output / label / 'stderr.log').read_text()
        assert 'duplicate' in message.lower(), message
        record(label, original_raw_bytes_preserved=True, diagnostic=message.strip(),
               raw_manifest_sha256=sha(manifest_path), outer_identity=bound_identity,
               run_manifest_sha256=changed_record['manifest_sha256'])
        (output / (label + '.manifest.json')).write_text(malformed)
        manifest_path.write_bytes(manifest_raw)
        run_path.write_bytes(run_raw)
    assert results.read_bytes() == results_raw and manifest_path.read_bytes() == manifest_raw
    # A final actual physical self query provides the complete corrected reader
    # file/process/network syscall evidence, directly against the untouched run.
    final = compare(output, 'final-original-physical-readonly', generation,
                    'coarse_run', PHYSICAL, 'coarse_run', PHYSICAL, 'descriptive', timeout=180)
    write(output / 'final-original-physical.json', final)
    write(output / 'controls.json', {'status': 'passed', 'cases': checks, 'case_count': len(checks),
          'eda_runs': 0, 'additional_functional_simulations': 0,
          'limits': {'metadata_file_bytes': LIMIT, 'metadata_aggregate_bytes': 64 * 1024 * 1024,
                     'comparison_response_bytes': 1024 * 1024, 'invocation_timeout_seconds': 180},
          'final_physical_comparison_digest': final['comparison_digest']})


if __name__ == '__main__':
    main()
