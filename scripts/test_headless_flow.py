"""Real installed-library project + recorder/native provider, no EDA or builds."""
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import unittest

CLIENT = Path(__file__).with_name('headless_flow.py').absolute()
# Reuse only disposable source/Git setup, never its provider build machinery.
import test_project_routing as routing


RECORDER = r'''
import json, os, sys, time
from pathlib import Path
a = sys.argv[1:]
root = Path(os.environ['RECORDER_ROOT'])
def emit(v): print(json.dumps(v), flush=True)
def obs(**kw): return dict(contract='hardcaml-asic.stage-observation', schema_version=2, stream_id='stream', **kw)
if '--version' in a:
    emit(dict(cli_contract=dict(version=4, capabilities=dict(namedflow1=json.loads(os.environ.get('CAP', 'true'))))))
elif a[0] == 'stages':
    (root/'launched').write_text(json.dumps(a))
    (root/'pid').write_text(str(os.getpid()))
    bundle = json.loads((Path(a[1])/'manifest.json').read_text())['identity']
    identity = a[a.index('--expected-plan-identity')+1]
    (root/'methodology').write_text(json.dumps(dict(contract='hardcaml-asic.historical-methodology', schema_version=1,
        state='recorded', plan_identity=identity, bundle_identity=bundle, reference=dict(attempt_id='stream'))))
    emit(dict(contract='hardcaml-asic.stage-observation', schema_version=1,
              event='observation_allocated', attempt=str(root/'explicit attempt'), stream_id='stream'))
    if os.environ.get('BAD_LINE'): print('{broken', flush=True); time.sleep(60)
    deadline = time.monotonic()+10
    while not (root/'read').exists():
        if time.monotonic()>deadline: sys.exit(9)
        time.sleep(.02)
    time.sleep(60 if os.environ.get('HOLD') else .2)
    (root/'done').write_text('done')
    identity = a[a.index('--expected-plan-identity')+1]
    emit(dict(attempt_id='stream', status='completed', exit_code=0, occurrences=[],
              plan=dict(schema_version=3, stages=['synthesis']),
              methodology=dict(contract='hardcaml-asic.methodology-execution-reference', schema_version=1,
                               attempt_id='stream', plan_identity=identity, expected_plan_identity=identity,
                               snapshot_path=str(root/'explicit snapshot.json'))))
    emit(dict(contract='hardcaml-asic.stage-observation', schema_version=1,
              event='observation_terminal', execution_file=None if os.environ.get('NO_REF') else str(root/'explicit execution.json')))
elif a[:2] == ['observation', 'read-updates']:
    after = int(a[a.index('--after')+1])
    assert a[a.index('--stream-id')+1] == 'stream'
    with (root/'queries').open('a') as f: f.write(str(after)+'\n')
    (root/'read').write_text('incremental')
    done = (root/'done').exists()
    cursor = 2 if done else 1
    emit(obs(after=after, cursor=cursor, events=[obs(sequence=i, event='outcome' if i==2 else 'allocated') for i in range(after+1,cursor+1)]))
elif a[:2] == ['observation', 'inspect']:
    done = (root/'done').exists()
    failed = bool(os.environ.get('FAILED'))
    emit(obs(cursor=2 if done else 1, writer_active=not done,
             observation_status='final' if done else 'live',
              state=dict(outcome=dict(status='failed' if failed else 'completed', exit_code=2 if failed else 0) if done else None),
              methodology=json.loads((root/'methodology').read_text()),
              execution_file=str(root/'explicit execution.json') if done and not os.environ.get('NO_REF') else None,
             final_results=dict(acceptance='not_evaluated',physical_completion='not_recorded')))
elif a[0] == 'report':
    assert a[1] == str(root/'explicit execution.json')
    method = json.loads((root/'methodology').read_text())
    if os.environ.get('BAD_REPORT'): method['plan_identity'] = '0'*64
    emit(dict(contract='hardcaml-asic.report', schema_version=1,
              execution=dict(attempt_id='stream'),
              methodology=method, additive='allowed'))
else: sys.exit(8)
'''


