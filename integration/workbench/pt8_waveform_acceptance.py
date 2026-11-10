#!/usr/bin/env python3
"""Fresh real FS2 waveform pair, negative/cancel controls and preservation; EDA0."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
from workbench_paths import ROOT
from wire import parse, sexp
from pt8_acceptance import sha, write
from pt8_workloads import validate_waveform


def protected():
    paths = list(ROOT.glob('hardcaml-workbench*.sexp')) + [ROOT / 'asic-dependency.json',
        ROOT / 'asics/fifo_demo/verif/bundle/dune', ROOT / 'asics/fifo_demo/project/project.ml']
    for path in ROOT.glob('hardcaml-workbench*.sexp'):
        for key, value in parse(path.read_text()):
            if key in ('provider_executable', 'project_executable'):
                paths.append(Path(value))
    for name in ('session-final-review-01', 'session-standard-recovery-02'):
        session = ROOT / '.dev/asic-pt8-workbench' / name
        paths += [session / 'manifest.json', session / 'source-snapshot.json']
        paths += list((session / 'provider').rglob('*'))
        paths += list((session / 'project').glob('*.sexp'))
    paths += list((ROOT / 'acceptance/pt8-workloads/simulation-04').rglob('*'))
    return {str(p): {'sha256': sha(p), 'link': os.readlink(p) if p.is_symlink() else None}
            for p in sorted(set(paths)) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--preservation', type=Path)
    args = parser.parse_args()
    if args.baseline:
        write(args.baseline, protected())
        return
    session = args.session.resolve(strict=True)
    manifest = json.loads((session / 'manifest.json').read_text())
    provider = manifest['provider_command']
    output = session / ('waveform-direct-' + uuid.uuid4().hex)
    output.mkdir()
    write(output / 'invocation.json', {'argv': sys.argv, 'eda_allocation': 0})
    def request(label, cases=('flops256', 'exact256'), prefix=provider):
        d = output / label
        d.mkdir()
        (d / 'artifacts').mkdir()
        (d / 'request.sexp').write_text(sexp([('protocol_version', 1), ('attempt_id', label),
            ('selection', [('suite', 'pt8-memory-workloads'), ('cases', cases), ('seed', '34097'),
                           ('parameters', []), ('asic_inputs', [])])]) + '\n')
        return d, prefix + ['run', '--protocol-version', '1', '--request', str(d / 'request.sexp'),
            '--events', str(d / 'events.sexp'), '--artifact-dir', str(d / 'artifacts')]
    def payloads(d):
        events = [dict(parse(line)) for line in (d / 'events.sexp').read_text().splitlines()]
        assert [int(e['sequence']) for e in events] == list(range(len(events)))
        assert all(e['attempt_id'] == d.name for e in events)
        return [e['payload'] for e in events]
    def execute(d, argv):
        with (d / 'stdout.log').open('xb') as out, (d / 'stderr.log').open('xb') as err:
            code = subprocess.run(argv, stdout=out, stderr=err, timeout=240).returncode
        write(d / 'command.json', {'argv': argv, 'exit_code': code, 'eda_allocation': 0})
        assert code == 0, str(d)
        return payloads(d)
    positive, argv = request('positive-both')
    events = execute(positive, argv)
    assert events[0] == 'Started' and events[-1] == ['Finished', 'Passed'], str(positive)
    results = {}
    for case, policy in (('flops256', 'flops'), ('exact256', 'exact')):
        reference = json.loads((positive / 'artifacts' / (case + '-result-reference.json')).read_text())
        assert set(reference) == {'contract', 'schema_version', 'result', 'source_digest'}
        result = Path(reference['result'])
        assert result.is_relative_to(session / 'project/.dev/asic-pt8-workbench/workloads')
        r = json.loads(result.read_text())
        assert r['counters'] == dict(cycles=1307, reads=525, writes=262, operations=787,
            defined_observations=2083, read_latency=1)
        assert json.loads((result.parent / 'oracle-check.json').read_text()) == {'mismatches': [], 'pass': True}
        # Exact stdout values (including x) must equal the historical real execution.
        old = ROOT / 'acceptance/pt8-workloads/simulation-04' / policy / 'trace.json'
        assert json.loads((result.parent / 'trace.json').read_text()) == json.loads(old.read_text())
        inspection = json.loads((result.parent.parent / 'inspection.json').read_text())
        assert inspection['source_digest'] == reference['source_digest']
        assert inspection['outcome']['functional'] == 'pass'
        wave = result.parent / 'waveform.vcd'
        descriptor = validate_waveform(wave, 1307)
        assert descriptor == json.loads((result.parent / 'waveform.json').read_text())
        copied = positive / 'artifacts' / (case + '-waveform.vcd')
        assert copied.read_bytes() == wave.read_bytes()
        artifact = next(dict(e[1]) for e in events if isinstance(e, list) and e[0] == 'Artifact'
                        and dict(e[1])['id'] == case + '-waveform')
        assert artifact['case_id'] == [case] and artifact['kind'] == 'trace' and artifact['media_type'] == 'text/vcd'
        command = json.loads((result.parent / 'execute/command.json').read_text())
        assert command['cwd'] == str(result.parent) and command['exit_code'] == 0
        assert not (session / 'project/waveform.vcd').exists()
        results[case] = {'result': str(result), 'waveform': descriptor, 'copied': str(copied)}
    # Missing stock model: preceding Flops remains available; Exact announces neither artifact.
    empty = output / 'empty-models'
    empty.mkdir()
    broken = provider.copy()
    broken[broken.index('--model-root') + 1] = str(empty)
    partial, argv = request('missing-model', prefix=broken)
    events = execute(partial, argv)
    assert events[-1] == ['Finished', 'Failed']
    assert (partial / 'artifacts/flops256-waveform.vcd').is_file()
    assert not any(p.name.startswith('exact256') for p in (partial / 'artifacts').iterdir())
    cancel, argv = request('cancelled', cases=('flops256',))
    with (cancel / 'stdout.log').open('xb') as out, (cancel / 'stderr.log').open('xb') as err:
        child = subprocess.Popen(argv, stdout=out, stderr=err)
        deadline = time.monotonic() + 20
        children = []
        while time.monotonic() < deadline and child.poll() is None:
            children = Path(f'/proc/{child.pid}/task/{child.pid}/children').read_text().split()
            if children:
                child.send_signal(signal.SIGTERM)
                break
            time.sleep(.002)
        assert children
        code = child.wait(timeout=10)
        assert code == 130 and all(not Path('/proc/' + pid).exists() for pid in children)
    assert payloads(cancel)[-1] == ['Finished', 'Incomplete']
    assert not list((cancel / 'artifacts').iterdir())
    write(cancel / 'command.json', {'argv': argv, 'exit_code': code, 'children_reaped': children})
    assert all(sha(session / 'provider' / p) == h for p, h in manifest['captured_files'].items())
    before = json.loads(args.preservation.read_text())
    after = protected()
    write(output / 'preservation-after.json', after)
    assert before == after, 'protected root/session/evidence changed'
    write(output / 'assertions.json', {'pass': True, 'results': results, 'cancelled_no_artifacts': True,
        'missing_model_no_false_artifact': True, 'same_historical_raw_outputs': True,
        'protected_files': len(before), 'immutable_provider_unchanged': True, 'eda_allocation': 0})
    print(output)


if __name__ == '__main__':
    main()
