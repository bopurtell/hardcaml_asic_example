#!/usr/bin/env python3
"""Positive PT8 memory workloads using the example's existing exact FS2v1 codec."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
from workbench_paths import ROOT
from wire import Events, parse, record, sexp
from pt8_workbench_runner import Runner, Cancelled, CASES, SEED
from pt8_workloads import validate_waveform, workload, sha

SUITE = 'pt8-memory-workloads'


def catalog():
    return [('protocol_version', 1), ('suites', [[
        ('id', SUITE), ('label', 'PT8 implementation RTL / fixed directed seed 0x8531'),
        ('cases', [[('id', case), ('label', label)] for case, label in (
            ('flops256', 'Flops256 / implementation RTL'),
            ('exact256', 'Exact256 / unchanged stock macro models'))]),
        ('parameters', []), ('default_seed', SEED)]])]


def validate(value):
    req = record(value, ['protocol_version', 'attempt_id', 'selection'])
    if req['protocol_version'] != '1' or not isinstance(req['attempt_id'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', req['attempt_id']):
        raise ValueError('invalid version or attempt ID')
    sel = record(req['selection'], ['suite', 'cases', 'seed', 'parameters', 'asic_inputs'])
    cases = sel['cases']
    if (sel['suite'] != SUITE or not isinstance(cases, list) or not cases or
            any(not isinstance(c, str) or c not in CASES for c in cases) or len(set(cases)) != len(cases)):
        raise ValueError('select unique positive flops256/exact256 cases')
    if sel['seed'] != SEED:
        raise ValueError('only fixed declarative seed 34097 (0x8531) is supported; stimulus is not parametric')
    if sel['parameters'] != [] or sel['asic_inputs'] != []:
        raise ValueError('PT8 takes no parameters or ASIC inputs')
    return req, sel


def run(args):
    req, sel = validate(parse(args.request.read_text()))
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    with args.events.open('a') as stream:
        events = Events(stream, req['attempt_id'])
        events.emit('Started')
        failed = False
        for case in sel['cases']:
            events.emit(['Case_started', case])
            def progress(stage):
                print(f'PT8 {case}: {stage}', flush=True)
                events.emit(['Progress', [('case_id', [case]),
                    ('completed', {'emit': 0, 'simulate': 1, 'inspect': 2}[stage]),
                    ('total', [3]), ('unit_', 'producer stages')]])
            try:
                output, reference, passed = Runner(args.generation, args.emitter,
                    args.model_root, progress, args.producer_root).run(case, sel['seed'], req['attempt_id'])
                artifact_id = case + '-result-reference'
                path = artifact_id + '.json'
                shutil.copyfile(output / 'result-reference.json', args.artifact_dir / path)
                events.emit(['Artifact', [('id', artifact_id), ('case_id', [case]),
                    ('label', case + ' retained workload result'), ('kind', 'json'),
                    ('media_type', 'application/json'), ('path', path)]])
                if passed:
                    # Functional inspection must pass before waveform publication.
                    # Failed inspection still leaves its independent JSON readable.
                    wave = output / CASES[case] / 'waveform.vcd'
                    descriptor = json.loads(wave.with_suffix('.json').read_text())
                    if validate_waveform(wave, len(workload()['operations'])) != descriptor:
                        raise ValueError('retained waveform descriptor mismatch')
                    wave_id = case + '-waveform'
                    wave_path = wave_id + '.vcd'
                    copied = args.artifact_dir / wave_path
                    with wave.open('rb') as source, copied.open('xb') as destination:
                        shutil.copyfileobj(source, destination)
                    if (validate_waveform(copied, descriptor['cycles'])['source']['sha256'] !=
                            descriptor['source']['sha256'] or sha(copied) != descriptor['source']['sha256']):
                        raise ValueError('copied waveform digest mismatch')
                    events.emit(['Artifact', [('id', wave_id), ('case_id', [case]),
                        ('label', case + ' implementation interface waveform'), ('kind', 'trace'),
                        ('media_type', 'text/vcd'), ('path', wave_path)]])
                status, message = ('Passed', []) if passed else ('Failed', ['functional failure; inspect retained result'])
            except Cancelled:
                # Incomplete belongs to the supervisor's normalized state, not
                # provider terminal events. Keep the accepted prefix and partial
                # evidence; FS2 owns cancellation and marks unfinished cases.
                return 130
            except Exception as error:
                print(f'PT8 {case}: {error}', file=sys.stderr, flush=True)
                status, message = 'Failed', [str(error)[:1000]]
            failed |= status != 'Passed'
            events.emit(['Case_finished', [('case_id', case), ('status', status), ('message', message)]])
        events.emit(['Finished', 'Failed' if failed else 'Passed'])
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--producer-root', type=Path, required=True)
    parser.add_argument('--emitter', type=Path, required=True)
    parser.add_argument('--model-root', type=Path, required=True)
    parser.add_argument('operation', choices=['discover', 'run'])
    parser.add_argument('--protocol-version', choices=['1'], required=True)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--events', type=Path)
    parser.add_argument('--artifact-dir', type=Path)
    args = parser.parse_args()
    if args.operation == 'discover':
        print(sexp(catalog()))
        return 0
    if not all((args.request, args.events, args.artifact_dir)):
        parser.error('run requires request, events and artifact-dir')
    return run(args)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
