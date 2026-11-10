#!/usr/bin/env python3
"""Private prebuilt Workbench HTTP/PTY smoke, supervised by this foreground owner."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import uuid
import importlib.util

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
WB = ROOT.parent / 'hardcaml_workbench'
sys.path.insert(0, str(WB / 'demo/synthetic_flow'))
from http_client import Client, field, sexp, parse
from pt8_acceptance import write, sha


class Terminal:
    def __init__(self, command, env, output):
        self.output = output
        self.height, self.width = 46, 150
        self.data = bytearray()
        spec = importlib.util.spec_from_file_location('pt8_screen', WB / 'scripts/test-fs0.py')
        emulator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(emulator)
        self.screen = emulator.terminal_screen
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 46, 150, 0, 0))
        self.child = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)

    def drain(self, seconds=.25):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], .05)[0]:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    break
                if not data:
                    break
                self.data.extend(data)
        assert self.child.poll() is None, 'production terminal exited'
        return self.screen(bytes(self.data), width=self.width, height=self.height)

    def capture(self, label, expected=()):
        deadline = time.monotonic() + 15
        while True:
            text = self.drain()
            if all(s.casefold() in text.casefold() for s in expected):
                break
            if time.monotonic() >= deadline:
                self.save(label, text)
                raise AssertionError(f'{label}: expected {expected!r}\n{text}')
        self.save(label, text)
        return text

    def save(self, label, text):
        (self.output / (label + '.txt')).write_text(text)
        (self.output / (label + '.ansi')).write_bytes(self.data)

    def key(self, value):
        os.write(self.master, value)
        return self.drain(.15)

    def palette(self, title):
        for key in (b' ', b'c', b'c'):
            self.key(key)
        self.key(title.encode())
        self.capture('palette-' + str(time.time_ns()), [title])
        self.key(b'\r')
        self.drain(.4)

    def resize(self, height, width):
        self.height, self.width = height, width
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        self.child.send_signal(signal.SIGWINCH)
        self.drain(.4)

    def close(self):
        self.child.terminate()
        self.child.wait(timeout=10)
        os.close(self.master)
        (self.output / 'pty-all.ansi').write_bytes(self.data)


def protected_state():
    """Only read root configuration and the exact programs it currently selects."""
    from http_client import parse
    paths = list(ROOT.glob('hardcaml-workbench*.sexp')) + [ROOT / 'asic-dependency.json']
    for path in list(paths):
        if path.suffix != '.sexp':
            continue
        values = dict(parse(path.read_text()))
        for key in ('provider_executable', 'project_executable'):
            if key in values:
                paths.append(Path(values[key]))
    return {str(p): {'sha256': sha(p), 'symlink': os.readlink(p) if p.is_symlink() else None}
            for p in sorted(set(paths)) if p.is_file()}


def installed_state(session, manifest):
    paths = list((session / 'provider').rglob('*'))
    paths += list(Path(manifest['generation']).rglob('*'))
    paths += list((session / 'project').glob('*.sexp'))
    paths += list((session / 'tool-bin').glob('*'))
    return {str(p): sha(p) for p in sorted(paths) if p.is_file()}


def retained_state(results):
    roots = {path.parent for path in results}
    roots.update(Path(json.loads(path.read_text())['bundle']) for path in results)
    return {str(p): sha(p) for root in sorted(roots) for p in sorted(root.rglob('*')) if p.is_file()}


def review_evidence(output):
    """Summarize the retained native wire/PTY evidence, including a blocked gate."""
    history = json.loads((output / 'http.json').read_text())
    details = []
    inspections = []
    comparisons = []
    for item in history:
        response = parse(item['response'])
        if item['path'] == '/api/v1/simulation' and response[0] == 'Ok':
            detail = dict(response[1]).get('detail', [])
            if detail and dict(detail[0])['lifecycle'] == 'Finished':
                details.append(dict(detail[0]))
        if item['path'] == '/api/v1/asic' and response[0] == 'Ok':
            workloads = dict(response[1]).get('workloads', [])
            if not workloads:
                continue
            selected = dict(workloads[0]).get('selected', [])
            if selected:
                document = json.loads(dict(selected[0])['json'])
                if document['contract'] == 'hardcaml-asic.workload-inspection':
                    inspections.append(document)
                else:
                    comparisons.append(document)
    ui_detail = next(d for d in reversed(details) if dict(dict(d['captured'])['selection'])['cases'] == ['exact256'])
    metrics = [m for m in comparisons[-1]['metrics'] if m['metric_id'].startswith('workload/')]
    artifacts = [dict(a) for a in ui_detail['artifacts']]
    blocked = output / 'ui-artifact-workloads-handoff.txt'
    summary = dict(json.loads((output / 'assertions.json').read_text()),
        actual_ui_fs2_attempt=ui_detail['id'], actual_ui_case='exact256',
        ui_form_launch_passed=ui_detail['outcome'] == 'Passed',
        native_artifact_ids=[a['id'] for a in artifacts],
        ui_handoff_blocked=blocked.exists() and 'No matching commands' in blocked.read_text(),
        public_comparison_seven_zero_deltas=len(metrics) == 7 and all(
            m['comparison'] == 'comparable' and m['right_minus_left'] == 0 for m in metrics),
        readable_failure_performance_unavailable=any(d['outcome']['functional'] == 'fail' and
            d['outcome']['performance'] == 'unavailable' for d in inspections),
        source='retained actual HTTP/PTY evidence; no new execution')
    write(output / 'reviewed-summary.json', summary)
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--direct-acceptance', type=Path)
    parser.add_argument('--review-evidence', type=Path)
    parser.add_argument('--audit-only', action='store_true')
    parser.add_argument('--baseline-evidence', type=Path)
    args = parser.parse_args()
    if args.review_evidence:
        return review_evidence(args.review_evidence.resolve(strict=True))
    if args.audit_only:
        if not args.session or not args.baseline_evidence:
            parser.error('audit requires session and baseline-evidence')
        session = args.session.resolve(strict=True)
        manifest = json.loads((session / 'manifest.json').read_text())
        output = session / ('final-audit-' + uuid.uuid4().hex)
        output.mkdir()
        roots = protected_state()
        write(output / 'root-protected-final.json', roots)
        write(output / 'installed-final.json', installed_state(session, manifest))
        assertions = {'root_configs_and_selected_providers_unchanged': roots == json.loads(
            (args.baseline_evidence / 'root-protected-before.json').read_text()),
            'immutable_provider_matches_capture': manifest['captured_files'] == {
                name: sha(session / 'provider' / name) for name in manifest['captured_files']},
            'asic_generation': manifest['generation'],
            'asic_receipt_sha256': sha(Path(manifest['generation']) / 'receipt.json'),
            'workload_reader_source_matches_capture': sha(session / 'asic-source/execution/results/workload_result.ml') ==
                sha(ROOT.parent / 'hardcaml_asic/execution/results/workload_result.ml'),
            'private_configs': {str(p): sha(p) for p in (session / 'project').glob('*.sexp')},
            'scope': 'read-only final audit; no daemon, producer, build or EDA launched'}
        write(output / 'assertions.json', assertions)
        assert assertions['root_configs_and_selected_providers_unchanged']
        assert assertions['immutable_provider_matches_capture']
        print(str(output))
        return
    if not args.session or not args.direct_acceptance:
        parser.error('requires session and direct-acceptance')
    session = args.session.resolve(strict=True)
    manifest = json.loads((session / 'manifest.json').read_text())
    direct = json.loads((args.direct_acceptance / 'assertions.json').read_text())
    assert direct['pass']
    build = Path(manifest['wb_build_root']) / 'default'
    for p in (build / 'daemon/main.exe', build / 'terminal/main.exe'):
        if not p.is_file():
            parser.error('A/B prebuilt main is not ready: ' + str(p))
    output = session / ('native-acceptance-' + uuid.uuid4().hex)
    output.mkdir()
    protected_before = protected_state()
    write(output / 'root-protected-before.json', protected_before)
    installed_before = {name: sha(session / 'provider' / name) for name in manifest['captured_files']}
    assert installed_before == manifest['captured_files'], 'configured provider capture changed'
    full_install_before = installed_state(session, manifest)
    write(output / 'installed-before.json', full_install_before)
    left = ROOT / 'acceptance/pt8-workloads/simulation-04/flops/result.json'
    right = ROOT / 'acceptance/pt8-workloads/simulation-04/exact/result.json'
    failed = ROOT / 'acceptance/pt8-workloads/simulation-04/ignored-workload/result.json'
    retained_before = retained_state([left, right, failed])
    write(output / 'retained-before.json', retained_before)
    launch = [sys.executable, '-B', str(ROOT / 'scripts/pt8_workbench_launch.py')]
    env = dict(os.environ, TERM='xterm-256color', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    http = None
    result = {'pass': False, 'session': str(session), 'wb_binaries': {
        str(p): sha(p) for p in (build / 'daemon/main.exe', build / 'terminal/main.exe')}}
    result.update(provider_generation=manifest['generation'],
        provider_receipt_sha256=sha(Path(manifest['generation']) / 'receipt.json'),
        inspection_companion_sha256=sha(Path(manifest['generation']) / 'bin/hardcaml-asic-experimental-workload-inspect'),
        comparison_companion_sha256=sha(Path(manifest['generation']) / 'bin/hardcaml-asic-experimental-compare'))
    write(output / 'invocation.json', {'argv': sys.argv, 'cwd': str(Path.cwd()),
        'prebuilt_only': True, 'eda_allocation': 0})
    with (output / 'daemon.stdout').open('xb') as out, (output / 'daemon.stderr').open('xb') as err:
        trace = output / 'process.strace'
        started_ns = time.time_ns()
        daemon = subprocess.Popen(['strace', '-f', '-s', '4096', '-e', 'trace=process', '-o', str(trace), '--',
            *launch, 'daemon', '--session', str(session)], stdout=out, stderr=err, env=env)
        owned_pid = None
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                metadata_path = session / 'discovery/daemon.sexp'
                if metadata_path.exists():
                    from http_client import parse
                    metadata = dict(parse(metadata_path.read_text()))
                    children = Path(f'/proc/{daemon.pid}/task/{daemon.pid}/children').read_text().split()
                    if metadata_path.stat().st_mtime_ns >= started_ns and metadata['pid'] in children:
                        owned_pid = int(metadata['pid'])
                        break
                assert daemon.poll() is None, 'private daemon failed; see retained logs'
                time.sleep(.05)
            else:
                raise TimeoutError('private daemon readiness')
            http = Client(metadata['endpoint'], manifest['project_root'])
            def rpc(domain, operation='Get', wait=False):
                return http.rpc(sexp(operation) if not isinstance(operation, str) else operation,
                                domain=domain, wait=wait)
            def inspect(path, digest=None):
                snapshot = rpc('asic', ['Workloads', ['Load', ['query', ['Inspect',
                    ['result', str(path)], ['expected_digest', [] if digest is None else [digest]]]],
                    ['refresh', 'true']]], wait=True)
                workloads = field(snapshot, 'workloads')[0]
                selected = field(workloads, 'selected')[0]
                return json.loads(field(selected, 'json'))
            left_view, right_view = inspect(left), inspect(right)
            assert left_view['outcome']['functional'] == right_view['outcome']['functional'] == 'pass'
            left_bundle, right_bundle = left_view['binding']['bundle'], right_view['binding']['bundle']
            assert left_bundle == str(Path(json.loads(left.read_text())['bundle']).resolve(strict=True))
            assert right_bundle == str(Path(json.loads(right.read_text())['bundle']).resolve(strict=True))
            write(output / 'retained-fresh-reader.json', {'left': left_view, 'right': right_view})
            query = ['Compare', ['left', ['Bundle', left_bundle]], ['right', ['Bundle', right_bundle]],
                ['axis', 'Resource_policy'], ['left_workload', [str(left)]], ['right_workload', [str(right)]],
                ['expected_left_digest', []], ['expected_right_digest', []],
                ['expected_left_workload_digest', []], ['expected_right_workload_digest', []]]
            snapshot = rpc('asic', ['Workloads', ['Load', ['query', query], ['refresh', 'true']]], wait=True)
            comparison = json.loads(field(field(field(snapshot, 'workloads')[0], 'selected')[0], 'json'))
            metrics = [m for m in comparison['metrics'] if m['metric_id'].startswith('workload/')]
            assert len(metrics) == 7 and all(m['comparison'] == 'comparable' and
                m['right_minus_left'] == 0 for m in metrics), metrics
            assert next(m for m in metrics if m['metric_id'] == 'workload/throughput')['right_minus_left_ratio'] == {'numerator': 0, 'denominator': 1}
            assert inspect(failed)['outcome']['performance'] == 'unavailable'
            result.update(public_comparison_seven_zero_deltas=True, readable_failed_result=True)
            # Launch actual fresh implementation RTL through FS2 HTTP, not through
            # a test-only producer path. Read the artifact through the native RPC.
            discovery = rpc('simulation', 'Discover')
            deadline = time.monotonic() + 20
            while not field(discovery, 'discovery_digest'):
                assert time.monotonic() < deadline
                time.sleep(.05)
                discovery = rpc('simulation')
            selection = [['suite', 'pt8-memory-workloads'], ['cases', ['flops256', 'exact256']],
                ['seed', '34097'], ['parameters', []], ['asic_inputs', []]]
            launched = rpc('simulation', ['Launch', ['submission_key', 'native-' + uuid.uuid4().hex],
                ['discovery_digest', field(discovery, 'discovery_digest')[0]], ['selection', selection]])
            attempt = field(field(launched, 'detail')[0], 'id')
            deadline = time.monotonic() + 120
            while True:
                observed = rpc('simulation', ['Observe', attempt])
                detail = field(observed, 'detail')[0]
                if field(detail, 'lifecycle') in ('Finished', 'Cancelled', 'Interrupted'):
                    break
                assert time.monotonic() < deadline
                time.sleep(.05)
            assert field(detail, 'outcome') == 'Passed', detail
            result.update(actual_fs2_attempt=attempt, fresh_native_fs2_both=True)
            for artifact in field(detail, 'artifacts'):
                if not field(artifact, 'id').endswith('-result-reference'):
                    continue
                page = rpc('simulation', ['Read_artifact_bytes', ['attempt_id', attempt],
                    ['artifact_id', field(artifact, 'id')], ['sha256', field(artifact, 'sha256')[0]],
                    ['offset', 0], ['limit', 16384]])
                reference = json.loads(bytes.fromhex(field(field(page, 'byte_page')[0], 'bytes_hex')))
                assert inspect(Path(reference['result']), reference['source_digest'])['outcome']['functional'] == 'pass'
            result['artifact_rpc_handoff'] = True
            # Real terminal attachment and production palette navigation, wide and
            # narrow, against this exact private daemon. No mocked renderer.
            terminal = Terminal(launch + ['client', '--session', str(session)], env, output)
            try:
                terminal.capture('ui-startup', ['private_pt8_workbench'])
                terminal.palette('Open Workloads workspace')
                def import_ui(path, outcome):
                    terminal.palette('Workloads: Import exact retained result.json')
                    terminal.key(str(path).encode())
                    terminal.key(b'\r')
                    terminal.capture('ui-import-' + outcome + '-' + path.parent.name,
                                     ['functional: ' + outcome])
                import_ui(left, 'pass')
                terminal.palette('Workloads: Capture A left result')
                left_screen = terminal.capture('ui-auto-capture-a', ['functional: pass'])
                assert 'CAPTURE A —' not in left_screen, 'unexpected manual bundle-entry form'
                import_ui(right, 'pass')
                terminal.palette('Workloads: Capture B right result')
                right_screen = terminal.capture('ui-auto-capture-b', ['functional: pass'])
                assert 'CAPTURE B —' not in right_screen, 'unexpected manual bundle-entry form'
                result['ui_bundle_auto_capture_no_manual_path'] = True
                terminal.palette('Workloads: Axis resource_policy')
                frames = []
                shown_metrics = set()
                required_metrics = {'cycles', 'defined_observations', 'operations', 'read_latency', 'reads', 'throughput', 'writes'}
                for n in range(18):
                    frame = terminal.capture('ui-comparison-%02d' % n)
                    frames.append(frame)
                    for line in frame.splitlines():
                        for key in required_metrics:
                            if 'workload/' + key + ':' in line and 'delta(B-A)=0' in line and 'comparable' in line:
                                shown_metrics.add(key)
                    if shown_metrics == required_metrics:
                        break
                    terminal.key(b']')
                assert shown_metrics == required_metrics, ('seven deltas not visible', shown_metrics)
                pair_state = field(rpc('asic'), 'workloads')[0]
                ui_pair = json.loads(field(field(pair_state, 'selected')[0], 'json'))
                assert ui_pair['axis'] == 'resource_policy'
                assert ui_pair['left']['target'] == left_bundle and ui_pair['right']['target'] == right_bundle
                assert ui_pair['left']['workload']['source_digest'] == left_view['source_digest']
                assert ui_pair['right']['workload']['source_digest'] == right_view['source_digest']
                pair_queries = [dict(dict(d)['query'][1:]) for d in field(pair_state, 'entries')
                    if dict(d)['query'][0] == 'Compare']
                assert any(q['left_workload'] == [str(left)] and q['right_workload'] == [str(right)] and
                    q['expected_left_workload_digest'] == [left_view['source_digest']] and
                    q['expected_right_workload_digest'] == [right_view['source_digest']] for q in pair_queries)
                write(output / 'ui-auto-capture-pair.json', {'queries': pair_queries, 'comparison': ui_pair})
                result['ui_retained_pair_compared'] = True
                terminal.key(b'\x1b')
                import_ui(failed, 'fail')
                result['ui_functional_failure_displayed'] = True
                # Get, resize, filtering and warm reopen must execute no tools.
                terminal.drain(1)
                def execs():
                    return [line for line in trace.read_text().splitlines() if 'execve(' in line]
                before_warm = execs()
                for _ in range(3):
                    rpc('asic')
                terminal.key(b'\x1b')
                terminal.key(b'/no-match\x1b')
                terminal.palette('Open Workloads workspace')
                terminal.resize(24, 80)
                terminal.capture('ui-warm-narrow', ['Workloads'])
                terminal.resize(46, 150)
                terminal.capture('ui-warm-wide', ['Workloads'])
                assert execs() == before_warm, 'warm navigation spawned a tool'
                result['warm_get_filter_reopen_resize_no_exec'] = True
                # The production UI, rather than HTTP, submits this fresh run.
                old_attempts = {field(a, 'id') for a in field(rpc('simulation'), 'attempts')}
                terminal.palette('Workloads: Launch fresh PT.8 workload')
                terminal.capture('ui-testing-catalog', ['pt8-memory-workloads'])
                terminal.palette('Simulation: Launch selected catalog subset')
                terminal.capture('ui-form-cases', ['CASES', 'flops256', 'exact256'])
                terminal.key(b'\x15exact256')
                terminal.key(b'\r')
                terminal.capture('ui-form-seed', ['SEED', '34097'])
                terminal.key(b'\r')
                terminal.capture('ui-form-confirm', ['CONFIRM', 'launch'])
                terminal.key(b'\r')
                deadline = time.monotonic() + 120
                while True:
                    terminal.drain(.2)
                    history = rpc('simulation')
                    added = [a for a in field(history, 'attempts') if field(a, 'id') not in old_attempts]
                    if added:
                        ui_attempt = field(added[0], 'id')
                        ui_detail = field(rpc('simulation', ['Observe', ui_attempt]), 'detail')[0]
                        if field(ui_detail, 'lifecycle') in ('Finished', 'Cancelled', 'Interrupted'):
                            break
                    assert time.monotonic() < deadline, 'UI launch did not finish'
                assert field(ui_detail, 'outcome') == 'Passed', ui_detail
                result.update(actual_ui_fs2_attempt=ui_attempt, actual_ui_case='exact256', ui_form_launch_passed=True)
                write(output / 'ui-completed-attempt.json', ui_detail)
                assert field(field(ui_detail, 'captured'), 'selection') == [
                    ['suite', 'pt8-memory-workloads'], ['cases', ['exact256']], ['seed', '34097'],
                    ['parameters', []], ['asic_inputs', []]]
                terminal.capture('ui-fresh-finished', ['exact256', 'Passed'])
                terminal.palette('Simulation: Select case exact256')
                terminal.palette('Inspect workload result (selected Testing case)')
                terminal.capture('ui-artifact-workloads-handoff', ['Workloads', 'functional: pass'])
                ui_artifact = next(a for a in field(ui_detail, 'artifacts') if field(a, 'id').endswith('-exact256-result-reference'))
                fetched = rpc('simulation', ['Read_artifact_bytes', ['attempt_id', ui_attempt],
                    ['artifact_id', field(ui_artifact, 'id')], ['sha256', field(ui_artifact, 'sha256')[0]],
                    ['offset', 0], ['limit', 16384]])
                ui_reference = json.loads(bytes.fromhex(field(field(fetched, 'byte_page')[0], 'bytes_hex')))
                selected_workloads = field(rpc('asic'), 'workloads')[0]
                descriptors = [dict(d) for d in field(selected_workloads, 'entries')]
                matching = [d for d in descriptors if d['query'][0] == 'Inspect' and
                    dict(d['query'][1:]) == {'result': ui_reference['result'],
                        'expected_digest': [ui_reference['source_digest']]}]
                assert matching and matching[0]['freshness'] == 'Validated', descriptors
                selected = json.loads(field(field(selected_workloads, 'selected')[0], 'json'))
                assert selected['source_digest'] == ui_reference['source_digest']
                new_result = Path(ui_reference['result'])
                new_simulation = json.loads((new_result.parent / 'simulation.json').read_text())
                old_simulations = [json.loads((p.parent / 'simulation.json').read_text())['attempt_id'] for p in (left, right)]
                assert new_simulation['attempt_id'] not in old_simulations
                assert new_simulation['attempt_id'] not in (ui_attempt, attempt)
                assert field(field(ui_detail, 'captured'), 'provider_executable') == manifest['provider_command'][0]
                result['ui_result_reference'] = ui_reference
                result['new_simulation_attempt_id'] = new_simulation['attempt_id']
                result['retained_simulation_attempt_ids'] = old_simulations
                result['provider_generation_fs2_and_simulation_identities_distinct'] = True
                write(output / 'ui-handoff-cache.json', {'descriptors': descriptors,
                    'selected': selected, 'reference': ui_reference})
                # Explicitly recapture fresh Exact as B and compare it against
                # retained sim04 Flops A; the old pair must not silently retarget.
                terminal.palette('Workloads: Capture B right result')
                terminal.palette('Workloads: Axis resource_policy')
                terminal.capture('ui-fresh-vs-retained-comparison',
                    ['workload/cycles:', 'workload/writes:', 'delta(B-A)=0', 'Validated'])
                mixed_state = field(rpc('asic'), 'workloads')[0]
                mixed = json.loads(field(field(mixed_state, 'selected')[0], 'json'))
                mixed_metrics = [m for m in mixed['metrics'] if m['metric_id'].startswith('workload/')]
                assert len(mixed_metrics) == 7 and all(m['comparison'] == 'comparable' and
                    m['right_minus_left'] == 0 for m in mixed_metrics)
                assert mixed['left']['workload']['source_digest'] == left_view['source_digest']
                assert mixed['right']['workload']['source_digest'] == ui_reference['source_digest']
                assert mixed['right']['workload']['binding']['simulation_attempt_id'] == new_simulation['attempt_id']
                write(output / 'ui-fresh-vs-retained-comparison.json', mixed)
                result['ui_fresh_exact_vs_original_flops_seven_zero_deltas'] = True
                result.update(actual_ui_fs2_attempt=ui_attempt, actual_ui_case='exact256',
                    ui_form_launch_passed=True, ui_artifact_handoff_expected_digest=True,
                    ui_retained_pair_compared=True, ui_functional_failure_displayed=True)
            finally:
                terminal.close()
            result.update(pass_=True, actual_fs2_attempt=attempt, public_comparison_seven_zero_deltas=True,
                fresh_native_fs2_both=True, artifact_rpc_handoff=True, private_pty_wide_narrow=True)
            result['pass'] = result.pop('pass_')
        finally:
            if http is not None:
                write(output / 'http.json', http.history)
            if owned_pid is not None:
                os.kill(owned_pid, signal.SIGTERM)
            else:
                daemon.terminate()
            daemon.wait(timeout=15)
            after = protected_state()
            write(output / 'root-protected-after.json', after)
            result['root_configs_and_selected_providers_unchanged'] = after == protected_before
            result['installed_capture_unchanged'] = installed_before == {
                name: sha(session / 'provider' / name) for name in manifest['captured_files']}
            full_install_after = installed_state(session, manifest)
            write(output / 'installed-after.json', full_install_after)
            result['full_installed_generation_and_private_configs_unchanged'] = full_install_before == full_install_after
            retained_after = retained_state([left, right, failed])
            write(output / 'retained-after.json', retained_after)
            result['original_retained_evidence_and_bundles_unchanged'] = retained_before == retained_after
            result['wb_binaries_unchanged_during_run'] = result['wb_binaries'] == {
                str(p): sha(p) for p in (build / 'daemon/main.exe', build / 'terminal/main.exe')}
            if not all(result.get(k, False) for k in ('root_configs_and_selected_providers_unchanged',
                'installed_capture_unchanged', 'full_installed_generation_and_private_configs_unchanged',
                'original_retained_evidence_and_bundles_unchanged', 'wb_binaries_unchanged_during_run')):
                result['pass'] = False
            write(output / 'assertions.json', result)
            assert result['pass'], 'native acceptance or preservation gate failed; see ' + str(output)
    print(str(output))


if __name__ == '__main__':
    main()
