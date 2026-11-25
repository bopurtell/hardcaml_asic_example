#!/usr/bin/env python3
"""Bounded public-protocol demonstration. Python standard library only."""
import argparse
import json
import math
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time


class ProtocolError(Exception):
    pass


def require(ok, message):
    if not ok:
        raise ProtocolError(message)


def decode(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda s: require(False, 'nonfinite JSON: ' + s))


def envelope(value, contract, version):
    require(isinstance(value, dict) and value.get('contract') == contract
            and type(value.get('schema_version')) is int
            and value['schema_version'] == version,
            'malformed/unsupported ' + contract)
    return value


def absolute(value):
    # Do not normalize '..' across a symlink parent or resolve executable aliases.
    require(isinstance(value, str) and value.startswith('/'), 'explicit absolute path required')
    return value


def query(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, text=True, timeout=30)
    require(result.returncode == 0, 'query failed: ' + repr(argv))
    return decode(result.stdout)


def provider_check(provider):
    metadata = query([provider, '--version', '--json'])
    contract = metadata.get('cli_contract', {})
    require(type(contract.get('version')) is int and contract['version'] == 4
            and contract.get('capabilities', {}).get('namedflow1') is True,
            'exact CLI4 + namedflow1=true required')
    return metadata


def save(path, receipt):
    # Client cache only; never writes into provider-owned attempt directories.
    temporary = path + '.pending'
    with open(temporary, 'w', encoding='utf-8') as out:
        json.dump(receipt, out, indent=2, sort_keys=True)
        out.write('\n')
    os.replace(temporary, path)


def observe(receipt, path):
    provider = receipt['config']['provider']
    attempt, stream = receipt['allocation']['attempt'], receipt['allocation']['stream_id']
    after = receipt['cursor']
    updates = envelope(query([provider, 'observation', 'read-updates', attempt,
                              '--stream-id', stream, '--after', str(after), '--json']),
                       'hardcaml-asic.stage-observation', 2)
    require(updates.get('stream_id') == stream and updates.get('after') == after,
            'update stream/cursor mismatch')
    cursor = updates.get('cursor')
    require(type(cursor) is int and cursor >= after, 'invalid update cursor')
    require(isinstance(updates.get('events'), list), 'missing events')
    for event in updates['events']:
        envelope(event, 'hardcaml-asic.stage-observation', 2)
        require(event.get('stream_id') == stream and type(event.get('sequence')) is int
                and after < event['sequence'] <= cursor, 'invalid event stream/sequence')
        after = event['sequence']
    receipt['updates'].append(updates)
    receipt['cursor'] = cursor
    status = envelope(query([provider, 'observation', 'inspect', attempt, '--json']),
                      'hardcaml-asic.stage-observation', 2)
    require(status.get('stream_id') == stream and type(status.get('writer_active')) is bool,
            'invalid reader status')
    require(type(status.get('cursor')) is int and status['cursor'] >= cursor,
            'inspection cursor regressed')
    receipt['inspection'] = status
    methodology = envelope(status.get('methodology'), 'hardcaml-asic.historical-methodology', 1)
    require(methodology.get('state') in ('pending', 'recorded'), 'named methodology missing')
    if methodology['state'] == 'pending':
        launch = methodology.get('launch', {})
        require(launch.get('attempt_id') == stream
                and launch.get('expected_plan_identity') == receipt['plan_identity'],
                'pending methodology identity mismatch')
    if methodology['state'] == 'recorded':
        require(methodology.get('plan_identity') == receipt['plan_identity']
                and methodology.get('bundle_identity') == receipt['plan']['bundle_identity']
                and methodology.get('reference', {}).get('attempt_id') == stream,
                'inspection methodology identity mismatch')
    receipt['outcome'] = status.get('state', {}).get('outcome')
    receipt['final_results'] = status.get('final_results')
    save(path, receipt)
    # Inactive writer alone is NOT proof of a terminal outcome.
    return (status.get('observation_status') == 'final'
            and status['writer_active'] is False and receipt['outcome'] is not None
            and status['cursor'] == cursor)


