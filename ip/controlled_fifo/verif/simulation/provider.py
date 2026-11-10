#!/usr/bin/env python3
"""Project-owned real Controlled_fifo FS2v1 provider. Never builds or installs."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'integration/workbench'))
from wire import Events, parse, record, sexp

SUITE = 'controlled-fifo'
CASES = ('directed', 'seeded')
PARAMETERS = {'cycles': ('4096', ['64', '4096', '20000']),
              'checker': ('normal', ['normal', 'mismatch'])}


def catalog():
    return [('protocol_version', 1), ('suites', [[
        ('id', SUITE), ('label', 'Controlled FIFO / independent list checker'),
        ('cases', [[('id', case), ('label', 'FIFO ' + case)] for case in CASES]),
        ('parameters', [[('key', k), ('label', k), ('default', default), ('choices', choices)]
                        for k, (default, choices) in sorted(PARAMETERS.items())]),
        ('default_seed', '42')]])]


def validate(value):
    req = record(value, ['protocol_version', 'attempt_id', 'selection'])
    if req['protocol_version'] != '1' or not isinstance(req['attempt_id'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', req['attempt_id']):
        raise ValueError('invalid version or attempt ID')
    sel = record(req['selection'], ['suite', 'cases', 'seed', 'parameters', 'asic_inputs'])
    cases = sel['cases']
    if sel['suite'] != SUITE or not isinstance(cases, list) or not cases or any(not isinstance(c, str) for c in cases) or len(set(cases)) != len(cases) or not set(cases) <= set(CASES):
        raise ValueError('select unique declared FIFO cases')
    seed = sel['seed']
    if not isinstance(seed, str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}', seed) or int(seed) >= 2**64:
        raise ValueError('seed must be canonical uint64')
    params = record(sel['parameters'], PARAMETERS)
    if any(not isinstance(params[k], str) or params[k] not in choices for k, (_, choices) in PARAMETERS.items()):
        raise ValueError('invalid FIFO parameter choice')
    if sel['asic_inputs'] != []:
        raise ValueError('FIFO simulation takes no ASIC inputs')
    return req, sel, params


def run(args):
    req, sel, params = validate(parse(args.request.read_text()))
    words = ','.join(str((int(sel['seed']) >> shift) & 65535) for shift in (0, 16, 32, 48))
    failed = False
    with args.events.open('a') as stream:
        events = Events(stream, req['attempt_id'])
        events.emit('Started')
        for case in sel['cases']:
            events.emit(['Case_started', case])
            print(f"FIFO {case} seed={sel['seed']} words={words} parameters={params}", flush=True)
            process = subprocess.Popen([str(args.simulator), case, sel['seed'], words, params['cycles'],
                                        str(args.artifact_dir / (case + '.vcd')),
                                        str(args.artifact_dir / (case + '.sexp')), params['checker']],
                                       stdout=subprocess.PIPE, text=True)
            status = None
            message = None
            for line in process.stdout:
                print(line, end='', flush=True)
                if line.startswith('PROGRESS '):
                    _, completed, total = line.split()
                    events.progress(case, int(completed), int(total))
                elif line.startswith('CHECK_FAILED ') and message is None:
                    # Keep the case row concise; full stimulus/history remain in
                    # native stdout and the immutable native report artifact.
                    message = line.split('(trace', 1)[0].strip() + ' (see native report)'
                elif line.startswith('RESULT '):
                    status = line.split()[1]
            if process.wait() != 0 or status not in ('Passed', 'Failed'):
                raise RuntimeError('native simulator failed without a complete result')
            failed |= status == 'Failed'
            events.artifact(case, case + '.vcd', 'waveform', 'text/x-vcd')
            events.artifact(case, case + '.sexp', 'failure-report' if status == 'Failed' else 'report', 'text/plain')
            events.emit(['Case_finished', [('case_id', case), ('status', status),
                                             ('message', [] if message is None else [message])]])
        events.emit(['Finished', 'Failed' if failed else 'Passed'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', type=Path, default=Path(__file__).resolve().with_name('fifo_sim.exe'))
    parser.add_argument('operation', choices=['discover', 'run'])
    parser.add_argument('--protocol-version', required=True, choices=['1'])
    parser.add_argument('--request', type=Path)
    parser.add_argument('--events', type=Path)
    parser.add_argument('--artifact-dir', type=Path)
    args = parser.parse_args()
    if args.operation == 'discover':
        print(sexp(catalog()))
    else:
        if not all((args.request, args.events, args.artifact_dir)):
            parser.error('run requires request, events, artifact-dir')
        run(args)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
