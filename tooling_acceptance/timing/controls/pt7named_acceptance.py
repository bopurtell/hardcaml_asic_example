#!/usr/bin/env python3
"""Independent public named synthesis consumer; new directories for every attempt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / '.dev/asic-pt7named'
EVIDENCE = ROOT / 'acceptance/pt7named'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not p.is_symlink()}


def command(output, label, argv, generation=None, expected=(0,), timeout=900):
    directory = output / label
    directory.mkdir()
    argv = list(map(str, argv))
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    if generation:
        env['OCAMLPATH'] = str(generation / 'lib') + (':' + env['OCAMLPATH'] if env.get('OCAMLPATH') else '')
        env['PATH'] = str(generation / 'bin') + ':' + env['PATH']
    receipt = {'argv': argv, 'cwd': str(ROOT), 'timeout_seconds': timeout,
               'allocation_jobs': 6, 'sta_threads': 1,
               'thread_environment': {key: env[key] for key in
                                      ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
               'generation': str(generation) if generation else None}
    if generation:
        receipt['provider_receipt_sha256'] = sha(generation / 'receipt.json')
    start = time.monotonic()
    with (directory / 'stdout.log').open('xb') as out, (directory / 'stderr.log').open('xb') as err:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=out, stderr=err, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = 124
            receipt['timed_out'] = True
    receipt.update(exit_code=code, elapsed_seconds=time.monotonic() - start,
                   logs={name: sha(directory / name) for name in ('stdout.log', 'stderr.log')})
    write_new(directory / 'command.json', receipt)
    if code not in expected:
        raise RuntimeError(f'{label}: exit {code}; retained at {directory}')
    return directory / 'stdout.log'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('capture', 'build', 'prepare', 'run', 'public'))
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', type=Path)
    parser.add_argument('--profile', choices=('area', 'delay'), default='area')
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--runtime-confirmation', type=Path,
                        help='A-authored JSON confirming named worker bounds; required before EDA')
    args = parser.parse_args()
    if not args.attempt or Path(args.attempt).name != args.attempt:
        parser.error('--attempt must be a single directory name')
    output = EVIDENCE / args.attempt
    output.mkdir(parents=True, exist_ok=False)
    generation = args.generation.resolve(strict=True) if args.generation else None
    if generation and not generation.is_relative_to(STORE / 'provider/generations'):
        parser.error('--generation must belong to the isolated named provider store')
    if args.phase == 'capture':
        command(output, 'capture', ['opam', 'exec', '--switch=5.2.0+ox', '--', 'flock',
                '/tmp/opencode/asic-pt7-build.lock', 'python3', '-B', 'scripts/asic_dependency.py',
                '--store', STORE / 'provider', 'refresh', '--source', ROOT.parent / 'hardcaml_asic',
                '--mode', 'development', '--jobs', '6'], timeout=1200)
        return
    if not generation:
        parser.error('--generation must name the exact newly captured generation')
    provider = generation / 'bin/hardcaml-asic-flow'
    if args.phase == 'build':
        command(output, 'build', ['opam', 'exec', '--switch=5.2.0+ox', '--', 'flock',
                '/tmp/opencode/example-pt7-build.lock', 'dune', 'build', '--build-dir',
                '_build_pt7named', '-j6', 'tooling_acceptance/timing/named_flow/named_timing_cli.exe',
                'tooling_acceptance/timing/named_flow/reader/named_sources.exe',
                'tooling_acceptance/timing/named_flow/reader/named_snapshot.exe',
                'tooling_acceptance/timing/named_flow/reader/named_precheck.exe'], generation)
    elif args.phase == 'prepare':
        cli = ROOT / '_build_pt7named/default/tooling_acceptance/timing/named_flow/named_timing_cli.exe'
        plan_file = command(output, 'plan', [cli, 'plan', ROOT, args.profile], generation)
        plan = json.loads(plan_file.read_text())
        identity = plan['plan_identity']
        emission_file = command(output, 'emit', [cli, 'emit', ROOT, args.profile,
                                                STORE / 'bundles', identity], generation)
        emission = json.loads(emission_file.read_text())
        assert emission['plan'] == plan
        bundle = Path(emission['output_dir'])
        manifest = json.loads((bundle / 'manifest.json').read_text())
        for member in manifest['files']:
            assert sha(bundle / member['path']) == member['sha256'], member['path']
        assert manifest['timing_native_coverage']['schema'] == 2
        assert manifest['timing_native_coverage']['profile'] == 'opensta-2.7-native-state-v2'
        frozen = output / 'methodology-plan.json'
        write_new(frozen, plan)
        frozen.chmod(0o444)
        write_new(output / 'prepared.json', {
            'profile': args.profile, 'generation': str(generation),
            'provider_receipt_sha256': sha(generation / 'receipt.json'),
            'plan_file': str(frozen), 'plan_sha256': sha(frozen), 'plan_identity': identity,
            'bundle': str(bundle), 'bundle_identity': emission['bundle_identity'],
            'bundle_inventory': inventory(bundle)})
    elif args.phase == 'run':
        if not args.runtime_confirmation or not args.prepared:
            parser.error('run requires --runtime-confirmation and --prepared')
        confirmation = json.loads(args.runtime_confirmation.read_text())
        for phase in ('preflight', 'probe', 'synthesis', 'publication', 'analysis'):
            assert type(confirmation[phase]) is int and 1 <= confirmation[phase] <= 6, phase
        assert confirmation['sta_threads'] == 1 and confirmation['confirmed_by'] == 'A'
        prepared = json.loads(args.prepared.read_text())
        assert prepared['generation'] == str(generation)
        assert prepared['provider_receipt_sha256'] == sha(generation / 'receipt.json')
        assert prepared['plan_sha256'] == sha(Path(prepared['plan_file']))
        assert prepared['bundle_inventory'] == inventory(Path(prepared['bundle']))
        write_new(output / 'runtime-confirmation.json', confirmation)
        # Enumerate complete declared host inputs; admission uses provider limits.
        command(output, 'closure-precheck', [sys.executable, '-B',
                ROOT / 'tooling_acceptance/timing/controls/pt7named_precheck.py', '--pdk',
                ROOT / '_flow_tools/pdk/ihp-sg13cmos5l',
                '--bundle', prepared['bundle'], '--plan', prepared['plan_file'],
                '--output', output / 'pdk-precheck.json'], generation)
        command(output, 'public-precheck',
                [ROOT / '_build_pt7named/default/tooling_acceptance/timing/named_flow/reader/named_precheck.exe',
                 output / 'pdk-precheck.json',
                 (ROOT / '_flow_tools/pdk').resolve(strict=True),
                 (ROOT / '_flow_tools/tt').resolve(strict=True)], generation)
        workspace = STORE / 'workspaces' / args.attempt
        workspace.parent.mkdir(parents=True, exist_ok=True)
        assert not workspace.exists(), workspace
        command(output, 'stages', [provider, 'stages', prepared['bundle'],
                '--methodology-plan', prepared['plan_file'], '--expected-plan-identity', prepared['plan_identity'],
                '--workspace', workspace, '--checkpoint-store', workspace / 'checkpoints',
                '--support-tools', ROOT / '_flow_tools/tt', '--pdk-root', ROOT / '_flow_tools/pdk',
                '--python', ROOT / '_flow_tools/.venv/bin/python', '--timeout', '600', '--json'], generation)
        assert prepared['bundle_inventory'] == inventory(Path(prepared['bundle']))
        write_new(output / 'run-receipt.json', {'workspace': str(workspace),
                  'prepared': str(args.prepared.resolve()), 'bundle_unchanged': True,
                  'runtime_confirmation_sha256': sha(args.runtime_confirmation)})
    else:
        if not args.execution:
            parser.error('public requires exact --execution FILE')
        execution = args.execution.resolve(strict=True)
        before = inventory(execution.parent)
        inspected = command(output, 'inspect', [provider, 'timing-intent-inspect', execution,
                                                '--kind', 'execution', '--json'], generation, (1,))
        reported = command(output, 'report', [provider, 'report', execution, '--json'], generation, (0, 1))
        sources_file = command(output, 'sources',
                               [ROOT / '_build_pt7named/default/tooling_acceptance/timing/named_flow/reader/named_sources.exe',
                                execution], generation)
        view = json.loads(inspected.read_text())
        report = json.loads(reported.read_text())
        assert report['timing_intent'] == view, 'named report/inspect mismatch'
        assert view['status'] == 'completed' and view['verdict'] == 'unavailable'
        assert len(view['corners']) == 1
        assert view['requested_corners'] == view['executed_corners']
        audit = view['corners'][0]
        assert len(audit['resolved']['stages']) == 5
        native = audit['native_coverage']
        assert native['profile'] == 'opensta-2.7-native-state-v2'
        assert native['stored_exception_scope']['status'] == 'matched'
        assert native['stored_exception_scope']['relation_count'] == 6
        assert len(native['diagnostics']['categories']) == 7
        assert native['endpoints']['count'] == 12
        assert native['exhaustive_exception_effect'] == 'unavailable'
        record = json.loads(execution.read_text())
        expectation = record['timing_intent']
        publication = json.loads(Path(expectation['publication']).read_text())
        checkpoint_sources = [row for row in publication['sources']
                              if '/checkpoints/' in row['path']]
        assert checkpoint_sources, 'publication must retain checkpoint source hashes before STA'
        for row in checkpoint_sources:
            assert sha(Path(row['path'])) == row['sha256'], row['path']
        corner_dir = Path(expectation['directory']) / 'corners' / view['executed_corners'][0]
        minimum = (corner_dir / 'downstream_min.rpt').read_text()
        maximum = (corner_dir / 'downstream_max.rpt').read_text()
        assert minimum.count('Startpoint:') == 3 and maximum.count('Startpoint:') == 3
        assert minimum.count('slack (VIOLATED)') == 3, 'negative hold witnesses must remain visible'
        sources = json.loads(sources_file.read_text())
        assert sources, 'verified exact source inventory must be nonempty'
        for row in sources:
            assert sha(Path(row['path'])) == row['sha256'], row['path']
        assert before == inventory(execution.parent), 'public readers changed execution evidence'
        write_new(output / 'readonly.json', {'execution': str(execution), 'files': before,
                  'unchanged': True, 'inspect_sha256': sha(inspected)})
        write_new(output / 'acceptance.json', {
            'status': 'accepted_bounded_named_synthesis', 'execution': str(execution),
            'provider_receipt_sha256': sha(generation / 'receipt.json'),
            'report_inspect_equal': True, 'stages': 5, 'stored_relations': 6,
            'diagnostic_categories': 7, 'endpoints': 12, 'executed_corners': view['executed_corners'],
            'negative_hold_witnesses': 3, 'checkpoint_sources': checkpoint_sources,
            'verified_sources': len(sources), 'source_inventory_sha256': sha(sources_file),
            'closure_scope': 'path_bound', 'timing_closure': 'not_established',
            'exhaustive_exception_effect': 'unavailable'})


if __name__ == '__main__':
    main()