def finish(receipt, path):
    for key in ('blocker', 'report', 'report_status', 'execution_file'):
        receipt.pop(key, None)
    outcome = receipt.get('outcome') or {}
    completed = outcome.get('status') == 'completed' and outcome.get('exit_code') == 0
    receipt['execution_completed'] = completed
    receipt['acceptance'] = (receipt.get('final_results') or {}).get('acceptance', 'not_evaluated')
    # Only follow public explicit references, never workspace + guessed basename.
    execution = receipt['inspection'].get('execution_file')
    delivered = [v['execution_file'] for v in receipt['launcher_messages'] if v.get('execution_file')]
    require(all(value == execution for value in delivered), 'terminal/inspection execution reference mismatch')
    if execution:
        receipt['execution_file'] = absolute(execution)
        report = envelope(query([receipt['config']['provider'], 'report', execution, '--json']),
                          'hardcaml-asic.report', 1)
        methodology = envelope(report.get('methodology'), 'hardcaml-asic.historical-methodology', 1)
        require(methodology.get('state') == 'recorded'
                and methodology.get('plan_identity') == receipt['plan_identity']
                and methodology.get('bundle_identity') == receipt['plan']['bundle_identity']
                and methodology.get('reference', {}).get('attempt_id') == receipt['allocation']['stream_id']
                and report.get('execution', {}).get('attempt_id') == receipt['allocation']['stream_id'],
                'report methodology identity mismatch')
        receipt['report'] = report
        receipt['report_status'] = 'available'
    elif completed:
        receipt['blocker'] = ('Provider completed execution but returned no explicit execution_file '
                              'reference; cannot request terminal report without reconstructing a path.')
    else:
        receipt['report_status'] = 'unavailable_no_execution_record'
    save(path, receipt)
    return 0 if completed and not receipt.get('blocker') else 1


