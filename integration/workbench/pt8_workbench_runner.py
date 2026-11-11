#!/usr/bin/env python3
"""Reusable positive-only PT8 producer. No builds, no detached children, no EDA."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

from workbench_paths import ROOT
import pt8_workloads as producer

STORE = ROOT / '.dev/asic-pt8-workbench'
CASES = {'flops256': 'flops', 'exact256': 'exact'}
SEED = '34097'


class Cancelled(Exception):
    pass


class Runner:
    def __init__(self, generation, emitter, model_root, progress=lambda stage: None, root=ROOT,
                 output_root=None):
        global ROOT, STORE
        ROOT = Path(root).resolve(strict=True)
        STORE = ROOT / '.dev/asic-pt8-workbench'
        self.generation = Path(generation).resolve(strict=True)
        self.emitter = Path(emitter).resolve(strict=True)
        self.model_root = Path(model_root).resolve(strict=True)
        self.progress = progress
        self.output_root = Path(output_root) if output_root is not None else STORE / 'workloads'
        self.child = None

    def cancel(self, signum, frame):
        # Also works when only the provider PID is signalled. FS2 normally signals
        # the inherited whole process group. Never create a new session/group.
        if self.child is not None:
            if self.child.poll() is None:
                self.child.terminate()
            try:
                self.child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()
        raise Cancelled(f'cancelled by signal {signum}')

    def command(self, output, label, argv, *unused, **kwargs):
        directory = output / label
        directory.mkdir()
        argv = list(map(str, argv))
        env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
        started = time.monotonic()
        cwd = kwargs.get('cwd', ROOT)
        code = None
        print('PT8 ' + label + ': ' + ' '.join(argv), flush=True)
        try:
            with (directory / 'stdout.log').open('xb') as out, (directory / 'stderr.log').open('xb') as err:
                self.child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=err)
                code = self.child.wait(timeout=180)
            if code:
                raise RuntimeError(f'{label} exit {code}; see {directory}')
        finally:
            if self.child is not None and self.child.poll() is None:
                self.child.kill()
                self.child.wait()
            producer.write(directory / 'command.json', {
                'argv': argv, 'cwd': str(cwd), 'exit_code': code,
                'child_exit_code': self.child.returncode if self.child else None,
                'elapsed_seconds': time.monotonic() - started,
                'max_parallel_processes': 1, 'eda_allocation': 0})
            self.child = None
        return directory / 'stdout.log'

    def run(self, case, seed, attempt):
        if case not in CASES or seed != SEED:
            raise ValueError('only flops256/exact256 and fixed declarative seed 34097 are supported')
        root = self.output_root
        root.mkdir(parents=True, exist_ok=True)
        output = root / (case + '-' + uuid.uuid4().hex)
        output.mkdir()
        producer.write(output / 'request.json', {'fs2_attempt_id': attempt, 'case': case,
            'seed': seed, 'seed_semantics': 'fixed-directed-stimulus-identity-not-parametric',
            'producer_root': str(ROOT), 'generation': str(self.generation),
            'emitter': str(self.emitter), 'emitter_sha256': producer.sha(self.emitter)})
        previous = {s: signal.signal(s, self.cancel) for s in (signal.SIGINT, signal.SIGTERM)}
        outcome = {'status': 'partial', 'result': None}
        try:
            # Reuse the existing directed stimulus, implementation testbench, trace
            # and PT8 evidence writer without modifying historical acceptance code.
            producer.command = self.command
            os.environ['PT8_VENDOR_MODEL_ROOT'] = str(self.model_root)
            w = producer.workload()
            w['identity'] = producer.identity(w)
            producer.write(output / 'workload.json', w)
            self.progress('emit')
            policy = CASES[case]
            emitted = json.loads(self.command(output, 'emit', [self.emitter, ROOT,
                policy, output / 'bundles']).read_text())
            producer.write(output / 'emitted.json', emitted)
            self.progress('simulate')
            producer.simulate(output, policy, emitted, w, capture_waveform=True)
            result = output / policy / 'result.json'
            self.progress('inspect')
            inspected = json.loads(self.command(output, 'inspect', [
                self.generation / 'bin/hardcaml-asic-flow', 'workload-inspect', result,
                '--json']).read_text())
            producer.write(output / 'inspection.json', inspected)
            passed = inspected['outcome']['functional'] == 'pass'
            reference = {'contract': 'hardcaml-workbench.pt8-result-reference',
                'schema_version': 1, 'result': str(result.resolve()),
                'source_digest': inspected['source_digest']}
            producer.write(output / 'result-reference.json', reference)
            outcome = {'status': 'passed' if passed else 'failed', 'result': str(result),
                       'source_digest': inspected['source_digest']}
            return output, reference, passed
        except Cancelled as error:
            outcome['status'] = 'cancelled'
            outcome['error'] = str(error)
            raise
        except Exception as error:
            outcome['status'] = 'partial'
            outcome['error'] = str(error)
            raise
        finally:
            producer.write(output / 'outcome.json', outcome)
            producer.write(output / 'inventory.json', {
                str(p.relative_to(output)): {'sha256': producer.sha(p), 'bytes': p.stat().st_size}
                for p in sorted(output.rglob('*')) if p.is_file()})
            for s, handler in previous.items():
                signal.signal(s, handler)
