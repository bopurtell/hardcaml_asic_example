#!/usr/bin/env python3
"""Real production Testing launch -> waveform parse/cursor via owned private PTY."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
from pt8_workbench_native_acceptance import Terminal, Client, field, parse, sexp
from pt8_waveform_acceptance import ROOT, protected
from pt8_acceptance import write, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--preservation', type=Path, required=True)
    args = parser.parse_args()
    session = args.session.resolve(strict=True)
    manifest = json.loads((session / 'manifest.json').read_text())
    output = session / ('waveform-native-' + uuid.uuid4().hex)
    output.mkdir()
    launch = [sys.executable, '-B', str(ROOT / 'scripts/pt8_workbench_launch.py')]
    common = ['--session', str(session), '--runtime-root', str(output)]
    env = dict(os.environ, TERM='xterm-256color', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1')
    binaries = {str(Path(manifest['wb_build_root']) / 'default' / p):
                sha(Path(manifest['wb_build_root']) / 'default' / p)
                for p in ('daemon/main.exe', 'terminal/main.exe')}
    write(output / 'invocation.json', {'argv': sys.argv, 'binaries': binaries, 'eda_allocation': 0})
    terminal, http = None, None
    receipt = {'pass': False}
    with (output / 'daemon.stdout').open('xb') as out, (output / 'daemon.stderr').open('xb') as err:
        daemon = subprocess.Popen(launch + ['daemon'] + common, stdout=out, stderr=err, env=env)
        try:
            deadline = time.monotonic() + 20
            while not (output / 'discovery/daemon.sexp').exists():
                assert daemon.poll() is None and time.monotonic() < deadline
                time.sleep(.05)
            metadata = dict(parse((output / 'discovery/daemon.sexp').read_text()))
            assert int(metadata['pid']) == daemon.pid
            http = Client(metadata['endpoint'], manifest['project_root'])
            def rpc(op='Get'):
                return http.rpc(op if isinstance(op, str) else sexp(op), domain='simulation', wait=False)
            terminal = Terminal(launch + ['client'] + common, env, output)
            terminal.capture('startup', ['Connection: connected', 'Overview', 'Testing'])
            terminal.palette('Workloads: Launch fresh PT.8 workload')
            terminal.capture('testing-catalog', ['pt8-memory-workloads'])
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
                snapshot = rpc()
                attempts = field(snapshot, 'attempts')
                if attempts:
                    attempt = field(attempts[0], 'id')
                    detail = field(rpc(['Observe', attempt]), 'detail')[0]
                    if field(detail, 'lifecycle') in ('Finished', 'Cancelled', 'Interrupted'):
                        break
                assert time.monotonic() < deadline, 'fresh UI run timeout'
            write(output / 'ui-attempt.json', detail)
            assert field(detail, 'outcome') == 'Passed'
            artifacts = field(detail, 'artifacts')
            wave = next(a for a in artifacts if field(a, 'id').endswith('-exact256-waveform'))
            assert field(wave, 'attempt_id') == attempt and field(wave, 'case_id') == ['exact256']
            assert field(wave, 'media_type') == 'text/vcd' and field(wave, 'availability') == 'Available'
            data = b''
            size = int(field(wave, 'size')[0])
            while len(data) < size:
                page = rpc(['Read_artifact_bytes', ['attempt_id', attempt], ['artifact_id', field(wave, 'id')],
                            ['sha256', field(wave, 'sha256')[0]], ['offset', len(data)], ['limit', 16384]])
                chunk = bytes.fromhex(field(field(page, 'byte_page')[0], 'bytes_hex'))
                assert chunk
                data += chunk
            (output / 'transport.vcd').write_bytes(data)
            assert sha(output / 'transport.vcd') == field(wave, 'sha256')[0]
            terminal.capture('fresh-finished', ['exact256', 'Passed'])
            terminal.palette('Simulation: Select case exact256')
            terminal.palette('Simulation: Open embedded waveform ' + field(wave, 'label'))
            screen = terminal.capture('waveform-parsed', ['Waveform', 'Cursor 0 ticks', 'tb.clk',
                '6 matching', '6 enabled', 'rst_n', 'tb.q[15:0] contains X/Z'])
            assert 'Unsupported VCD' not in screen and 'result-reference' not in screen
            # First initialized read response; earlier X remains visible/truthful.
            terminal.key(b':2595000\r')
            screen = terminal.capture('waveform-cursor-2595000', ['Cursor 2595000 ticks', 'tb.clk'])
            assert 'Graph unavailable' not in screen
            terminal.key(b'l')
            terminal.capture('waveform-cursor-2595001', ['Cursor 2595001 ticks'])
            terminal.palette('Waveform: Open dedicated Waveforms workspace')
            terminal.capture('dedicated-waveforms', ['Waveforms', 'Signals', 'Waves', 'VCD picker', 'Ready'])
            receipt.update(pass_=True, actual_ui_attempt=attempt, actual_ui_case='exact256',
                fresh_testing_form_run=True, hash_bound_transport=True, native_parse_six_signals=True,
                actual_cursor_ticks=[0, 2595000, 2595001], unknown_initial_response_preserved=True,
                defined_read_wave_rendered=True, dedicated_workspace=True,
                waveform_sha256=field(wave, 'sha256')[0], waveform_bytes=len(data))
            receipt['pass'] = receipt.pop('pass_')
        finally:
            if terminal is not None:
                terminal.close()
            if http is not None:
                write(output / 'http.json', http.history)
            daemon.terminate()
            daemon.wait(timeout=10)
            after = protected()
            write(output / 'preservation-after.json', after)
            receipt['protected_files_unchanged'] = after == json.loads(args.preservation.read_text())
            receipt['immutable_provider_unchanged'] = all(sha(session / 'provider' / p) == h
                for p, h in manifest['captured_files'].items())
            receipt['eda_allocation'] = 0
            write(output / 'assertions.json', receipt)
    assert receipt['pass'] and receipt['protected_files_unchanged'] and receipt['immutable_provider_unchanged']
    print(output)


if __name__ == '__main__':
    main()