class HeadlessTests(unittest.TestCase):
    setUp = routing.RoutingTests.setUp

    def setup_client(self):
        self.provider = self.providers/'recorder with spaces'
        self.provider.write_text('#!'+sys.executable+'\n'+RECORDER)
        self.provider.chmod(0o755)
        self.env['RECORDER_ROOT'] = str(self.base)
        self.receipt = self.base/'client-cache.json'
        self.args = [sys.executable, str(CLIENT), '--project', str(routing.EXE),
                     '--provider', str(self.provider), '--source-root', str(self.root),
                     '--results-root', str(self.base/'results'), '--toolchain', str(self.base/'tools'),
                     '--endpoint', 'synthesis', '--receipt', str(self.receipt), '--timeout', '20']

    def invoke_client(self, expected=0, extra=()):
        result = subprocess.run(self.args+list(extra), env=self.env, capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertEqual(result.stdout, '')
        return json.loads(self.receipt.read_text()) if self.receipt.exists() else None

    def test_incremental_reconnect_and_exact_request(self):
        self.setup_client()
        receipt = self.invoke_client(extra=['--flow', 'standard', '--profile', 'synth_delay', '--set', 'SYNTH_ABC_BUFFERING=false'])
        self.assertTrue(receipt['execution_completed'])
        self.assertEqual(receipt['acceptance'], 'not_evaluated')
        self.assertTrue(any(u['cursor'] == 1 for u in receipt['updates']))
        self.assertFalse(receipt['inspection']['writer_active'])
        self.assertEqual(receipt['cursor'], 2)
        argv = json.loads((self.base/'launched').read_text())
        self.assertEqual(argv[argv.index('--expected-plan-identity')+1], receipt['plan_identity'])
        self.assertNotIn('--timeout', argv)
        self.assertIsNone(receipt['config']['stage_timeout'])
        receipt['config'].pop('stage_timeout')  # Old v1 receipts remain reader-only.
        launched = (self.base/'launched').stat().st_mtime_ns
        receipt['blocker'] = 'old provider did not deliver a reference'
        self.receipt.write_text(json.dumps(receipt))
        result = subprocess.run([sys.executable, str(CLIENT), '--receipt', str(self.receipt), '--reconnect'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.base/'queries').read_text().splitlines()[-1], '2')
        self.assertNotIn('blocker', json.loads(self.receipt.read_text()))
        self.assertIsNone(json.loads(self.receipt.read_text())['config']['stage_timeout'])
        self.assertEqual((self.base/'launched').stat().st_mtime_ns, launched)
        result = subprocess.run([sys.executable, str(CLIENT), '--receipt', str(self.receipt), '--reconnect'],
                                env=dict(self.env, BAD_REPORT='1'), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('report methodology identity mismatch', result.stderr)

    def test_stage_timeout_forwarding_and_pure_preview(self):
        self.setup_client()
        previews = []
        for budget in ('3600', '7200'):
            receipt = self.invoke_client(extra=['--preview-only', '--stage-timeout', budget])
            previews.append(receipt['plan'])
            self.assertEqual(receipt['config']['stage_timeout'], int(budget))
            self.assertEqual(receipt['config']['timeout'], 20)
            launch = receipt['launch_argv']
            self.assertEqual(launch[launch.index('--timeout')+1], budget)
            self.assertFalse((self.base/'launched').exists())
            self.receipt.unlink()
        self.assertEqual(*previews)
        receipt = self.invoke_client(extra=['--stage-timeout', '3600'])
        self.assertEqual(receipt['plan'], previews[0])
        argv = json.loads((self.base/'launched').read_text())
        self.assertEqual(argv[argv.index('--timeout')+1], '3600')
        self.assertNotIn('20', argv)

    def test_invalid_stage_timeout_before_queries(self):
        self.setup_client()
        for values in ([], ['0'], ['-1'], ['nan'], ['inf'], ['-inf'], ['1.5']):
            with self.subTest(values=values):
                self.invoke_client(expected=2, extra=['--stage-timeout', *values])
                self.assertFalse(self.receipt.exists())
                self.assertFalse((self.base/'launched').exists())

    def test_client_timeout_is_distinct_owned_budget(self):
        self.setup_client()
        self.env['HOLD'] = '1'
        self.args[self.args.index('--timeout')+1] = '.5'
        receipt = self.invoke_client(expected=2, extra=['--stage-timeout', '3600'])
        self.assertIn('owned launcher timeout', receipt['client_error']['detail'])
        self.assertEqual(receipt['config']['timeout'], .5)
        argv = json.loads((self.base/'launched').read_text())
        self.assertEqual(argv[argv.index('--timeout')+1], '3600')
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.base/'pid').read_text()), 0)

    def test_failed_run_query_zero_is_not_success(self):
        self.setup_client()
        self.env['FAILED'] = '1'
        receipt = self.invoke_client(expected=1)
        self.assertFalse(receipt['execution_completed'])

    def test_completed_without_explicit_report_ref_is_blocker(self):
        self.setup_client()
        self.env['NO_REF'] = '1'
        receipt = self.invoke_client(expected=1)
        self.assertTrue(receipt['execution_completed'])
        self.assertIn('no explicit execution_file', receipt['blocker'])
        self.assertNotIn('report', receipt)

    def test_missing_or_malformed_capability(self):
        for cap in ('false', 'null', '1', '"true"'):
            self.setup_client()
            self.env['CAP'] = cap
            self.invoke_client(expected=2)
            self.assertFalse((self.base/'launched').exists())

    def test_failure_cleans_owned_launcher(self):
        self.setup_client()
        self.env['BAD_LINE'] = '1'
        self.invoke_client(expected=2)
        pid = int((self.base/'pid').read_text())
        with self.assertRaises(ProcessLookupError): os.kill(pid, 0)

    def test_reader_setup_failure_reaps_real_owned_child(self):
        self.setup_client()
        wrapper = self.base/'fault-injection.py'
        wrapper.write_text('''import importlib.util, os, select, signal, subprocess, sys, threading, time
spec = importlib.util.spec_from_file_location('client', sys.argv[1])
client = importlib.util.module_from_spec(spec); spec.loader.exec_module(client)
mode, fault = sys.argv[2:4]
sys.argv = [sys.argv[1], *sys.argv[4:]]
signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
real_popen, real_thread, real_start = subprocess.Popen, threading.Thread, threading.Thread.start
owned = []
def popen(argv, *args, **kwargs):
    if argv[1:3] != ['flow', 'run']: return real_popen(argv, *args, **kwargs)
    ready, notify = os.pipe()
    try:
        # A real disposable child acknowledges only after filling its stdout pipe.
        p = real_popen([sys.executable, '-c',
            'import os,signal,sys\\nos.set_blocking(1,False)\\nwhile True:\\n'
            ' try: os.write(1,bytes(65536))\\n except BlockingIOError: break\\n'
            'os.write(int(sys.argv[1]),b"R"); os.close(int(sys.argv[1])); signal.pause()', str(notify)],
            stdout=subprocess.PIPE, text=True, pass_fds=(notify,))
        owned.append(p)
        assert select.select([ready], [], [], 5)[0], 'child readiness timeout'
        assert os.read(ready, 1) == b'R'
        return p
    finally:
        os.close(ready); os.close(notify)
def fail(*args, **kwargs):
    assert len(owned) == 1 and owned[0].poll() is None
    if mode == 'started': real_start(args[0])
    if fault == 'SIGINT': os.kill(os.getpid(), signal.SIGINT)
    elif fault == 'SIGTERM': os.kill(os.getpid(), signal.SIGTERM)
    elif fault == 'KeyboardInterrupt': raise KeyboardInterrupt('injected reader setup')
    else: raise RuntimeError('injected reader setup')
subprocess.Popen = popen
if mode == 'construct': threading.Thread = fail
else: threading.Thread.start = fail
started = time.monotonic()
try:
    result = client.main()
    assert result == (2 if fault == 'RuntimeError' else 130), result
    assert len(owned) == 1 and owned[0].returncode is not None
    assert owned[0].wait(timeout=0) != 0
    try: os.waitpid(owned[0].pid, os.WNOHANG)
    except ChildProcessError: pass
    else: raise AssertionError('child was not reaped')
    assert time.monotonic()-started < 12
    sys.exit(result)
finally:
    # Test cleanup owns exactly the Popen object created above, never a cached PID.
    for p in owned:
        if p.poll() is None: p.kill(); p.wait(timeout=5)
''')
        for mode, fault in [(m, f) for m in ('construct', 'start', 'started')
                            for f in ('KeyboardInterrupt', 'RuntimeError')] + [
                                ('start', 'SIGINT'), ('start', 'SIGTERM')]:
            with self.subTest(mode=mode, fault=fault):
                self.receipt.unlink(missing_ok=True)
                result = subprocess.run([sys.executable, str(wrapper), str(CLIENT), mode, fault,
                                         *self.args[2:]], env=self.env, capture_output=True,
                                        text=True, timeout=20)
                self.assertEqual(result.returncode, 2 if fault == 'RuntimeError' else 130,
                                 (result.stdout, result.stderr))
                receipt = json.loads(self.receipt.read_text())
                self.assertIsNone(receipt['allocation'])
                self.assertFalse(receipt['reconnect_available'])
                self.assertEqual(receipt['client_status'], 'failed' if fault == 'RuntimeError' else 'interrupted')
                self.assertNotEqual(receipt['launcher_exit'], 0)
                self.assertNotIn('execution_completed', receipt)

    def test_client_cancel_forwards_only_owned_launcher(self):
        self.setup_client()
        self.env['HOLD'] = '1'
        process = subprocess.Popen(self.args, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic()+10
            while not (self.base/'read').exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.02)
            process.send_signal(signal.SIGTERM)
            _, diagnostics = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 130, diagnostics)
            pid = int((self.base/'pid').read_text())
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
        finally:
            if process.poll() is None: process.kill(); process.wait()

    def test_stopping_reconnected_reader_leaves_run_alive(self):
        self.setup_client()
        self.env['HOLD'] = '1'
        owner = subprocess.Popen(self.args, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        reader = None
        try:
            deadline = time.monotonic()+10
            while not (self.base/'read').exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.02)
            # Reconnect operates on a separate client-cache copy: no concurrent writers.
            copy = self.base/'reader-cache.json'
            copy.write_text(self.receipt.read_text())
            reader = subprocess.Popen([sys.executable, str(CLIENT), '--receipt', str(copy), '--reconnect'],
                                      env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(.2)
            reader.terminate()
            reader.communicate(timeout=10)
            self.assertEqual(reader.returncode, 130)
            os.kill(int((self.base/'pid').read_text()), 0)
            self.assertIsNone(owner.poll())
        finally:
            if reader and reader.poll() is None: reader.kill(); reader.communicate()
            owner.terminate(); owner.communicate(timeout=10)

    def test_lexical_executable_parent_and_unsupported_version(self):
        self.setup_client()
        actual = self.base/'actual'
        (actual/'child').mkdir(parents=True)
        provider = actual/'provider'
        provider.write_text(self.provider.read_text())
        provider.chmod(0o755)
        (self.base/'alias').symlink_to(actual/'child', target_is_directory=True)
        lexical = str(self.base/'alias/../provider')
        self.args[self.args.index('--provider')+1] = lexical
        receipt = self.invoke_client()
        self.assertEqual(receipt['config']['provider'], lexical)
        self.receipt.unlink()
        provider.write_text(provider.read_text().replace('version=4', 'version=5'))
        self.invoke_client(expected=2)

    def test_stale_expected_identity_zero_launch(self):
        self.setup_client()
        wrapper = self.base/'stale wrapper'
        wrapper.write_text('#!'+sys.executable+'\nimport os,sys\na=sys.argv[1:]\n'+
            'if "--expected-plan-identity" in a: a[a.index("--expected-plan-identity")+1]="0"*64\n'+
            'os.execv('+repr(str(routing.EXE))+', ['+repr(str(routing.EXE))+']+a)\n')
        wrapper.chmod(0o755)
        self.args[self.args.index('--project')+1] = str(wrapper)
        self.invoke_client(expected=2)
        self.assertFalse((self.base/'launched').exists())

    def test_changed_source_and_catalog_reject_before_launch(self):
        for relative in ('ip/controlled_fifo/rtl/controlled_fifo.ml', 'asics/fifo_demo/project/flow_profiles.ml'):
            self.setup_client()
            # Mutation after preview, before real project run. Real project enforces identity.
            wrapper = self.base/'project wrapper'
            wrapper.write_text('#!'+sys.executable+'\n'+
                'import os,sys\nfrom pathlib import Path\n'+
                'if sys.argv[1:3] == ["flow","run"]:\n'+
                ' p=Path('+repr(str(self.root/relative))+'); p.write_text(p.read_text()+"\\n(* changed *)\\n")\n'+
                'os.execv('+repr(str(routing.EXE))+', ['+repr(str(routing.EXE))+']+sys.argv[1:])\n')
            wrapper.chmod(0o755)
            self.args[self.args.index('--project')+1] = str(wrapper)
            self.invoke_client(expected=2)
            self.assertFalse((self.base/'launched').exists())
            self.receipt.unlink()

    def test_installed_native_readiness_failure(self):
        self.setup_client()
        provider = os.environ.get('HARDCAML_ASIC_TEST_PROVIDER')
        if not provider: self.skipTest('explicit frozen native provider required')
        self.args[self.args.index('--provider')+1] = provider
        tools = self.base/'tools'
        (tools/'tt').mkdir(parents=True)
        (tools/'pdk').mkdir()
        receipt = self.invoke_client(expected=1, extra=['--python', '/bin/false'])
        self.assertFalse(receipt['execution_completed'])
        self.assertEqual(receipt['outcome']['status'], 'failed')
        self.assertFalse(receipt['inspection']['writer_active'])
        terminal = receipt['launcher_messages'][-1]
        self.assertEqual(terminal['methodology']['reference']['plan_identity'], receipt['plan_identity'])
        self.assertIsNone(terminal['execution_file'])
        # Historical public reads need neither the source checkout nor PATH/Python modules.
        self.root.rename(self.base/'source unavailable')
        result = subprocess.run([sys.executable, str(CLIENT), '--receipt', str(self.receipt), '--reconnect'],
                                env=dict(self.env, PATH='', PYTHONPATH=''), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_native_prepared_synthesis_report_and_allocation_only_reconnect(self):
        provider = os.environ.get('HARDCAML_ASIC_TEST_PROVIDER')
        fixture_source = os.environ.get('HARDCAML_ASIC_ENGINE_FIXTURES')
        if not provider or not fixture_source:
            self.skipTest('explicit installed provider and external engine fixture directory required')
        self.setup_client()
        self.args[self.args.index('--provider')+1] = provider
        fixtures = Path(fixture_source)
        # Fixture setup only: frozen inventory from the provider test preparation.
        # The client and its launch/query paths use exclusively public CLI commands.
        inventory = json.loads((fixtures/'classic-inventory.json').read_text())
        settings = json.loads((fixtures/'classic-settings.json').read_text())
        for profile, failure in [('balanced', False), ('synth_delay', False), ('balanced', True)]:
            with self.subTest(profile=profile, failure=failure):
                case = self.base/f'{profile}-{failure}'
                case.mkdir()
                tools = case/'bin'
                tools.mkdir()
                for name in ('python', 'docker', 'git'):
                    shutil.copyfile(fixtures/'stage_preparation_engine.py', tools/name)
                    (tools/name).chmod(0o755)
                shutil.copyfile(fixtures/'segment_service_engine.py', tools/'segment_service_engine.py')
                for name, value in [('classic-inventory.json', inventory), ('classic-settings.json', settings)]:
                    (case/name).write_text(json.dumps(value))
                # Obtain literal external collateral declarations from a public preview.
                plan = json.loads(subprocess.check_output([str(routing.EXE), 'flow', 'plan', '--json',
                    '--source-root', str(self.root), '--flow', 'standard', '--profile', profile,
                    '--endpoint', 'synthesis'], env=self.env, text=True))
                manifest = json.loads(plan['bundle_manifest'])
                for ref in manifest['target']['external_references']:
                    base = case/'tt' if ref['source'] == 'Support_tools' else case/'pdk'/manifest['target']['technology']
                    path = base/ref['path']
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if ref['source'] == 'Support_tools':
                        shutil.copyfile(fixtures/'support-tools'/ref['path'], path)
                    else:
                        path.write_text('native fixture collateral')
                env = dict(self.env, PATH=str(tools), PYTHONPATH='/denied', SERVICE_ENGINE_ROOT=str(case),
                    SERVICE_ENGINE_FIXTURE=str(fixtures/'segment_service_fixture.py'),
                    PREPARATION_IMAGE=(fixtures/'image.txt').read_text().strip(), PREPARATION_REVISION='a'*40,
                    BRIDGE_FIXTURE_FINAL_VIEWS='1', BRIDGE_FIXTURE_BUNDLE_CONFIG='1',
                    PREPARATION_RELEASE=str(case/'release'))
                env['PREPARATION_REVISIONS'] = json.dumps({
                    str(case/'tt'): manifest['requested_tools']['support_tools_revision'],
                    str(case/'pdk'): manifest['requested_tools']['pdk_revision'],
                    str(case/'pdk'/manifest['target']['technology']): manifest['requested_tools']['pdk_revision']})
                if failure:
                    env['SERVICE_FIXTURE_MODE'] = 'exit17'
                receipt_path = case/'cache.json'
                args = self.args.copy()
                for flag, value in [('--receipt', receipt_path), ('--results-root', case/'results'), ('--timeout', '90')]:
                    args[args.index(flag)+1] = str(value)
                args += ['--flow', 'standard', '--profile', profile, '--python', str(tools/'python'),
                         '--support-tools', str(case/'tt'), '--pdk-root', str(case/'pdk')]
                owner = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                reader = None
                try:
                    deadline = time.monotonic()+30
                    while not (case/'backend-waiting').exists():
                        self.assertIsNone(owner.poll(), owner.communicate() if owner.poll() is not None else '')
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.02)
                    early = json.loads(receipt_path.read_text())
                    self.assertIsNotNone(early['allocation'])
                    self.assertIsNone(early.get('outcome'))
                    self.assertFalse(any(m.get('status') == 'completed' for m in early['launcher_messages']))
                    # An allocation/cursor cache alone suffices; lose all terminal stdout.
                    early['launcher_messages'] = []
                    reader_path = case/'reader.json'
                    reader_path.write_text(json.dumps(early))
                    reader = subprocess.Popen([sys.executable, str(CLIENT), '--reconnect', '--receipt', str(reader_path)],
                        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    time.sleep(.2)
                    reader.send_signal(signal.SIGINT)
                    _, err = reader.communicate(timeout=10)
                    self.assertEqual(reader.returncode, 130, err)
                    self.assertIsNone(owner.poll())
                    (case/'release').touch()
                    out, err = owner.communicate(timeout=90)
                    self.assertEqual(owner.returncode, 1 if failure else 0, (out, err))
                    saved = json.loads(receipt_path.read_text())
                    self.assertEqual(saved['execution_completed'], not failure)
                    self.assertEqual(saved['report']['methodology']['plan_identity'], saved['plan_identity'])
                    self.assertEqual(saved['report_status'], 'available')
                    self.assertEqual(saved['acceptance'], 'not_evaluated')
                    self.assertEqual(saved['execution_file'], saved['inspection']['execution_file'])
                    reconnect = subprocess.run([sys.executable, str(CLIENT), '--reconnect', '--receipt', str(reader_path)],
                        env=dict(env, PATH='/denied', PYTHONPATH='/denied'), capture_output=True, text=True, timeout=30)
                    self.assertEqual(reconnect.returncode, 1 if failure else 0, reconnect.stderr)
                    resumed = json.loads(reader_path.read_text())
                    self.assertEqual(resumed['launcher_messages'], [])
                    self.assertEqual(resumed['execution_file'], saved['execution_file'])
                    self.assertEqual(resumed['report'], saved['report'])
                finally:
                    for process in (reader, owner):
                        if process and process.poll() is None:
                            process.terminate()
                            process.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main()
