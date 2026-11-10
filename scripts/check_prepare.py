#!/usr/bin/env python3
"""Real project CLIs + installed preparation reader; no build, PDK or EDA calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zlib


def fixture_repository(root):
    """Independent, empty Git baseline without invoking Git mutation commands.

    Source-observation fixtures must also work in copied Workbench projects,
    where there is no parent checkout metadata to discover.
    """
    metadata = root / '.git'
    (metadata / 'objects').mkdir(parents=True)
    (metadata / 'refs/heads').mkdir(parents=True)

    def obj(kind, data):
        raw = kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data
        identity = hashlib.sha1(raw).hexdigest()
        path = metadata / 'objects' / identity[:2] / identity[2:]
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(zlib.compress(raw))
        return identity

    tree = obj('tree', b'')
    commit = obj('commit', ('tree ' + tree + '\nauthor Fixture <fixture@example.test> 1 +0000\n'
        'committer Fixture <fixture@example.test> 1 +0000\n\nPreparation fixture\n').encode())
    (metadata / 'HEAD').write_text('ref: refs/heads/fixture\n')
    (metadata / 'refs/heads/fixture').write_text(commit + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--memory', type=Path, required=True)
    p.add_argument('--fifo', type=Path, required=True)
    p.add_argument('--provider', type=Path, required=True)
    p.add_argument('--provider-receipt', type=Path,
                   help='installed generation receipt (default: provider parent prefix/receipt.json)')
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--historical-dir', type=Path,
                   help='Original v1 archive (default SOURCE/acceptance/preparation/capture)')
    a = p.parse_args()
    memory, fifo, provider, root = (x.resolve() for x in
                                  (a.memory, a.fifo, a.provider, a.source_root))
    output = a.output_dir.resolve() if a.output_dir else None
    if output:
        output.mkdir(parents=True, exist_ok=False)
    checks, launches = [], []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    def run(argv, code=0, timeout=30):
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=timeout)
        assert result.returncode == code, (argv, result.returncode, result.stderr, result.stdout)
        return result.stdout

    def inspect(attempt, *extra, code=0):
        text = run([provider, 'preparation-inspect', attempt, '--json', *extra], code)
        return json.loads(text) if code == 0 else text

    # All mutable evidence belongs to this source root's private scratch space.
    with tempfile.TemporaryDirectory(prefix='prepare-check-', dir=root / '.dev') as tmp:
        work = Path(tmp)
        store = work / 'attempts'

        def launch(label, executable=memory, selection='exact', operation='synthesis',
                   depth=256, source=root, code=0, destination=store):
            argv = [executable, 'prepare', '--source-root', source,
                    '--results-root', destination, '--json']
            if executable == memory:
                argv += ['--selection', selection, '--operation', operation, '--depth', str(depth)]
            proc = subprocess.Popen(list(map(str, argv)), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            first = proc.stdout.readline()
            allocation = json.loads(first)
            attempt = Path(allocation['attempt'])
            check(label + ': allocation first, persisted', allocation['event'] == 'allocated'
                  and (attempt / 'operation.json').is_file())
            remaining, stderr = proc.communicate()
            assert proc.returncode == code, (label, proc.returncode, stderr, remaining)
            terminal, = [json.loads(line) for line in remaining.splitlines()]
            check(label + ': terminal follows allocation', terminal['event'] == 'terminal'
                  and terminal['attempt'] == str(attempt))
            view = inspect(attempt)
            check(label + ': retained terminal agrees', view['operation'] == terminal['record'])
            check(label + ': status', view['operation']['status'] == ('completed' if code == 0 else 'failed'))
            launches.append(dict(case=label, exit_code=proc.returncode,
                                 events=[allocation, terminal]))
            return attempt, view['preparation']

        saved = {}
        for operation in ('synthesis', 'hardening'):
            for selection, depth, reason in (('flops', 256, 'explicit_flops'),
                                              ('exact', 256, 'exact_mapping'),
                                              ('fallback', 128, 'flop_fallback')):
                label = selection + '-' + operation
                attempt, prep = launch(label, selection=selection, operation=operation, depth=depth)
                r, = prep['resources']['resources']
                check(label + ': program policy/reason/role', r['id']['display'] == 'program'
                      and r['policy'] == {'kind': 'instance', 'resource': 'program'}
                      and r['selection']['reason']['kind'] == reason
                      and r['elaborated_as'] == 'selected_implementation')
                check(label + ': explicit coverage', prep['coverage'] == dict(
                    declared_sources=True, compiled_source_proven=False, p6_source_stamp=False,
                    collateral_files_verified=False, measured_evidence=False))
                if selection == 'exact':
                    check(label + ': macro linkage/references',
                          r['selection']['implementation']['name'] == 'RM_IHPSG13_1P_256x16_c2_bm_bist'
                          and r['actual_instances']['status'] == 'rtl_verified'
                          and len(r['collateral']) > 0
                          and all(c['verification'] == 'unresolved_reference' for c in r['collateral'])
                          and r['physical_intent']['status'] == 'resolved_intent')
                saved[label] = (attempt, prep)

        bad, failure = launch('unsupported-exact-128', depth=128, code=1)
        check('failed attempt has no inventory', failure is None
              and not (bad / 'resources.json').exists()
              and 'fallback is not permitted' in json.dumps(inspect(bad)).lower())
        retry, _ = launch('unsupported-retry', depth=128, code=1)
        check('retry gets fresh attempt', retry != bad)
        missing, _ = launch('source-unavailable', source=work / 'absent', code=1)
        check('source failure retained', inspect(missing)['operation']['diagnostic'] is not None)
        fifo_attempt, fifo_prep = launch('fifo-zero-resources', executable=fifo)
        check('FIFO genuine successful empty inventory', fifo_prep['resources']['resources'] == [])

        for executable, arguments in (
                (memory, ['--selection', 'exact', '--operation', 'synthesis']), (fifo, [])):
            live = json.loads(run([executable, 'resources', *arguments, '--json']))
            simulation = json.loads(run([executable, 'resources', *arguments, '--simulation', '--json']))
            check(executable.name + ': explicit simulation mode', live['mode'] == 'implementation'
                  and live['scope'] == 'resolved' and simulation['mode'] == 'simulation'
                  and simulation['scope'] == 'elaborated')
            if executable == memory:
                r, = simulation['resources']
                check('simulation selected macro is behavioral',
                      r['selection']['implementation']['kind'] == 'macro'
                      and r['elaborated_as'] == 'behavioral_model'
                      and r['actual_instances']['status'] == 'not_applicable')

        # Inventory gates: every project-owned constructor/CLI dependency is observed.
        for prep, required in (
                (saved['exact-synthesis'][1], {'asics/program_memory/project/dune',
                    'asics/program_memory/project/program_memory.ml', 'asics/program_memory/project/memory_cli.ml'}),
                (fifo_prep, {'asics/fifo_demo/cli/dune', 'asics/fifo_demo/cli/project.ml',
                    'asics/fifo_demo/project/project.ml', 'asics/fifo_demo/project/fifo_asic.ml',
                    'asics/fifo_demo/rtl/tt_wrapper.ml', 'ip/controlled_fifo/rtl/controlled_fifo.ml'})):
            paths = {x['path'] for x in prep['source']['inputs']}
            check('source inventory gate: ' + prep['resources']['project'], required <= paths)

        fixture = work / 'source'
        fixture.mkdir()
        for item in saved['exact-synthesis'][1]['source']['inputs']:
            path = fixture / item['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / item['path'], path)
        fixture_repository(fixture)

        def preview(operation='synthesis', selection='exact', depth=256):
            return json.loads(run([memory, 'preview', '--source-root', fixture,
                                   '--selection', selection, '--operation', operation,
                                   '--depth', str(depth), '--json']))

        before_paths = sorted(str(x.relative_to(work)) for x in work.rglob('*'))
        base = preview()
        check('deterministic nonpublishing preparation', preview() == base
              and before_paths == sorted(str(x.relative_to(work)) for x in work.rglob('*')))
        config = preview(operation='hardening')
        check('config identity changes independently of source/circuit',
              config['configuration_identity'] != base['configuration_identity']
              and config['source_identity'] == base['source_identity']
              and config['circuit_identity'] == base['circuit_identity'])
        small, large = preview(selection='flops', depth=128), preview(selection='flops')
        check('actual circuit identity changes', small['circuit_identity'] != large['circuit_identity']
              and small['source_identity'] == large['source_identity'])
        readme = fixture / 'asics/program_memory/README.md'
        readme.write_bytes(readme.read_bytes() + b'\nPreparation source observation fixture.\n')
        changed = preview()
        check('observed source identity changes independently', changed['source_identity'] != base['source_identity']
              and changed['identity'] != base['identity']
              and changed['configuration_identity'] == base['configuration_identity']
              and changed['circuit_identity'] == base['circuit_identity'])
        historic, prep = launch('historical-fixture', source=fixture)
        shutil.rmtree(fixture)
        check('historical source unavailable', inspect(historic)['preparation'] == prep)
        for current, state in ((prep['identity'], 'matches'), (base['identity'], 'differs')):
            check('comparison ' + state, inspect(historic, '--current-identity', current)['comparison']['state'] == state)
        check('failed comparison unavailable', inspect(bad, '--current-identity', prep['identity'])['comparison']['state'] == 'unavailable')

        corrupt = work / 'corrupt'
        shutil.copytree(historic, corrupt)
        payload = corrupt / 'resources.json'
        payload.write_bytes(payload.read_bytes() + b' ')
        inspect(corrupt, code=2)
        checks.append('corrupt payload refused by installed reader')
        refused = work / 'not-a-directory'
        refused.write_text('preserve\n')
        result = subprocess.run([str(memory), 'prepare', '--selection', 'exact', '--operation',
                                 'synthesis', '--source-root', str(root), '--results-root', str(refused), '--json'],
                                capture_output=True, text=True)
        check('store refusal: no allocation, no overwrite', result.returncode != 0
              and not result.stdout and refused.read_text() == 'preserve\n')

        # Exercise the installed reader's file-type boundary, not a local decoder.
        for leaf in ('operation.json', 'resources.json'):
            nonregular = work / ('fifo-' + leaf)
            shutil.copytree(historic, nonregular)
            artifact = nonregular / leaf
            artifact.unlink()
            os.mkfifo(artifact)
            run([provider, 'preparation-inspect', nonregular, '--json'], code=2, timeout=5)
            checks.append('named-pipe evidence rejected without blocking: ' + leaf)

        check('current descriptor v2, outer schema1', all(
            launch['events'][1]['record']['schema_version'] == 1
            and launch['events'][1]['record']['operation']['schema_version'] == 2
            and launch['events'][1]['record']['operation']['phases'].index('snapshot')
            < launch['events'][1]['record']['operation']['phases'].index('source_after')
            for launch in launches))

        historical = (a.historical_dir or root / 'acceptance/preparation/capture').resolve()
        compatibility = []
        if historical.is_dir():
            def fingerprint():
                return {str(path.relative_to(historical)): dict(
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    bytes=path.stat().st_size, mtime_ns=path.stat().st_mtime_ns)
                    for path in sorted(historical.rglob('*')) if path.is_file()}

            before = fingerprint()
            for label in ('exact-synthesis', 'unsupported-exact-128', 'fifo-zero-resources'):
                attempt = historical / label
                view = inspect(attempt)
                operation = json.loads((attempt / 'operation.json').read_text())
                check('v1 historical descriptor preserved: ' + label,
                      view['operation'] == operation and operation['schema_version'] == 1
                      and operation['operation']['schema_version'] == 1)
                comparisons = []
                if view['preparation'] is not None:
                    identity = view['preparation']['identity']
                    other = (saved['exact-hardening'][1] if label == 'exact-synthesis'
                             else saved['exact-synthesis'][1])['identity']
                    assert identity != other
                    for current, state in ((identity, 'matches'), (other, 'differs')):
                        comparison = inspect(attempt, '--current-identity', current)['comparison']
                        check('v1 explicit comparison ' + label + ': ' + state,
                              comparison['state'] == state)
                        comparisons.append(comparison)
                else:
                    comparison = inspect(attempt, '--current-identity',
                                         saved['exact-synthesis'][1]['identity'])['comparison']
                    check('v1 failure comparison unavailable', comparison['state'] == 'unavailable')
                    comparisons.append(comparison)
                compatibility.append(dict(case=label, operation=operation, comparisons=comparisons))
            after = fingerprint()
            check('original v1 archive unchanged: hashes/lengths/mtimes/paths', before == after)
            compatibility = dict(attempts=compatibility, before=before, after=after)
        elif a.historical_dir:
            raise AssertionError('explicit historical archive is missing: ' + str(historical))

        if output:
            for label, attempt in (('exact-synthesis', saved['exact-synthesis'][0]),
                                   ('unsupported-exact-128', bad), ('fifo-zero-resources', fifo_attempt)):
                shutil.copytree(attempt, output / label)
                inspect(output / label)
            (output / 'launches.json').write_text(json.dumps(launches, indent=2) + '\n')
            (output / 'historical-compatibility.json').write_text(json.dumps(compatibility, indent=2) + '\n')
            receipt = a.provider_receipt or provider.parent.parent / 'receipt.json'
            report = dict(checks=checks, count=len(checks), provider=json.loads(run([provider, '--version', '--json'])),
                          capture=json.loads(receipt.read_text()),
                          executables={str(x): hashlib.sha256(x.read_bytes()).hexdigest() for x in (memory, fifo)},
                          coverage='Observed declared sources; compiled source consistency is not proven. No PDK/EDA.')
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f'PASS: {len(checks)} preparation checks; real memory/FIFO CLIs and installed historical reader')


if __name__ == '__main__':
    main()
