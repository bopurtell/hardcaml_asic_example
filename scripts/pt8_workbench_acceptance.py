#!/usr/bin/env python3
"""Real direct FS2 acceptance; retained positive/negative/cancel evidence, no builds."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
from wire import parse, record, sexp
from pt8_acceptance import write, sha
from pt8_workloads import ref


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    args = parser.parse_args()
    session = args.session.resolve(strict=True)
    manifest = json.loads((session / 'manifest.json').read_text())
    provider = manifest['provider_command']
    generation = Path(manifest['generation'])
    output = session / ('direct-acceptance-' + uuid.uuid4().hex)
    output.mkdir()
    def command(label, argv, code=0):
        directory = output / label
        directory.mkdir()
        with (directory / 'stdout.log').open('xb') as out, (directory / 'stderr.log').open('xb') as err:
            result = subprocess.run(list(map(str, argv)), stdout=out, stderr=err, timeout=180)
        write(directory / 'command.json', {'argv': list(map(str, argv)), 'exit_code': result.returncode})
        assert result.returncode == code, (label, result.returncode, directory)
        return (directory / 'stdout.log').read_text()
    discovered = record(parse(command('discover', provider + ['discover', '--protocol-version', '1'])), ['protocol_version', 'suites'])
    assert discovered['protocol_version'] == '1' and len(discovered['suites']) == 1
    suite = dict(discovered['suites'][0])
    assert suite['id'] == 'pt8-memory-workloads' and suite['default_seed'] == '34097'
    assert [dict(c)['id'] for c in suite['cases']] == ['flops256', 'exact256']
    selection = [('suite', 'pt8-memory-workloads'), ('cases', ['flops256', 'exact256']),
                 ('seed', '34097'), ('parameters', []), ('asic_inputs', [])]
    def request(label, changes=(), prefix=provider):
        directory = output / label
        directory.mkdir()
        artifacts = directory / 'artifacts'
        artifacts.mkdir()
        selected = dict(selection)
        selected.update(changes)
        (directory / 'request.sexp').write_text(sexp([('protocol_version', 1),
            ('attempt_id', label), ('selection', list(selected.items()))]) + '\n')
        return directory, prefix + ['run', '--protocol-version', '1', '--request', str(directory / 'request.sexp'),
            '--events', str(directory / 'events.sexp'), '--artifact-dir', str(artifacts)]
    positive, argv = request('positive-both')
    command('positive-command', argv)
    events = [record(parse(line), ['protocol_version', 'attempt_id', 'sequence', 'payload'])
              for line in (positive / 'events.sexp').read_text().splitlines()]
    assert [int(e['sequence']) for e in events] == list(range(len(events)))
    assert events[0]['payload'] == 'Started' and events[-1]['payload'] == ['Finished', 'Passed']
    results = []
    for case in ('flops256', 'exact256'):
        artifact = json.loads((positive / 'artifacts' / (case + '-result-reference.json')).read_text())
        assert set(artifact) == {'contract', 'schema_version', 'result', 'source_digest'}
        assert artifact['contract'] == 'hardcaml-workbench.pt8-result-reference' and artifact['schema_version'] == 1
        result = Path(artifact['result'])
        assert result.is_absolute() and result.is_relative_to(ROOT / '.dev/asic-pt8-workbench/workloads')
        results.append(result)
        inspection = json.loads(command(case + '-handoff', [generation / 'bin/hardcaml-asic-flow',
            'workload-inspect', result, '--json']))
        assert inspection['source_digest'] == artifact['source_digest']
        assert inspection['outcome']['functional'] == 'pass'
        assert len(inspection['metrics']) == 7
        r = json.loads(result.read_text())
        assert inspection['binding']['bundle'] == str(Path(r['bundle']).resolve(strict=True))
        assert inspection['binding']['bundle_identity'] == json.loads(
            (Path(r['bundle']) / 'manifest.json').read_text())['identity']
        assert Path(r['bundle']).is_relative_to(result.parent.parent / 'bundles')
        sim = json.loads((result.parent / 'simulation.json').read_text())
        assert sim['rtl_mode'] == 'implementation'
        if case == 'exact256':
            models = Path(provider[provider.index('--model-root') + 1])
            for name in ('RM_IHPSG13_1P_256x16_c2_bm_bist.v', 'RM_IHPSG13_1P_core_behavioral_bm_bist.v'):
                stock = ROOT / '_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog' / name
                assert sha(result.parent / name) == sha(stock) == sha(models / name)
    for label, changes in [('seed-rejected', [('seed', '1')]),
        ('hex-seed-rejected', [('seed', '0x8531')]), ('parameter-rejected', [('parameters', [('depth', '128')])]),
        ('case-rejected', [('cases', ['flops-ignored'])]), ('duplicate-case', [('cases', ['flops256', 'flops256'])])]:
        directory, argv = request(label, changes)
        before = set((ROOT / '.dev/asic-pt8-workbench/workloads').iterdir())
        command(label + '-command', argv, 2)
        assert not (directory / 'events.sexp').exists()
        assert set((ROOT / '.dev/asic-pt8-workbench/workloads').iterdir()) == before
    # A missing stock model must retain partial actual evidence and publish no
    # reference for that case, while retaining the preceding successful case.
    empty = output / 'empty-models'
    empty.mkdir()
    broken = provider.copy()
    broken[broken.index('--model-root') + 1] = str(empty)
    partial, argv = request('partial-model', prefix=broken)
    command('partial-command', argv)
    payloads = [dict(parse(line))['payload'] for line in (partial / 'events.sexp').read_text().splitlines()]
    assert payloads[-1] == ['Finished', 'Failed']
    assert (partial / 'artifacts/flops256-result-reference.json').exists()
    assert not (partial / 'artifacts/exact256-result-reference.json').exists()
    # Signal the real foreground provider while its native emitter is running.
    cancel, argv = request('cancelled', [('cases', ['flops256'])])
    with (cancel / 'stdout.log').open('xb') as out, (cancel / 'stderr.log').open('xb') as err:
        child = subprocess.Popen(argv, stdout=out, stderr=err)
        deadline = time.monotonic() + 20
        native = []
        while time.monotonic() < deadline and child.poll() is None:
            children = Path(f'/proc/{child.pid}/task/{child.pid}/children').read_text().split()
            if children:
                native = children
                child.send_signal(signal.SIGTERM)
                break
            time.sleep(.002)
        assert native, 'never observed foreground native child'
        code = child.wait(timeout=10)
        assert code == 130, (code, cancel)
        assert all(not Path('/proc/' + pid).exists() for pid in native), 'orphan child'
    write(cancel / 'command.json', {'argv': argv, 'exit_code': code, 'native_child_pids': native,
                                  'signal': 'SIGTERM-to-provider-pid', 'orphans': False})
    assert dict(parse((cancel / 'events.sexp').read_text().splitlines()[-1]))['payload'] == ['Finished', 'Incomplete']
    assert not list((cancel / 'artifacts').iterdir())
    # Readable partial result fixture derived from actual positive evidence;
    # explicitly not a new execution, with fully rebound retained references.
    fixture = output / 'partial-fixture-not-execution'
    shutil.copytree(results[0].parent, fixture)
    simulation = json.loads((fixture / 'simulation.json').read_text())
    simulation['status'] = 'partial'
    (fixture / 'simulation.json').write_text(json.dumps(simulation) + '\n')
    result = json.loads((fixture / 'result.json').read_text())
    result['simulation'] = ref(fixture, fixture / 'simulation.json')
    (fixture / 'result.json').write_text(json.dumps(result) + '\n')
    results += [fixture / 'result.json', ROOT / 'acceptance/pt8-workloads/simulation-04/ignored-workload/result.json']
    partial_inspection = json.loads(command('partial-inspection', [generation / 'bin/hardcaml-asic-flow',
        'workload-inspect', results[-2], '--json']))
    assert partial_inspection['outcome']['functional'] == 'unavailable'
    assert partial_inspection['outcome']['performance'] == 'unavailable'
    failed_inspection = json.loads(command('failed-inspection', [generation / 'bin/hardcaml-asic-flow',
        'workload-inspect', results[-1], '--json']))
    assert failed_inspection['outcome']['functional'] == 'fail'
    assert failed_inspection['outcome']['performance'] == 'unavailable'
    spec = importlib.util.spec_from_file_location('cli_acceptance', ROOT.parent / 'hardcaml_asic/bin/workload_inspect_acceptance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check(generation / 'bin/hardcaml-asic-flow', session / 'provider/workload_public.exe', results, output / 'cli-parity')
    write(output / 'assertions.json', {'pass': True, 'actual_positive_cases': 2,
        'public_cli_api_parity': True, 'strict_cli': True, 'seed_rejected_before_execution': True,
        'cancelled_native_child_reaped': True, 'partial_case_no_reference': True,
        'result_reference_digest_checked': True, 'stock_models_unchanged': True,
        'eda_allocation': 0, 'session': str(session), 'results': list(map(str, results))})
    print(str(output))


if __name__ == '__main__':
    main()
