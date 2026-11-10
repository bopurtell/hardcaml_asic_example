#!/usr/bin/env python3
"""Correction receipt using prior actual captures; no new emitter/simulator/EDA."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
from workbench_paths import ROOT
import pt8_workloads as producer
from pt8_acceptance import sha, write
from pt8_waveform_acceptance import protected

WB = ROOT.parent / 'hardcaml_workbench'


def preservation():
    files = set()
    old = ROOT / '.dev/asic-pt8-workbench/session-waveforms-02'
    review = Path('/tmp/opencode/pt8-producer-review-y6yxh4gt')
    for root in (old, review):
        for base, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('_build') and d != '__pycache__']
            files.update(Path(base) / name for name in names)
    files.update((WB / 'scripts/review-pt8-waveform-producer.py',
                  WB / 'docs/pt8_waveform_producer_review.md'))
    return {'protected': protected(), 'session02_and_review': {
        str(p): {'sha256': sha(p), 'link': str(p.readlink()) if p.is_symlink() else None}
        for p in sorted(files) if p.is_file()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-session', type=Path)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    if args.verify_session:
        session = args.verify_session.resolve(strict=True)
        baseline = args.baseline.resolve(strict=True)
        assert preservation() == json.loads((baseline / 'preservation-after.json').read_text())
        manifest = json.loads((session / 'manifest.json').read_text())
        assert all(sha(session / 'provider' / name) == digest
                   for name, digest in manifest['captured_files'].items())
        for name in ('tooling_acceptance/workloads/controls/pt8_workloads.py',
                     'integration/workbench/pt8_workbench_provider.py', 'integration/workbench/pt8_workbench_runner.py'):
            assert sha(ROOT / name) == sha(session / 'provider' / name)
        assert manifest['source_snapshot']['scripts/test_pt8_waveforms.py'] == sha(ROOT / 'scripts/test_pt8_waveforms.py')
        previous = ROOT / '.dev/asic-pt8-workbench/session-final-review-01/manifest.json'
        assert manifest['generation'] == json.loads(previous.read_text())['generation']
        assert manifest['private_source_root'] == str(session / 'project')
        write(session / 'final-capture-ready.json', {'pass': True, 'session': str(session),
            'correction_receipt': str(baseline / 'assertions.json'), 'generation': manifest['generation'],
            'captured_files': manifest['captured_files'], 'source_snapshot_sha256': sha(session / 'source-snapshot.json'),
            'root_and_session02_and_original_review_unchanged': True, 'tests_match_snapshot': True,
            'native_final': 'awaiting final frontend binaries; no final fresh workload run yet',
            'real_simulations_started': 0, 'max_jobs': 2, 'eda_allocation': 0})
        print(session / 'final-capture-ready.json')
        return
    output = ROOT / '.dev/asic-pt8-workbench' / ('waveform-correction-' + uuid.uuid4().hex)
    output.mkdir()
    before = preservation()
    write(output / 'preservation-before.json', before)
    sources = {name: sha(ROOT / name) for name in (
        'tooling_acceptance/workloads/controls/pt8_workloads.py',
        'integration/workbench/pt8_workbench_runner.py', 'integration/workbench/pt8_workbench_provider.py',
        'scripts/test_pt8_waveforms.py', 'integration/workbench/pt8_waveform_correction_check.py')}
    write(output / 'sources.json', sources)
    # Run the durable unit regressions, whose Icarus stub checks output syntax only.
    # No real workload pair is rerun; the original actual pair is revalidated below.
    argv = [sys.executable, '-B', str(ROOT / 'scripts/test_pt8_waveforms.py'), '-v']
    with (output / 'tests.stdout').open('xb') as out, (output / 'tests.stderr').open('xb') as err:
        code = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=err, timeout=60).returncode
    write(output / 'tests.command.json', {'argv': argv, 'exit_code': code, 'eda_allocation': 0})
    assert code == 0
    direct = (ROOT / '.dev/asic-pt8-workbench/session-waveforms-02/'
              'waveform-direct-84166e76c12147508792f756556fea1c/assertions.json')
    prior = json.loads(direct.read_text())
    results = {}
    from wire import parse
    probe = WB / '_build_pt8_workbench/default/terminal/waveform_probe.exe'
    for case, receipt in prior['results'].items():
        wave = Path(receipt['result']).with_name('waveform.vcd')
        descriptor = producer.validate_waveform(wave, 1307)
        assert descriptor == receipt['waveform'] == json.loads(wave.with_suffix('.json').read_text())
        assert wave.read_bytes() == Path(receipt['copied']).read_bytes()
        argv = [str(probe), str(wave), '2595000', '2595107', '0', '2595000', '2595001']
        native = subprocess.run(argv, capture_output=True, timeout=30)
        (output / (case + '.native.sexp')).write_bytes(native.stdout)
        (output / (case + '.native.stderr')).write_bytes(native.stderr)
        assert native.returncode == 0
        parsed = dict(parse(native.stdout.decode()))
        assert parsed['status'] == 'ok'
        results[case] = descriptor
    real = Path(prior['results']['flops256']['result']).with_name('waveform.vcd').read_bytes()
    mutations = {
        'unsupported-real-type': real.replace(b'$var reg 1 ! clk', b'$var real 1 ! clk', 1),
        'missing-upscope': real.replace(b'$upscope $end\n', b'', 1),
        'scalar-bus': real.replace(b'bx &', b'x&', 1),
        'bad-range': real.replace(b'[7:0]', b'[999:0]', 1),
    }
    rejects = {}
    for name, data in mutations.items():
        path = output / (name + '.vcd')
        path.write_bytes(data)
        try:
            producer.validate_waveform(path, 1307)
        except ValueError as error:
            rejects[name] = str(error)
        else:
            raise AssertionError('malformed waveform admitted: ' + name)
        native = subprocess.run([str(probe), str(path), '0', '100'], capture_output=True, timeout=30)
        (output / (name + '.native.sexp')).write_bytes(native.stdout)
        assert native.returncode == 0 and dict(parse(native.stdout.decode()))['status'] == 'error'
    after = preservation()
    write(output / 'preservation-after.json', after)
    assert before == after
    write(output / 'assertions.json', {'pass': True, 'sources': sources, 'real_captures_revalidated': results,
        'four_parser_incompatible_mutations_rejected': rejects, 'six_unit_tests_pass': True,
        'failed_inspection_json_only_regression': True, 'session02_and_original_review_unchanged': True,
        'protected_files': len(before['session02_and_review']) + len(before['protected']),
        'native_probe_sha256': sha(probe), 'real_simulations_started': 0, 'eda_allocation': 0})
    print(output)


if __name__ == '__main__':
    main()
