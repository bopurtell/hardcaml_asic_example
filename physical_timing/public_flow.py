#!/usr/bin/env python3
"""Ordinary public flow consumer with retained input identities and attempt budget.

Call only after A/B handoff readiness. Native tools and the provider own timing
facts; this consumer checks public verdicts, identities and preservation.
"""
import argparse
import json
from pathlib import Path

from commands import ROOT, STORE, command, identity, inventory, sha, write_new


def checked_bundle(prepared, generation):
    value = json.loads(prepared.read_text())
    assert value['generation'] == str(generation)
    assert value['provider_receipt_sha256'] == sha(generation / 'receipt.json')
    assert value['bundle_inventory'] == inventory(Path(value['bundle']))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('run', 'inspect', 'postcheck', 'public'))
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--b-handoff', type=Path)
    parser.add_argument('--synthesis-inspection', type=Path)
    parser.add_argument('--repair-plan', type=Path)
    args = parser.parse_args()
    if not args.attempt or Path(args.attempt).name != args.attempt:
        parser.error('attempt must be a single directory name')
    generation = args.generation.resolve(strict=True)
    assert generation.is_relative_to(STORE / 'provider/generations')
    output = STORE / 'evidence' / args.attempt
    output.mkdir(parents=True, exist_ok=False)
    provider = generation / 'bin/hardcaml-asic-flow'

    def call(label, argv, timeout=1800, deadline=None):
        prefix = ['timeout', '--signal=TERM', '--kill-after=60s', str(deadline) + 's'] if deadline else []
        code = command(output / label, [*prefix, provider, *argv], generation=generation, timeout=timeout)
        write_new(output / (label + '-exit.json'), {'exit_code': code})
        return code

    if args.phase == 'run':
        if not args.prepared or not args.b_handoff:
            parser.error('run requires prepared input and B ready-handoff reference')
        prepared = checked_bundle(args.prepared, generation)
        write_new(output / 'admission-sources.json', {
            'prepared': identity(args.prepared), 'b_handoff': identity(args.b_handoff),
            'workers': {'flow': 6, 'container_cpus': 6, 'openroad': 6, 'klayout': 6,
                        'sta_corner_workers': 1, 'sta_native_threads': 1},
            'scope': 'caller reviewed A/B readiness; verify actual native execution receipts'})
        if prepared['stage'] == 'full':
            if not args.synthesis_inspection:
                parser.error('full requires actual all-corner synthesis inspection')
            baseline = json.loads(args.synthesis_inspection.read_text())
            assert baseline['status'] == 'completed'
            assert len(baseline['executed_corners']) == 3
            assert baseline['executed_corners'] == baseline['requested_corners']
            if (STORE / 'full-attempt-1.json').exists():
                if not args.repair_plan:
                    parser.error('second full attempt requires recorded diagnosed repair plan')
                ledger = STORE / 'full-attempt-2.json'
                plan = identity(args.repair_plan)
            else:
                ledger = STORE / 'full-attempt-1.json'
                plan = None
            write_new(ledger, {'attempt': args.attempt, 'prepared': identity(args.prepared),
                               'synthesis_inspection': identity(args.synthesis_inspection),
                               'repair_plan': plan})
        code = call('run', ['run', prepared['bundle'], '--stage', prepared['stage'],
                    '--support-tools', ROOT / '_flow_tools/tt', '--pdk-root', ROOT / '_flow_tools/pdk',
                    '--python', ROOT / '_flow_tools/.venv/bin/python', '--runs',
                    STORE / (prepared['stage'] + '-runs'), '--json'],
                    timeout=960 if prepared['stage'] == 'synthesis' else 3660,
                    deadline=900 if prepared['stage'] == 'synthesis' else 3600)
        assert prepared['bundle_inventory'] == inventory(Path(prepared['bundle']))
        write_new(output / 'bundle-preservation.json', {'unchanged': True})
        raise SystemExit(code)

    if not args.run:
        parser.error('this phase requires --run')
    run = args.run.resolve(strict=True)
    assert run.is_relative_to(STORE)
    if args.phase == 'postcheck':
        code = call('postcheck', ['postcheck', run, '--support-tools', ROOT / '_flow_tools/tt',
                    '--pdk-root', ROOT / '_flow_tools/pdk', '--precheck-python',
                    ROOT / '_flow_tools/.venv-precheck/bin/python', '--testbench',
                    ROOT / 'physical_timing/functional_tb.v', '--testbench-top',
                    'timing_physical_replay', '--timeout', '1800', '--json'], timeout=2160, deadline=2100)
        raise SystemExit(code)
    before = inventory(run)
    code = call('inspect', ['timing-intent-inspect', run, '--kind', 'coarse_run', '--json'])
    assert code in (0, 1)
    view = json.loads((output / 'inspect/stdout.log').read_text())
    if args.phase == 'inspect':
        write_new(output / 'read-only.json', {'unchanged': before == inventory(run),
                                             'files': len(before)})
        assert before == inventory(run)
        print(json.dumps({'inspection': str(output / 'inspect/stdout.log'),
                          'status': view['status'], 'all_corner_timing_goal': view.get('all_corner_timing_goal')}))
        return
    assert call('collect', ['collect', run, '--stdout', '--json']) == 0
    assert call('report', ['report', run, '--json']) in (0, 1)
    report = json.loads((output / 'report/stdout.log').read_text())
    assert report['timing_intent'] == view
    assert call('archive-list', ['archive', run, '--list']) == 0
    assert call('archive', ['archive', run, '--output', output / 'archive-output', '--json']) == 0
    # collect may create/update results; all pre-existing implementation sources
    # other than that public collection cache must remain byte-identical.
    changed = [name for name, digest in before.items() if name != 'results.json'
               and (not (run / name).is_file() or sha(run / name) != digest)]
    write_new(output / 'preservation.json', {'files': len(before), 'changed': changed})
    assert not changed


if __name__ == '__main__':
    main()
