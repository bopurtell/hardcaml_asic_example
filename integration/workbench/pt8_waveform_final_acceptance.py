#!/usr/bin/env python3
"""Final corrected capture: one direct real pair, source-only Plan, native UI Exact."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
from workbench_paths import ROOT
from pt8_acceptance import sha, write
from pt8_waveform_correction_check import preservation
from pt8_waveform_acceptance import ROOT
from pt8_workbench_native_acceptance import Terminal, Client, field, parse, sexp
import pt8_workloads as producer

WB = ROOT.parent / 'hardcaml_workbench'
FINAL_CLIENT = '2c301d20dd744e46942e4a4604a7bde475c67f126a8e86c157c9518fe05da698'


def command(output, label, argv, cwd, env=None):
    d = output / label
    d.mkdir()
    with (d / 'stdout').open('xb') as out, (d / 'stderr').open('xb') as err:
        code = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, stdout=out, stderr=err, timeout=240).returncode
    write(d / 'command.json', {'argv': list(map(str, argv)), 'cwd': str(cwd), 'exit_code': code,
                               'eda_allocation': 0, 'max_parallel_processes': 1})
    assert code == 0, str(d)
    return (d / 'stdout').read_text()


def verify_result(output, case, reference, copied=None):
    policy = {'flops256': 'flops', 'exact256': 'exact'}[case]
    assert set(reference) == {'contract', 'schema_version', 'result', 'source_digest'}
    result = Path(reference['result'])
    directory = result.parent
    r = json.loads(result.read_text())
    assert r['counters'] == dict(cycles=1307, reads=525, writes=262, operations=787,
        defined_observations=2083, read_latency=1)
    assert json.loads((directory / 'oracle-check.json').read_text()) == {'mismatches': [], 'pass': True}
    inspection = json.loads((directory.parent / 'inspection.json').read_text())
    assert inspection['source_digest'] == reference['source_digest']
    assert inspection['outcome']['functional'] == 'pass'
    w = json.loads((directory.parent / 'workload.json').read_text())
    assert w['operations'] == producer.workload()['operations']
    trace = producer.parse_trace(directory / 'execute/stdout.log', w['operations'])
    assert trace == json.loads((directory / 'trace.json').read_text()) == json.loads(
        (ROOT / 'acceptance/pt8-workloads/simulation-04' / policy / 'trace.json').read_text())
    wave = directory / 'waveform.vcd'
    desc = producer.validate_waveform(wave, 1307)
    assert desc == json.loads(wave.with_suffix('.json').read_text())
    if copied:
        assert copied.read_bytes() == wave.read_bytes()
    times = [n * 10000 + phase for n in range(1307) for phase in (4000, 9000)]
    probe = WB / '_build_pt8_workbench/default/terminal/waveform_probe.exe'
    parsed = dict(parse(command(output, case + '-same-execution',
        [probe, wave, '2595000', '2595107', *map(str, times)], output)))
    assert parsed['status'] == 'ok'
    signals = {dict(s)['name'].split('[')[0]: dict(s) for s in parsed['signals']}
    widths = dict(clk=1, ena=1, rst_n=1, ui_in=8, uio_in=8, q=16)
    assert {k: int(s['width']) for k, s in signals.items()} == {'tb.' + k: v for k, v in widths.items()}
    values = {name: {int(t): v[0] if v else None for t, v in s['values']} for name, s in signals.items()}
    rows = [line.split() for line in (directory / 'execute/stdout.log').read_text().splitlines()
            if line.startswith('TRACE ')]
    assert len(rows) == 1307
    samples = unknowns = 0
    for n, (_, cycle, prior, response) in enumerate(rows):
        assert int(cycle) == n
        op = w['operations'][n]
        for phase, word in ((4000, prior), (9000, response)):
            tick = n * 10000 + phase
            wanted = dict(clk=int(phase == 9000), ena=int(op['enable']), rst_n=int(not op['write']),
                          ui_in=op['address'], uio_in=op['data'] & 255)
            for name, value in wanted.items():
                assert values['tb.' + name][tick] == format(value, f'0{widths[name]}b'), (case, n, phase, name)
                samples += 1
            bits = ''.join(c * 4 if c in 'xz' else format(int(c, 16), '04b') for c in word.lower()).zfill(16)
            assert values['tb.q'][tick] == bits, (case, n, phase, word)
            samples += 1
            unknowns += int('x' in bits or 'z' in bits)
    assert samples == 15684 and unknowns == 519
    execution = json.loads((directory / 'execute/command.json').read_text())
    assert execution['cwd'] == str(directory) and execution['exit_code'] == 0
    assert Path(execution['argv'][1]).parent == directory
    if policy == 'exact':
        model_root = ROOT / '_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog'
        for name in ('RM_IHPSG13_1P_256x16_c2_bm_bist.v', 'RM_IHPSG13_1P_core_behavioral_bm_bist.v'):
            assert sha(directory / name) == sha(model_root / name)
    return dict(result=str(result), source_digest=reference['source_digest'], waveform=desc,
                same_execution_signal_samples=samples, unknown_q_samples=unknowns, counters=r['counters'])


def direct(session, manifest, output):
    project = Path(manifest['project_root'])
    assert all(sha(project / name) == digest for name, digest in manifest['source_snapshot'].items())
    plan = json.loads(command(output, 'standard-source-only-plan',
        ['strace', '-f', '-e', 'trace=process', '-o', output / 'plan.process.strace', '--',
         session / 'provider/project.exe', 'flow', 'plan', '--flow', 'standard', '--profile', 'balanced',
         '--endpoint', 'synthesis', '--source-root', project, '--json'], project))
    assert plan['plan_identity']
    write(output / 'standard-plan.json', plan)
    assert all(sha(project / name) == digest for name, digest in manifest['source_snapshot'].items())
    fs2 = output / 'fs2'
    fs2.mkdir()
    (fs2 / 'artifacts').mkdir()
    attempt = 'final-direct-' + uuid.uuid4().hex
    (fs2 / 'request.sexp').write_text(sexp([('protocol_version', 1), ('attempt_id', attempt), ('selection', [
        ('suite', 'pt8-memory-workloads'), ('cases', ['flops256', 'exact256']), ('seed', '34097'),
        ('parameters', []), ('asic_inputs', [])])]) + '\n')
    command(output, 'actual-direct-pair', ['strace', '-f', '-e', 'trace=process', '-o',
        output / 'direct.process.strace', '--', *manifest['provider_command'], 'run', '--protocol-version', '1',
        '--request', fs2 / 'request.sexp', '--events', fs2 / 'events.sexp', '--artifact-dir', fs2 / 'artifacts'], output)
    events = [dict(parse(line)) for line in (fs2 / 'events.sexp').read_text().splitlines()]
    assert [int(e['sequence']) for e in events] == list(range(len(events)))
    assert events[-1]['payload'] == ['Finished', 'Passed']
    results = {}
    for case in ('flops256', 'exact256'):
        reference = json.loads((fs2 / 'artifacts' / (case + '-result-reference.json')).read_text())
        assert Path(reference['result']).is_relative_to(project / '.dev/asic-pt8-workbench/workloads')
        results[case] = verify_result(output, case, reference, fs2 / 'artifacts' / (case + '-waveform.vcd'))
    for log in ('plan.process.strace', 'direct.process.strace'):
        trace = (output / log).read_text()
        assert not any(token in trace for token in ('"yosys"', '"openroad"', '"librelane"', '"dune"'))
    return dict(pass_=True, actual_direct_attempt=attempt, actual_cases=['flops256', 'exact256'],
                results=results, standard_source_only_plan_identity=plan['plan_identity'],
                private_source_snapshot_unchanged=True)


def native(session, manifest, output, prior):
    assert json.loads((prior / 'assertions.json').read_text())['pass']
    build = Path(manifest['wb_build_root']) / 'default'
    assert sha(build / 'terminal/main.exe') == FINAL_CLIENT
    spec = importlib.util.spec_from_file_location('final_proxy', WB / 'scripts/test-embedded-waveform.py')
    embedded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(embedded)
    launch = [sys.executable, '-B', str(ROOT / 'integration/workbench/pt8_workbench_launch.py')]
    common = ['--session', str(session), '--runtime-root', str(output)]
    env = dict(os.environ, TERM='xterm-256color', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
               XDG_STATE_HOME=str(output / 'client-state'))
    terminal = proxy = http = None
    with (output / 'daemon.stdout').open('xb') as out, (output / 'daemon.stderr').open('xb') as err:
        daemon = subprocess.Popen(['strace', '-f', '-e', 'trace=process', '-o', str(output / 'native.process.strace'),
            '--', *launch, 'daemon', *common], stdout=out, stderr=err, env=env)
        owned_pid = None
        try:
            deadline = time.monotonic() + 20
            while not (output / 'discovery/daemon.sexp').exists():
                assert daemon.poll() is None and time.monotonic() < deadline
                time.sleep(.05)
            metadata = dict(parse((output / 'discovery/daemon.sexp').read_text()))
            owned_pid = int(metadata['pid'])
            assert str(owned_pid) in Path(f'/proc/{daemon.pid}/task/{daemon.pid}/children').read_text().split()
            http = Client(metadata['endpoint'], manifest['project_root'])
            def rpc(op='Get'):
                return http.rpc(op if isinstance(op, str) else sexp(op), domain='simulation', wait=False)
            proxy = embedded.DelayedBytesProxy(metadata['endpoint'], output)
            terminal = Terminal([str(build / 'terminal/main.exe'), '--connect', proxy.url,
                                 '--project-root', manifest['project_root']], env, output)
            terminal.capture('startup', ['Connection: connected', 'Testing'])
            terminal.palette('Workloads: Launch fresh PT.8 workload')
            terminal.capture('catalog', ['pt8-memory-workloads'])
            terminal.palette('Simulation: Launch selected catalog subset')
            terminal.capture('form-cases', ['CASES', 'flops256', 'exact256'])
            terminal.key(b'\x15exact256\r')
            terminal.capture('form-seed', ['SEED', '34097'])
            terminal.key(b'\r')
            terminal.capture('form-confirm', ['CONFIRM', 'launch'])
            terminal.key(b'\r')
            deadline = time.monotonic() + 120
            while True:
                terminal.drain(.2)
                snap = rpc()
                attempts = field(snap, 'attempts')
                if attempts:
                    attempt = field(attempts[0], 'id')
                    detail = field(rpc(['Observe', attempt]), 'detail')[0]
                    if field(detail, 'lifecycle') in ('Finished', 'Cancelled', 'Interrupted'):
                        break
                assert time.monotonic() < deadline
            write(output / 'ui-attempt.json', detail)
            assert field(detail, 'outcome') == 'Passed'
            artifacts = field(detail, 'artifacts')
            wave = next(a for a in artifacts if field(a, 'id').endswith('-exact256-waveform'))
            reference_artifact = next(a for a in artifacts if field(a, 'id').endswith('-exact256-result-reference'))
            assert field(wave, 'attempt_id') == attempt and field(wave, 'case_id') == ['exact256']
            terminal.capture('finished', ['exact256', 'Passed'])
            terminal.palette('Simulation: Select case exact256')
            for _ in range(18):
                screen = terminal.drain(.1)
                if 'simulation artifacts' in screen.splitlines()[-1].lower().replace('-', ' '):
                    break
                terminal.key(b'\t')
            else:
                terminal.save('focus-failed', screen)
                raise AssertionError('Artifacts focus not reached')
            terminal.key(b'k' * 8)
            screen = terminal.capture('json-cursor', ['retained workload result'])
            assert any('>' in line and 'retained workload result' in line for line in screen.splitlines()), screen
            before = len(proxy.records)
            terminal.key(b'w')
            screen = terminal.capture('mixed-X-ready-at-zero', ['Waveform', 'Cursor 0 ticks', '6 matching',
                '6 enabled', 'tb.clk', 'X/Z in window; no graph'])
            assert 'Graph unavailable' not in screen and 'result-reference' not in screen
            assert '┌Waves' in screen and 'xxxx' in screen.lower()
            assert any(r['request']['artifact_id'] == field(wave, 'id') for r in proxy.records[before:])
            assert all(r['request']['artifact_id'] == field(wave, 'id') for r in proxy.records[before:])
            terminal.key(b':2595000\r')
            screen = terminal.capture('read-response-2595000', ['Cursor 2595000 ticks', '13C6'])
            assert 'Graph unavailable' not in screen and 'X/Z in window' not in screen
            terminal.key(b'l')
            terminal.capture('cursor-2595001', ['Cursor 2595001 ticks'])
            terminal.palette('Waveform: Open dedicated Waveforms workspace')
            screen = terminal.capture('dedicated-ready', ['Waveforms', 'Signals', 'Waves', 'VCD picker',
                'Ready', 'Pinned: exact256 implementation', 'X/Z in window; no graph', 'Pinned attempt output'])
            assert 'Graph unavailable' not in screen and 'result-reference' not in screen
            assert all(r['request']['artifact_id'] == field(wave, 'id') for r in proxy.records)
            # Native transport and the UI's independent Workloads reference remain
            # byte/hash-bound to this exact fresh attempt.
            def fetch(a):
                data = b''
                while len(data) < int(field(a, 'size')[0]):
                    page = rpc(['Read_artifact_bytes', ['attempt_id', attempt], ['artifact_id', field(a, 'id')],
                        ['sha256', field(a, 'sha256')[0]], ['offset', len(data)], ['limit', 16384]])
                    chunk = bytes.fromhex(field(field(page, 'byte_page')[0], 'bytes_hex'))
                    assert chunk
                    data += chunk
                return data
            transported = output / 'transport.vcd'
            transported.write_bytes(fetch(wave))
            assert sha(transported) == field(wave, 'sha256')[0]
            reference = json.loads(fetch(reference_artifact))
            verified = verify_result(output, 'exact256', reference, transported)
            job = field(detail, 'job')
            # Sidecar captures exact project/artifact/daemon/job provenance.
            pins = list((output / 'client-state').rglob('waveforms-*.sexp'))
            pin_text = '\n'.join(p.read_text() for p in pins)
            assert attempt in pin_text and job in pin_text and field(wave, 'id') in pin_text
            assert field(reference_artifact, 'id') not in pin_text
            return dict(pass_=True, direct_receipt=str(prior / 'assertions.json'), actual_ui_attempt=attempt,
                actual_ui_case='exact256', waveform_artifact=field(wave, 'id'),
                waveform_sha256=field(wave, 'sha256')[0], waveform_bytes=transported.stat().st_size,
                json_cursor_same_case_VCD=True, six_signals_ready_at_zero=True,
                known_lanes_rendered_unknown_q_lane=True, no_whole_graph_failure=True,
                actual_cursor_ticks=[0, 2595000, 2595001], response_hex='13C6',
                dedicated_no_JSON_pin=True, pinned_log_scope='attempt-wide', pinned_job=job,
                same_execution_verification=verified)
        finally:
            if terminal:
                terminal.close()
            if proxy:
                proxy.close()
            if http:
                write(output / 'http.json', http.history)
            if owned_pid:
                os.kill(owned_pid, 15)
            daemon.wait(timeout=10)


def audit_native(session, manifest, output, evidence, prior):
    """Complete the receipt from retained actual UI evidence; no new execution."""
    assert json.loads((prior / 'assertions.json').read_text())['pass']
    invocation = json.loads((evidence / 'invocation.json').read_text())
    assert invocation['binaries'][str(Path(manifest['wb_build_root']) / 'default/terminal/main.exe')] == FINAL_CLIENT
    detail = json.loads((evidence / 'ui-attempt.json').read_text())
    attempt, job = field(detail, 'id'), field(detail, 'job')
    assert field(detail, 'outcome') == 'Passed'
    wave = next(a for a in field(detail, 'artifacts') if field(a, 'id').endswith('-exact256-waveform'))
    reference_artifact = next(a for a in field(detail, 'artifacts') if field(a, 'id').endswith('-exact256-result-reference'))
    assert field(wave, 'case_id') == ['exact256'] and field(wave, 'attempt_id') == attempt
    checks = {
        'form-cases': ['CASES', 'flops256', 'exact256'],
        'form-seed': ['SEED', '34097'], 'form-confirm': ['CONFIRM', 'launch'],
        'mixed-X-ready-at-zero': ['Cursor 0 ticks', '6 matching', '6 enabled', 'tb.clk', 'X/Z in window; no graph', '┌Waves'],
        'read-response-2595000': ['Cursor 2595000 ticks', '13C6'],
        'cursor-2595001': ['Cursor 2595001 ticks'],
        'dedicated-ready': ['Ready', 'Signals', 'Waves', 'Pinned: exact256 implementation',
                            'Pinned attempt output', 'X/Z in window; no graph'],
    }
    for name, wanted in checks.items():
        screen = (evidence / (name + '.txt')).read_text()
        assert all(s in screen for s in wanted), name
        if name in ('mixed-X-ready-at-zero', 'read-response-2595000', 'dedicated-ready'):
            assert 'Graph unavailable' not in screen and 'result-reference' not in screen
    assert any('>' in line and 'retained workload result' in line
               for line in (evidence / 'json-cursor.txt').read_text().splitlines())
    requests = json.loads((evidence / 'delayed-byte-proxy.json').read_text())['byte_requests']
    assert requests and all(r['request']['artifact_id'] == field(wave, 'id')
        and r['request']['attempt_id'] == attempt and r['request']['sha256'] == field(wave, 'sha256')[0]
        and r['status'] == 200 for r in requests)
    pins = list((evidence / 'client-state').rglob('waveforms-*.sexp'))
    assert len(pins) == 1
    saved = dict(parse(pins[0].read_text()))
    pin = dict(dict(saved['pins'][0])['pin'])
    assert dict(pin['artifact']) == dict(wave)
    log = pin['log']
    assert log[0] == 'Job' and dict(log[1:])['job'] == job
    assert field(reference_artifact, 'id') not in pins[0].read_text()
    probe_command = json.loads((evidence / 'exact256-same-execution/command.json').read_text())
    assert probe_command['exit_code'] == 0
    directory = Path(probe_command['argv'][1]).parent
    reference = json.loads((directory.parent / 'result-reference.json').read_text())
    transported = evidence / 'transport.vcd'
    assert sha(transported) == field(wave, 'sha256')[0]
    verified = verify_result(output, 'exact256', reference, transported)
    # The actual HTTP-fetched JSON bytes must be the same authoritative reference.
    history = json.loads((evidence / 'http.json').read_text())
    references = []
    for item in history:
        response = parse(item['response'])
        if response[0] == 'Ok':
            page = dict(response[1]).get('byte_page', [])
            if page and field(page[0], 'artifact_id') == field(reference_artifact, 'id'):
                references.append(json.loads(bytes.fromhex(field(page[0], 'bytes_hex'))))
    assert references == [reference]
    trace = (evidence / 'native.process.strace').read_text()
    assert not any(token in trace for token in ('"yosys"', '"openroad"', '"librelane"'))
    dune_probes = [line for line in trace.splitlines() if 'execve(' in line and '/dune",' in line]
    assert all('"--version"' in line or '"describe", "workspace"' in line for line in dune_probes)
    assert any('/.opam/5.2.0+ox/bin/dune' in line and '"describe"' in line and '"-j2"' in line
               for line in dune_probes)
    write(output / 'retained-ui-evidence-hashes.json', {str(p.relative_to(evidence)): sha(p)
        for p in evidence.rglob('*') if p.is_file() and p.suffix in ('.txt', '.ansi', '.json', '.vcd', '.sexp')})
    return dict(pass_=True, actual_ui_evidence=str(evidence), direct_receipt=str(prior / 'assertions.json'),
        actual_ui_attempt=attempt, actual_ui_case='exact256', waveform_artifact=field(wave, 'id'),
        waveform_sha256=field(wave, 'sha256')[0], waveform_bytes=transported.stat().st_size,
        json_cursor_same_case_VCD=True, six_signals_ready_at_zero=True, known_lanes_rendered_unknown_q_lane=True,
        no_whole_graph_failure=True, actual_cursor_ticks=[0, 2595000, 2595001], response_hex='13C6',
        dedicated_no_JSON_pin=True, pinned_log_scope='attempt-wide', pinned_job=job,
        pinned_daemon_instance=dict(log[1:])['instance_id'], same_execution_verification=verified,
        harness_sidecar_glob_corrected=True, original_failed_receipt_preserved=True,
        automatic_dune_metadata_only=dune_probes,
        real_simulations_started_by_audit=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=['direct', 'native', 'audit-native'])
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--direct-receipt', type=Path)
    p.add_argument('--native-evidence', type=Path)
    args = p.parse_args()
    session = args.session.resolve(strict=True)
    manifest = json.loads((session / 'manifest.json').read_text())
    output = session / ('final-' + args.phase + '-' + uuid.uuid4().hex)
    output.mkdir()
    print(output, flush=True)
    before = preservation()
    write(output / 'preservation-before.json', before)
    sources = {str(ROOT / name): sha(ROOT / name) for name in (
        'integration/workbench/pt8_waveform_final_acceptance.py',
        'tooling_acceptance/workloads/controls/pt8_workloads.py',
        'integration/workbench/pt8_workbench_provider.py', 'integration/workbench/pt8_workbench_runner.py',
        'scripts/test_pt8_waveforms.py')}
    binaries = {str(Path(manifest['wb_build_root']) / 'default' / x):
                sha(Path(manifest['wb_build_root']) / 'default' / x)
                for x in ('terminal/main.exe', 'daemon/main.exe', 'terminal/waveform_probe.exe')}
    assert binaries[str(Path(manifest['wb_build_root']) / 'default/terminal/main.exe')] == FINAL_CLIENT
    assert all(sha(session / 'provider' / name) == digest for name, digest in manifest['captured_files'].items())
    write(output / 'invocation.json', {'argv': sys.argv, 'sources': sources, 'binaries': binaries,
        'generation': manifest['generation'], 'captured_files': manifest['captured_files'], 'eda_allocation': 0})
    result = {'pass': False}
    try:
        if args.phase == 'direct':
            result = direct(session, manifest, output)
        elif args.phase == 'native':
            result = native(session, manifest, output, args.direct_receipt.resolve(strict=True))
        else:
            result = audit_native(session, manifest, output, args.native_evidence.resolve(strict=True),
                                  args.direct_receipt.resolve(strict=True))
        result['pass'] = result.pop('pass_')
    finally:
        after = preservation()
        write(output / 'preservation-after.json', after)
        result['all_protected_files_unchanged'] = before == after
        result['immutable_provider_unchanged'] = all(sha(session / 'provider' / name) == digest
            for name, digest in manifest['captured_files'].items())
        result['private_source_snapshot_unchanged'] = all(sha(Path(manifest['project_root']) / name) == digest
            for name, digest in manifest['source_snapshot'].items())
        result['final_client_sha256'] = FINAL_CLIENT
        result['eda_allocation'] = 0
        write(output / 'assertions.json', result)
    assert result['pass'] and result['all_protected_files_unchanged'] and result['immutable_provider_unchanged']
    assert result['private_source_snapshot_unchanged']


if __name__ == '__main__':
    main()
