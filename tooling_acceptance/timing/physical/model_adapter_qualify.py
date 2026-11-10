#!/usr/bin/env python3
"""Actual Icarus qualification of the captured production cell-body adapter.

This is an adapter diagnostic using real synthesis input, not a full-run or final
postcheck record. No Hardening manifest, final-netlist path or native evidence is
invented to bypass the ordinary postcheck admission boundary.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

from commands import ROOT, STORE, command, identity, sha, write_new

PROFILE = 'cmos5l_physical_timing_used_cells_v1'
FLOPS = ['sg13cmos5l_dfrbpq_1', 'sg13cmos5l_dfrbpq_2',
         'sg13cmos5l_dfrbp_1', 'sg13cmos5l_dfrbp_2']
CELLS = FLOPS + ['sg13cmos5l_buf_' + str(i) for i in (1, 2, 4, 8, 16)] + [
    'sg13cmos5l_dlygate4sd' + str(i) + '_1' for i in (1, 2, 3)] + [
    'sg13cmos5l_and2_1', 'sg13cmos5l_and2_2', 'sg13cmos5l_tiehi', 'sg13cmos5l_tielo']


def derive(output, helper, vendor, udp, netlist, preflight):
    refs = {row['path']: row['sha256'] for row in json.loads(preflight.read_text())['references'] if 'path' in row}
    before = [identity(p) for p in (helper, vendor, udp, netlist, preflight)]
    assert refs[str(vendor)] == sha(vendor) and refs[str(udp)] == sha(udp)
    spec = importlib.util.spec_from_file_location('captured_production_physical_runtime', helper)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    text = vendor.read_text()
    bodies, modules = [], {}
    for name in CELLS:
        matches = re.findall(r'\bmodule\s+' + re.escape(name) + r'\s*\(.*?\bendmodule', text, re.S)
        assert len(matches) == 1, name
        # All functional transformation belongs to the captured production helper.
        body, delayed = runtime.reviewed_timing_cell(name, matches[0])
        bodies.append(body)
        modules[name] = {'vendor_module_sha256': hashlib.sha256(matches[0].encode()).hexdigest(),
                         'functional_module_sha256': hashlib.sha256(body.encode()).hexdigest(),
                         'adapted_delayed_pins': delayed}
    (output / 'adapter-functional.v').write_text('`timescale 1ns/1ps\n' + '\n'.join(bodies))
    (output / 'vendor-unchanged.v').write_bytes(vendor.read_bytes())
    (output / 'udp-unchanged.v').write_bytes(udp.read_bytes())
    original = netlist.read_text()
    assert original.count('sg13cmos5l_dfrbpq_1 ') == 5
    for master in FLOPS:
        # Disposable sizing/function diagnostics. The actual mapped netlist is
        # unchanged, and no variant is labeled a completed implementation.
        (output / (master + '.v')).write_text(original.replace('sg13cmos5l_dfrbpq_1 ', master + ' '))
    assert before == [identity(p) for p in (helper, vendor, udp, netlist, preflight)]
    write_new(output / 'adapter-inventory.json', {'scope': 'production_reviewed_cell_adapter_diagnostic',
        'profile_under_test': PROFILE, 'full_postcheck_admission_exercised': False,
        'inputs': before, 'modules': modules, 'derived_view': identity(output / 'adapter-functional.v'),
        'vendor_copy_identical': sha(output / 'vendor-unchanged.v') == sha(vendor),
        'udp_copy_identical': sha(output / 'udp-unchanged.v') == sha(udp),
        'claim': 'zero_delay_digital_functional_only_not_vendor_timing_or_sdf_conformance'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', required=True)
    p.add_argument('--generation', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--derive-only', action='store_true')
    a = p.parse_args()
    assert a.attempt and Path(a.attempt).name == a.attempt
    generation = a.generation.resolve(strict=True)
    run = a.run.resolve(strict=True)
    assert generation.is_relative_to(STORE / 'provider/generations') and run.is_relative_to(STORE)
    output = STORE / 'evidence' / a.attempt
    helper = generation / 'lib/hardcaml_asic/flow/hardcaml_asic_flow/physical_runtime.py'
    cells = ROOT / '_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/verilog'
    vendor, udp = cells / 'sg13cmos5l_stdcell.v', cells / 'sg13cmos5l_udp.v'
    view = json.loads((run / 'timing-intent/runtime-result.json').read_text())
    netlist = run / view['implementation']['netlist']['path']
    preflight = run / 'preflight.json'
    tb = ROOT / 'tooling_acceptance/timing/physical/functional_tb.v'
    inputs = [helper, vendor, udp, netlist, preflight, tb, Path(__file__).resolve()]
    if a.derive_only:
        derive(output, helper, vendor, udp, netlist, preflight)
        return
    output.mkdir(parents=True, exist_ok=False)
    cpu = str(min(os.sched_getaffinity(0)))
    version = command(output / 'capability', [generation / 'bin/hardcaml-asic-flow', '--version', '--json'], generation=generation)
    assert version == 0
    capability = json.loads((output / 'capability/stdout.log').read_text())
    assert capability['cli_contract']['capabilities']['timing_intent_physical2']['functional_postcheck'] == PROFILE
    code = command(output / 'derive', ['taskset', '-c', cpu, sys.executable, '-B', Path(__file__).resolve(),
                   '--attempt', a.attempt, '--generation', generation, '--run', run, '--derive-only'],
                   generation=generation, inputs=inputs, timeout=60)
    assert code == 0, 'production adapter failed; retained derive log'
    inventory = output / 'adapter-inventory.json'
    model = output / 'adapter-functional.v'
    udp_copy = output / 'udp-unchanged.v'
    results = []
    for master in FLOPS:
        diagnostic = output / (master + '.v')
        executable = output / (master + '.vvp')
        sources = [*inputs, inventory, model, udp_copy, diagnostic]
        code = command(output / (master + '-compile'), ['taskset', '-c', cpu, 'iverilog', '-g2012',
                       '-DFUNCTIONAL', '-DSIM', '-s', 'timing_physical_replay', '-o', executable,
                       model, udp_copy, diagnostic, tb], inputs=sources, timeout=60)
        assert code == 0, master
        for label, arguments, expected in [('positive', [], 0), ('negative', ['+negative'], 1)]:
            directory = output / (master + '-' + label)
            code = command(directory, ['taskset', '-c', cpu, 'vvp', executable, *arguments],
                           inputs=[*sources, executable], timeout=60)
            raw = (directory / 'stdout.log').read_text()
            assert code == expected, (master, label, code)
            assert ('checks=512' if label == 'positive' else 'functional mismatch check=20') in raw
            results.append({'master': master, 'control': label, 'exit_code': code,
                            'command': identity(directory / 'command.json')})
    write_new(output / 'summary.json', {'status': 'passed', 'profile_under_test': PROFILE,
        'scope': 'captured_production_reviewed_cell_adapter_actual_icarus',
        'full_postcheck_admission_exercised': False, 'final_netlist_acceptance': False,
        'diagnostic_variants': 4, 'positive_observations_per_variant': 512,
        'native_workers': 1, 'host_cpu_affinity': [int(cpu)], 'results': results,
        'adapter_inventory': identity(inventory)})
    print(json.dumps({'status': 'passed', 'profile': PROFILE, 'positive_variants': 4, 'negative_controls': 4}))


if __name__ == '__main__':
    main()