def run(args):
    path = absolute(args.receipt)
    if args.reconnect:
        with open(path, encoding='utf-8') as inp:
            receipt = envelope(decode(inp.read()), 'example.headless-result', 1)
        receipt['config'].setdefault('stage_timeout', None)
        provider_check(absolute(receipt['config']['provider']))
        require(receipt.get('allocation'), 'receipt has no allocation to reconnect')
        deadline = time.monotonic() + args.timeout
        while not observe(receipt, path):
            require(time.monotonic() < deadline, 'reader timeout; run was not signalled')
            time.sleep(args.poll)
        return finish(receipt, path)

    require(not os.path.exists(path), 'receipt already exists; use --reconnect')
    for key in ('project', 'provider', 'source_root', 'results_root', 'toolchain'):
        absolute(getattr(args, key))
    require(not args.profile or args.flow, '--profile requires --flow')
    # Keep cache outside provider results (realpath comparison only, never used for exec).
    require(os.path.commonpath([os.path.realpath(path), os.path.realpath(args.results_root)])
            != os.path.realpath(args.results_root), 'client receipt must be separate from provider results')
    metadata = provider_check(args.provider)
    listing = envelope(query([args.project, 'flow', 'list', '--json']), 'hardcaml-asic.flow-list', 1)
    catalog = envelope(listing['declaration'], 'hardcaml-asic.flow-catalog', 1)
    flow = args.flow or catalog['default']['flow']
    entries = [e for e in catalog['entries'] if e['methodology']['id'] == flow]
    require(len(entries) == 1, 'unknown/duplicate flow')
    entry = entries[0]
    profile = args.profile or (entry['default_profile'] if args.flow else catalog['default']['profile'])
    require(sum(p['id'] == profile for p in entry['profiles']) == 1, 'unknown/duplicate profile')
    description = envelope(query([args.project, 'flow', 'describe', '--flow', flow, '--json']),
                           'hardcaml-asic.flow-describe', 1)
    options = ['--flow', flow, '--profile', profile, '--endpoint', args.endpoint,
               '--source-root', args.source_root, '--json']
    for assignment in args.set:
        options += ['--set', assignment]
    plan = envelope(query([args.project, 'flow', 'plan', *options]),
                    'hardcaml-asic.methodology-plan', 1)
    identity = plan.get('plan_identity')
    require(isinstance(identity, str) and re.fullmatch('[0-9a-f]{64}', identity), 'invalid plan identity')
    receipt = dict(contract='example.headless-result', schema_version=1,
                   config={k: getattr(args, k) for k in ('project', 'provider', 'source_root', 'results_root', 'toolchain', 'timeout', 'stage_timeout')},
                   metadata=metadata, discovery=listing, description=description, plan=plan,
                   selection=dict(flow=flow, profile=profile, endpoint=args.endpoint),
                   plan_identity=identity, allocation=None, cursor=0, updates=[], launcher_messages=[])
    launch = [args.project, 'flow', 'run', *options, '--expected-plan-identity', identity,
              '--provider', args.provider, '--results-root', args.results_root, '--toolchain', args.toolchain]
    if args.stage_timeout is not None:
        launch += ['--timeout', str(args.stage_timeout)]
    for key in ('python', 'support_tools', 'pdk_root'):
        if getattr(args, key):
            launch += ['--' + key.replace('_', '-'), absolute(getattr(args, key))]
    receipt['launch_argv'] = launch
    save(path, receipt)
    if args.preview_only:
        return 0
    messages = queue.Queue()
    process = None
    thread = None
    def read():
        try:
            for line in process.stdout:
                messages.put(line)
        finally:
            messages.put(None)
    try:
        process = subprocess.Popen(launch, stdout=subprocess.PIPE, text=True)
        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        deadline = time.monotonic() + args.timeout
        eof = False
        while not eof:
            require(time.monotonic() < deadline, 'owned launcher timeout')
            try:
                line = messages.get(timeout=args.poll)
                if line is None:
                    eof = True
                else:
                    value = decode(line)
                    require(isinstance(value, dict), 'launcher JSON object required')
                    if value.get('event') in ('observation_allocated', 'observation_terminal'):
                        envelope(value, 'hardcaml-asic.stage-observation', 1)
                    else:
                        # CLI4 Runner summaries have no outer schema discriminator.
                        # Their nested stage plan and named reference are versioned.
                        require('schema_version' not in value and 'contract' not in value
                                and receipt['allocation'] is not None
                                and value.get('attempt_id') == receipt['allocation']['stream_id']
                                and value.get('status') in ('completed', 'failed', 'interrupted')
                                and type(value.get('exit_code')) is int
                                and isinstance(value.get('occurrences'), list),
                                'malformed CLI4 execution summary')
                        stage_plan = value.get('plan', {})
                        require(type(stage_plan.get('schema_version')) is int
                                and stage_plan['schema_version'] in (3, 4)
                                and isinstance(stage_plan.get('stages'), list),
                                'unsupported execution stage plan')
                        reference = envelope(value.get('methodology'),
                                             'hardcaml-asic.methodology-execution-reference', 1)
                        require(reference.get('plan_identity') == identity
                                and reference.get('expected_plan_identity') == identity
                                and reference.get('attempt_id') == value['attempt_id'],
                                'execution methodology identity mismatch')
                        absolute(reference['snapshot_path'])
                    receipt['launcher_messages'].append(value)
                    if value.get('event') == 'observation_allocated':
                        require(receipt['allocation'] is None, 'duplicate allocation')
                        absolute(value['attempt'])
                        require(isinstance(value.get('stream_id'), str) and value['stream_id'], 'missing stream')
                        receipt['allocation'] = value
                    save(path, receipt)
            except queue.Empty:
                pass
            if receipt['allocation']:
                observe(receipt, path)
        receipt['launcher_exit'] = process.wait(timeout=5)
        require(receipt['allocation'], 'launcher exited before allocation (stale plan or launch failure)')
        while not observe(receipt, path):
            require(time.monotonic() < deadline, 'launcher exited without terminal observation')
            time.sleep(args.poll)
        result = finish(receipt, path)
        return result if receipt['launcher_exit'] == 0 else 1
    except BaseException as exc:
        receipt['client_error'] = {'type': type(exc).__name__, 'detail': str(exc)}
        receipt['client_status'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
        receipt['reconnect_available'] = receipt['allocation'] is not None
        raise
    finally:
        # A second user signal must not interrupt reaping the child we own.
        handlers = {sig: signal.signal(sig, signal.SIG_IGN)
                    for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            if process is not None:
                if process.poll() is None:
                    # Only this invocation's launcher; reconnect never signals it.
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                # Construction/start may fail, including after the thread started.
                # Never join an unstarted thread or block closing a pipe held by a reader.
                if thread is not None and thread.ident is not None:
                    thread.join(timeout=1)
                if thread is None or not thread.is_alive():
                    process.stdout.close()
                receipt['launcher_exit'] = process.returncode
            save(path, receipt)
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'provider', 'source-root', 'results-root', 'toolchain',
                 'python', 'support-tools', 'pdk-root', 'flow', 'profile', 'endpoint'):
        parser.add_argument('--' + name)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--set', action='append', default=[])
    parser.add_argument('--reconnect', action='store_true')
    parser.add_argument('--preview-only', action='store_true')
    parser.add_argument('--poll', type=float, default=0.1)
    parser.add_argument('--timeout', type=float, default=600,
                        help='overall client budget in seconds (default: 600); reconnect bounds only the reader')
    parser.add_argument('--stage-timeout', type=int,
                        help='positive integer seconds per provider segment/publication; omitted uses provider default 600')
    args = parser.parse_args()
    try:
        require(math.isfinite(args.poll) and args.poll > 0
                and math.isfinite(args.timeout) and args.timeout > 0, 'positive finite poll/timeout required')
        require(args.stage_timeout is None or args.stage_timeout > 0,
                '--stage-timeout requires positive integer seconds')
        if not args.reconnect:
            require(args.endpoint, '--endpoint required')
        return run(args)
    except (ProtocolError, ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print('headless client: ' + str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('headless client cancelled; owned launcher received SIGTERM (reader-only reconnect signals no run)', file=sys.stderr)
        return 130


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    sys.exit(main())
