"""Exercise compiled consumer routes, resource selection and actual bundle publication."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

EXE = Path(sys.argv[1]).resolve(strict=True)
ROOT = Path(subprocess.check_output(['git', '-C', sys.argv[2], 'rev-parse', '--show-toplevel'], text=True).strip())


def cli(*args, ok=True):
    p = subprocess.run([EXE, *args, '--json'], cwd=ROOT, text=True, capture_output=True)
    if not ok:
        assert p.returncode and not p.stdout, (args, p)
        return p.stderr
    assert p.returncode == 0, (args, p.stderr)
    return json.loads(p.stdout)


with tempfile.TemporaryDirectory(prefix='chip-routing-') as directory:
    store = Path(directory) / 'store'
    catalog = cli('chip', 'list')
    chips = {c['id']: c for c in catalog['chips']}
    assert catalog['schema_version'] == 1 and catalog['default_chip'] == 'fifo_demo'
    assert set(chips) == {'fifo_demo', 'program_memory', 'sram_budget'}
    assert all(c['default_variant'] in {v['id'] for v in c['variants']} for c in chips.values())
    baseline = cli('flow', 'plan', '--endpoint', 'synthesis')
    assert baseline == cli('flow', 'plan', '--chip', 'fifo_demo', '--variant', 'default', '--endpoint', 'synthesis')
    assert json.loads(baseline['bundle_manifest'])['top_module'] == 'tt_um_controlled_fifo'

    target = ['--chip', 'program_memory', '--variant', 'default']
    flow = cli('flow', 'list', *target)['declaration']
    assert flow['default'] == {'flow': 'stock256-r0', 'profile': 'qualification'}
    entry = cli('flow', 'describe', '--flow', 'stock256-r0', *target)['entry']
    assert entry == flow['entries'][0]
    assert entry['methodology']['endpoints'] == ['synthesis', 'floorplan', 'placement', 'cts', 'routing', 'timing']
    sel = [*target, '--endpoint', 'timing']
    plan = cli('flow', 'plan', *sel)
    cli('flow', 'emit', *sel, '--results-root', store, '--expected-plan-identity', baseline['plan_identity'], ok=False)
    cli('flow', 'run', *sel, '--results-root', store, '--expected-plan-identity', baseline['plan_identity'], ok=False)
    cli('flow', 'plan', *target, '--endpoint', 'signoff', ok=False)
    assert not store.exists()
    emitted = cli('flow', 'emit', *sel, '--results-root', store, '--expected-plan-identity', plan['plan_identity'])
    manifest = json.loads((Path(emitted['output_dir']) / 'manifest.json').read_text())
    assert emitted['plan'] == plan and manifest == json.loads(plan['bundle_manifest'])
    assert manifest['top_module'] == 'tt_um_program_memory' and manifest['macro_contract']['schema_version'] == 2
    assert 'asics/program_memory/project/program_memory.ml' in {f['path'] for f in manifest['source_inputs']}

    budgets = chips['sram_budget']
    assert budgets['default_variant'] == 'two_slot' and {v['id'] for v in budgets['variants']} == {'two_slot', 'three_slot'}
    ids = []
    for variant, slots in [('two_slot', 2), ('three_slot', 3)]:
        target = ['--chip', 'sram_budget', '--variant', variant]
        entry = cli('flow', 'describe', *target, '--flow', 'standard')['entry']
        assert entry['methodology']['endpoints'] == ['synthesis']
        assert cli('flow', 'list', *target)['declaration']['entries'] == [entry]
        cli('flow', 'plan', *target, '--endpoint', 'floorplan', ok=False)
        route = [*target, '--flow', 'standard', '--profile', 'balanced', '--endpoint', 'synthesis']
        plan = cli('flow', 'plan', *route)
        assert plan['project_name'] == 'sram_budget' and plan['methodology']['recipe']['stages'] == ['synthesis']
        receipt = cli('flow', 'emit', *route, '--results-root', store, '--expected-plan-identity', plan['plan_identity'])
        assert receipt['plan'] == plan
        ids.append(plan['plan_identity'])
        bundle = Path(receipt['output_dir'])
        m = json.loads((bundle / 'manifest.json').read_text())
        assert m == json.loads(plan['bundle_manifest'])
        assert m['identity'] == receipt['bundle_identity'] and m['top_module'] == 'tt_um_sram_budget'
        assert m['hardware_variant']['assignments'] == {'bank_variant': variant}
        # Capture the provider boundary without requiring synthesis tools.
        provider = Path(directory) / 'provider'
        provider.write_text("#!/usr/bin/env python3\nimport sys,json\nfrom pathlib import Path\n"
            "if sys.argv[1]=='--version': print(json.dumps({'cli_contract':{'version':4,'capabilities':"
            "{'namedflow1':True,'sram_synthesis1':True}}}))\n"
            "else:\n assert sys.argv[1]=='stages'\n print(Path(sys.argv[sys.argv.index('--methodology-plan')+1]).read_text())\n")
        provider.chmod(0o755)
        run = ['run', *route, '--provider', provider, '--results-root', store, '--expected-plan-identity', plan['plan_identity']]
        assert cli('flow', *run) == plan
        provider.write_text(provider.read_text().replace("'sram_synthesis1':True", "'sram_synthesis1':False"))
        assert 'sram_synthesis1' in cli('flow', *run, ok=False)
        assert {f['path'] for f in m['source_inputs']} >= {'asics/sram_budget/sram_budget.ml', 'asics/fifo_demo/cli/project.ml'}
        assert not any('fifo_demo/project/' in f['path'] for f in m['source_inputs'])
        rows = {r['id']['display']: r for r in m['resource_snapshot']['resources']}
        assert set(rows) == {'bank0', 'bank1', 'bank2'}
        assert (bundle / 'src/tt_um_sram_budget.v').read_text().count('RM_IHPSG13_1P_256x16_c2_bm_bist') == slots
        assert (rows['bank2']['selection']['reason']['kind'] == 'budget_exhausted') == (slots == 2)
    assert ids[0] != ids[1]
    assert 'stale' in cli('flow', 'emit', *route, '--results-root', store, '--expected-plan-identity', ids[0], ok=False)
    for command in ['list', 'describe', 'plan', 'emit', 'run']:
        assert 'Unknown variant' in cli('flow', command, '--chip', 'fifo_demo', '--variant', 'three_slot', ok=False)
        assert 'Unknown chip' in cli('flow', command, '--chip', 'missing', ok=False)
    cli('emit', '--variant', 'three_slot', ok=False)
    cli('emit', '--chip', 'fifo_demo', '--chip', 'sram_budget', ok=False)
