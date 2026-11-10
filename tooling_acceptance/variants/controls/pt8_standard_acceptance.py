#!/usr/bin/env python3
"""Real private standard Plan/emit/Fresh source preparation; zero physical launch."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'integration/workbench'))
sys.path.insert(0, str(ROOT.parent / 'hardcaml_workbench/demo/synthetic_flow'))
from http_client import Client, field, sexp, parse
from pt8_acceptance import write, sha
from pt8_workbench_native_acceptance import protected_state, installed_state


def source_baseline(project, manifest):
    # Setup snapshots authored source before writing these session-local configs.
    # Check all other copied bytes against that snapshot, then freeze the actual
    # configured source tree for this acceptance attempt.
    configured = {f'hardcaml-workbench-{domain}.sexp'
                  for domain in ('asic', 'preparation', 'simulation')}
    baseline = {name: sha(project / name) for name in manifest['source_snapshot']}
    assert all(baseline[name] == digest for name, digest in manifest['source_snapshot'].items()
               if name not in configured), 'private authored source differs from its capture'
    return baseline


def wait(query, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = query()
        if value:
            return value
        time.sleep(.05)
    raise TimeoutError('private standard acceptance wait')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--protected-session', type=Path, required=True)
    args = parser.parse_args()
    session = args.session.resolve(strict=True)
    old = args.protected_session.resolve(strict=True)
    manifest = json.loads((session / 'manifest.json').read_text())
    old_manifest = json.loads((old / 'manifest.json').read_text())
    project = Path(manifest['project_root'])
    frozen_sources = source_baseline(project, manifest)
    output = session / ('standard-acceptance-' + uuid.uuid4().hex)
    output.mkdir()
    for name in ('discovery', 'state'):
        (output / name).mkdir()
    protected = protected_state()
    old_install = installed_state(old, old_manifest)
    new_install = installed_state(session, manifest)
    write(output / 'preservation-before.json', {'root': protected, 'old': old_install, 'new': new_install})
    result = {'pass': False, 'eda_allocation': 0, 'physical_launches': 0,
              'command': sys.argv, 'session': str(session), 'plans': []}
    http = None
    child = None
    def command(label, argv):
        directory = output / label
        directory.mkdir()
        proc = subprocess.run(list(map(str, argv)), cwd=project, capture_output=True, timeout=180)
        (directory / 'stdout.log').write_bytes(proc.stdout)
        (directory / 'stderr.log').write_bytes(proc.stderr)
        write(directory / 'command.json', {'argv': list(map(str, argv)), 'cwd': str(project),
              'exit_code': proc.returncode, 'eda_allocation': 0})
        assert proc.returncode == 0, str(directory)
        return json.loads(proc.stdout)
    try:
        binary = session / 'provider/project.exe'
        result['project_sha256'] = sha(binary)
        result['provider_receipt_sha256'] = sha(Path(manifest['generation']) / 'receipt.json')
        listing = command('list', [binary, 'flow', 'list', '--json'])
        write(output / 'listing.json', listing)
        # Captured binaries contain their original source inventories. A legacy
        # binary cannot consume a new-layout tree merely by changing source-root.
        # Keep the old session immutable and record this compatibility boundary.
        layout = manifest.get('source_layout')
        if layout and old_manifest.get('source_layout') == layout:
            command('old-binary-source-only-plan', [old / 'provider/project.exe', 'flow', 'plan',
                '--flow', 'standard', '--profile', 'balanced', '--endpoint', 'synthesis',
                '--source-root', project, '--json'])
            result['old_binary_plan'] = {'status': 'passed', 'source_layout': layout}
        else:
            result['old_binary_plan'] = {
                'status': 'unavailable', 'old_source_layout': old_manifest.get('source_layout'),
                'new_source_layout': layout,
                'reason': 'captured source layouts differ; use the newly built session binary'}
        write(output / 'old-binary-layout-compatibility.json', result['old_binary_plan'])
        log = (output / 'daemon.stdout').open('xb')
        err = (output / 'daemon.stderr').open('xb')
        argv = ['strace', '-f', '-s', '4096', '-e', 'trace=process', '-o', str(output / 'process.strace'),
            '--', sys.executable, '-B', str(ROOT / 'integration/workbench/pt8_workbench_launch.py'),
            'daemon', '--session', str(session), '--runtime-root', str(output)]
        write(output / 'daemon-command.json', argv)
        child = subprocess.Popen(argv, stdout=log, stderr=err, start_new_session=True)
        metadata_path = output / 'discovery/daemon.sexp'
        wait(lambda: metadata_path.exists() or child.poll() is not None, timeout=20)
        assert child.poll() is None
        metadata = dict(parse(metadata_path.read_text()))
        endpoint = urlsplit(metadata['endpoint'])
        assert endpoint.hostname in ('localhost', '127.0.0.1', '::1') and endpoint.port != 41735
        http = Client(metadata['endpoint'], project)
        discovered = http.rpc('Discover')
        flows = field(discovered, 'flows')
        assert len(flows) == 1 and field(flows[0], 'id') == 'standard'
        endpoints = field(flows[0], 'fresh_stage_endpoints')
        assert endpoints == ['synthesis', 'floorplan', 'placement', 'cts', 'routing', 'timing', 'signoff']
        profiles = field(flows[0], 'profiles')
        for profile in profiles:
            for endpoint in endpoints:
                selection = [['flow', 'standard'], ['profile', profile], ['endpoint', endpoint], ['assignments', []]]
                snapshot = http.rpc(sexp(['Plan', selection]))
                preview = field(snapshot, 'preview')[0]
                plan = json.loads(field(preview, 'plan_json'))
                assert field(preview, 'selection') == selection
                assert plan['plan_identity'] == field(preview, 'plan_identity')
                result['plans'].append({'profile': profile, 'endpoint': endpoint,
                    'plan_identity': plan['plan_identity'], 'bundle_identity': plan['bundle_identity']})
        selected = [['flow', 'standard'], ['profile', 'balanced'], ['endpoint', 'synthesis'], ['assignments', []]]
        options = ['--flow', 'standard', '--profile', 'balanced', '--endpoint', 'synthesis',
                   '--source-root', project, '--json']
        emission = command('emit', [binary, 'flow', 'emit', *options, '--results-root', output / 'emitted'])
        bundle = Path(emission['output_dir']).resolve(strict=True)
        assert bundle.is_relative_to(session)
        assert (bundle / 'manifest.json').is_file()
        result['emitted_bundle'] = emission
        # Stage physical intent only: validates ordinary Fresh input scope without admission.
        staged = http.rpc(sexp(['Stage_fresh', ['selection', selected], ['elaboration_only', 'false'],
                                ['expected_plan_identity', []]]), wait=False)
        intent = field(staged, 'fresh_intent')[0]
        assert field(intent, 'elaboration_only') == 'false'
        assert str(project) in field(intent, 'scope')
        assert not field(staged, 'workflows') and not field(staged, 'runs')
        write(output / 'physical-fresh-intent.json', intent)
        preparation = http.rpc('Get', domain='preparation')
        assert field(preparation, 'availability') == 'Available'
        # The unified Fresh route actually builds source and emits, elaboration only.
        staged = http.rpc(sexp(['Stage_fresh', ['selection', selected], ['elaboration_only', 'true'],
                                ['expected_plan_identity', []]]), wait=False)
        intent = field(staged, 'fresh_intent')[0]
        key = 'standard-source-only-' + uuid.uuid4().hex
        http.rpc(sexp(['Launch_fresh', ['key', key], ['intent_id', field(intent, 'id')]]), wait=False)
        def finished():
            snap = http.rpc('Get', wait=False)
            workflow = next((w for w in field(snap, 'workflows') if field(w, 'key') == key), None)
            return workflow if workflow and field(workflow, 'phase') in (
                'Completed', 'Failed', 'Cancelled', 'Interrupted') else None
        workflow = wait(finished, timeout=600)
        write(output / 'elaboration-workflow.json', workflow)
        assert field(workflow, 'phase') == 'Completed', workflow
        assert not field(workflow, 'run') and not field(workflow, 'reference')
        prepared = field(workflow, 'prepared')[0]
        assert Path(field(prepared, 'bundle_directory')).resolve().is_relative_to(session)
        for name in ('build_job', 'emission_job'):
            job = field(workflow, name)[0]
            assert field(job, 'state') == 'Complete'
            logs = http.raw('/api/v1/read-log', [['instance_id', http.instance], ['job', field(job, 'id')],
                ['offset', 0], ['max_records', 100], ['max_bytes', 65536]])
            write(output / (name + '.json'), {'job': job, 'logs': logs})
        assert (project / '_build/default/asics/fifo_demo/cli/project.exe').is_file()
        # Restore a physical stage ready for coordinator review, never launch it.
        staged = http.rpc(sexp(['Stage_fresh', ['selection', selected], ['elaboration_only', 'false'],
                                ['expected_plan_identity', []]]), wait=False)
        assert field(staged, 'fresh_intent') and not field(staged, 'runs')
        simulation = http.rpc('Discover', domain='simulation')
        simulation = wait(lambda: (lambda s: s if field(s, 'discovery_digest') else None)(
            http.rpc('Get', domain='simulation')), timeout=30)
        write(output / 'pt8-discovery.json', simulation)
        assert 'pt8-memory-workloads' in sexp(simulation)
        result.update(pass_=True, preparation_available=True, physical_fresh_stage_available=True,
            source_build_and_emission_completed=True, pt8_discovery=True,
            fresh_prepared=prepared, standard_profiles=profiles, standard_endpoints=endpoints)
        result['pass'] = result.pop('pass_')
    finally:
        if http:
            write(output / 'http.json', http.history)
        if child:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            result['owned_daemon_exit'] = child.returncode
            log.close()
            err.close()
        after = {'root': protected_state(), 'old': installed_state(old, old_manifest),
                 'new': installed_state(session, manifest)}
        write(output / 'preservation-after.json', after)
        result['preserved'] = after == {'root': protected, 'old': old_install, 'new': new_install}
        result['source_snapshot_unchanged'] = all(sha(project / name) == digest
            for name, digest in frozen_sources.items())
        result['wb_binaries'] = {str(p): sha(p) for p in (
            Path(manifest['wb_build_root']) / 'default/daemon/main.exe',
            Path(manifest['wb_build_root']) / 'default/terminal/main.exe')}
        if (output / 'process.strace').exists():
            trace = (output / 'process.strace').read_text()
            result['no_physical_provider_admission'] = not any(token in trace for token in (
                '"stages",', '"yosys"', '"openroad"', '"librelane"', '"iverilog"', '"vvp"'))
            assert result['no_physical_provider_admission']
        write(output / 'assertions.json', result)
        print(output, flush=True)
        assert result['preserved'] and result['source_snapshot_unchanged']


if __name__ == '__main__':
    main()
