#!/usr/bin/env python3
"""One real direct-FS2 Exact run against the immutable private recovery snapshot."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'integration/workbench'))
from wire import parse, record, sexp
from pt8_acceptance import write, sha
from pt8_workbench_native_acceptance import protected_state, installed_state


def tree(root):
    return {str(p): {'sha256': sha(p), 'symlink': os.readlink(p) if p.is_symlink() else None}
            for p in sorted(root.rglob('*')) if p.is_file()}


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
    provider = manifest['provider_command']
    assert Path(provider[provider.index('--producer-root') + 1]) == project
    output = session / ('exact-fs2-verification-' + uuid.uuid4().hex)
    output.mkdir()
    def known_state():
        return {'root_configs_selected_programs': protected_state(),
            'owner_flow_results': tree(ROOT / '_flow_results'),
            'owner_pt8_results': tree(ROOT / '.dev/asic-pt8-workbench/workloads'),
            'old_config_provider_generation': installed_state(old, old_manifest),
            'new_config_provider_generation': installed_state(session, manifest),
            'private_source': {name: sha(project / name) for name in manifest['source_snapshot']}}
    before = known_state()
    write(output / 'known-state-before.json', before)
    result = {'pass': False, 'physical_eda_launches': 0, 'actual_simulation_cases': 1,
        'session': str(session), 'argv': sys.argv, 'provider_command': provider}
    def command(label, argv):
        directory = output / label
        directory.mkdir()
        proc = subprocess.run(list(map(str, argv)), cwd=output, capture_output=True, timeout=240,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1'))
        (directory / 'stdout.log').write_bytes(proc.stdout)
        (directory / 'stderr.log').write_bytes(proc.stderr)
        write(directory / 'command.json', {'argv': list(map(str, argv)), 'cwd': str(output),
            'exit_code': proc.returncode, 'max_parallel_processes': 1})
        assert proc.returncode == 0, str(directory)
        return proc.stdout.decode()
    try:
        discovered = record(parse(command('discover', provider + ['discover', '--protocol-version', '1'])),
                            ['protocol_version', 'suites'])
        assert dict(discovered['suites'][0])['id'] == 'pt8-memory-workloads'
        transport = output / 'fs2-transport'
        transport.mkdir()
        artifacts = transport / 'artifacts'
        artifacts.mkdir()
        request = transport / 'request.sexp'
        request.write_text(sexp([('protocol_version', 1), ('attempt_id', 'recovery-exact-' + uuid.uuid4().hex),
            ('selection', [('suite', 'pt8-memory-workloads'), ('cases', ['exact256']), ('seed', '34097'),
                           ('parameters', []), ('asic_inputs', [])])]) + '\n')
        command('run', ['strace', '-f', '-s', '4096', '-e', 'trace=process', '-o', output / 'process.strace',
            '--', *provider, 'run', '--protocol-version', '1', '--request', request,
            '--events', transport / 'events.sexp', '--artifact-dir', artifacts])
        events = [dict(parse(line)) for line in (transport / 'events.sexp').read_text().splitlines()]
        assert [int(e['sequence']) for e in events] == list(range(len(events)))
        assert events[0]['payload'] == 'Started' and events[-1]['payload'] == ['Finished', 'Passed']
        assert [p['payload'][1] for p in events if isinstance(p['payload'], list)
                and p['payload'][0] == 'Case_started'] == ['exact256']
        reference = json.loads((artifacts / 'exact256-result-reference.json').read_text())
        assert set(reference) == {'contract', 'schema_version', 'result', 'source_digest'}
        result_path = Path(reference['result']).resolve(strict=True)
        store = project / '.dev/asic-pt8-workbench/workloads'
        assert result_path.is_relative_to(store)
        retained = result_path.parent.parent
        inventory_before = tree(retained)
        r = json.loads(result_path.read_text())
        simulation = json.loads((result_path.parent / 'simulation.json').read_text())
        bundle = Path(r['bundle']).resolve(strict=True)
        assert bundle.is_relative_to(retained / 'bundles')
        assert simulation['rtl_mode'] == 'implementation' and simulation['status'] == 'completed'
        assert simulation['bundle_identity'] == json.loads((bundle / 'manifest.json').read_text())['identity']
        models = Path(provider[provider.index('--model-root') + 1])
        for name in ('RM_IHPSG13_1P_256x16_c2_bm_bist.v', 'RM_IHPSG13_1P_core_behavioral_bm_bist.v'):
            stock = ROOT / '_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog' / name
            assert sha(result_path.parent / name) == sha(models / name) == sha(stock)
        # The entire FS2 transport location changes; the published closure must still open.
        transport.rename(output / 'completed-fs2-transport')
        generation = Path(manifest['generation'])
        inspect = [generation / 'bin/hardcaml-asic-flow', 'workload-inspect', result_path, '--json']
        view = json.loads(command('reopen-retained', inspect))
        assert view['source_digest'] == reference['source_digest']
        assert view['outcome']['functional'] == 'pass' and view['outcome']['performance'] == 'available'
        assert view['binding']['bundle'] == str(bundle)
        assert len(view['metrics']) == 7
        assert tree(retained) == inventory_before
        write(output / 'retained-closure-inventory.json', inventory_before)
        trace = (output / 'process.strace').read_text()
        assert not any(token in trace for token in ('"stages",', '"yosys"', '"openroad"', '"librelane"'))
        assert not any('execve(' in line and '"dune"' in line for line in trace.splitlines())
        result.update({'pass': True, 'result_reference': reference, 'simulation_attempt': simulation['attempt_id'],
            'persistent_bundle': str(bundle), 'retained_closure': str(retained), 'closure_files': len(inventory_before),
            'stock_models_unchanged': True, 'transport_relocated_before_reopen': True,
            'provider_hashes': manifest['captured_files'], 'source_builds': 0,
            'provider_receipt_sha256': sha(generation / 'receipt.json')})
    finally:
        after = known_state()
        write(output / 'known-state-after.json', after)
        result['known_state_unchanged'] = before == after
        write(output / 'assertions.json', result)
        print(output, flush=True)
        assert result['known_state_unchanged']


if __name__ == '__main__':
    main()
