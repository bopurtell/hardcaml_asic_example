#!/usr/bin/env python3
"""Run real checkout providers in pairs, with evidence isolated from Silver history."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/workbench'))
from wire import parse, record, sexp


def pair(base, command, selections):
    children, logs, streams, observed = {}, {}, {}, {}
    base.mkdir()
    try:
        for name, suite, cases, seed, parameters in selections:
            run = base / name
            artifacts = run / 'artifacts'
            artifacts.mkdir(parents=True)
            request, events = run / 'request.sexp', run / 'events.sexp'
            request.write_text(sexp([('protocol_version', 1), ('attempt_id', name),
                ('selection', [('suite', suite), ('cases', cases), ('seed', seed),
                               ('parameters', parameters), ('asic_inputs', [])])]) + '\n')
            logs[name] = (run / 'provider.log').open('w+')
            streams[name] = events
            children[name] = subprocess.Popen(
                [*command, 'run', '--protocol-version', '1', '--request', request,
                 '--events', events, '--artifact-dir', artifacts],
                cwd=ROOT, stdout=logs[name], stderr=subprocess.STDOUT, start_new_session=True)
        start = time.monotonic()
        while True:
            finished = all(child.poll() is not None for child in children.values())
            for name, events in streams.items():
                if not events.exists():
                    continue
                # Discard a partial last line while the other process is writing.
                for sequence, line in enumerate(events.read_text().split('\n')[:-1]):
                    fields = record(parse(line), ('protocol_version', 'attempt_id', 'sequence', 'payload'))
                    assert fields['attempt_id'] == name and fields['sequence'] == str(sequence), fields
                    for label, payload in [('started', 'Started'), ('passed', ['Finished', 'Passed'])]:
                        if fields['payload'] == payload:
                            observed.setdefault((name, label), time.monotonic() - start)
            if finished or time.monotonic() - start > 30:
                break
            time.sleep(.002)
        for name, child in children.items():
            logs[name].seek(0)
            assert child.poll() == 0 and (name, 'passed') in observed, logs[name].read()
            print(f"{name}: Started +{observed[name, 'started']:.3f}s; "
                  f"passed +{observed[name, 'passed']:.3f}s")
        assert max(observed[name, 'started'] for name in children) < min(
            observed[name, 'passed'] for name in children), observed
    finally:
        for child in children.values():
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for log in logs.values():
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path,
                        default=ROOT / '.dev/workbench-main/simulation/manifest.json')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    with tempfile.TemporaryDirectory(prefix='silver-simulation-overlap-') as temp:
        base = Path(temp)
        workloads = base / 'workloads'
        memory = manifest['provider_commands']['memory-workloads']
        memory[memory.index('--output-root') + 1] = str(workloads)
        private_manifest = base / 'manifest.json'
        private_manifest.write_text(json.dumps(manifest))
        command = manifest['provider_command'].copy()
        command[command.index('--manifest') + 1] = str(private_manifest)
        pair(base / 'mixed', command, [
            ('fifo', 'controlled-fifo', ['seeded', 'export-stress'], 42,
             [('checker', 'normal'), ('cycles', '20000'), ('trace_mib', '16')]),
            ('memory', 'memory-workloads', ['exact256', 'flops256'], 34097, []),
        ])
        for attempt, names in [
            ('fifo', ('seeded.vcd', 'seeded.sexp', 'export-stress.vcd', 'export-stress.sexp')),
            ('memory', ('exact256-waveform.vcd', 'flops256-waveform.vcd')),
        ]:
            for name in names:
                artifact = base / 'mixed' / attempt / 'artifacts' / name
                assert artifact.is_file() and artifact.stat().st_size > 0, artifact
        pair(base / 'same-case', command, [
            (f'same-{i}', 'memory-workloads', ['exact256'], 34097, []) for i in (1, 2)
        ])
        results = set()
        for i in (1, 2):
            attempt = f'same-{i}'
            artifact = base / 'same-case' / attempt / 'artifacts/exact256-result-reference.json'
            result = Path(json.loads(artifact.read_text())['result'])
            assert result.is_relative_to(workloads) and result.is_file(), result
            assert json.loads((result.parents[1] / 'request.json').read_text())['fs2_attempt_id'] == attempt
            results.add(result)
        assert len(results) == 2


if __name__ == '__main__':
    main()
