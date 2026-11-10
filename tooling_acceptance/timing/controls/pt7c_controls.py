#!/usr/bin/env python3
"""Native counterfactual attempts on NEW native-state copies, never old SDC edits."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', required=True)
    p.add_argument('--producer', type=Path)
    p.add_argument('--reference', type=Path)
    p.add_argument('--view', type=Path)
    a = p.parse_args()
    source = (a.reference / 'native-state.sdc') if a.reference else ROOT / 'acceptance/pt7c/native-diagnostics-01/baseline.sdc'
    baseline = source.read_text()
    mapping = {}
    if a.view:
        view = json.loads(a.view.read_text())['corners'][0]
        stages = {row['id']: row for row in view['resolved']['stages']}
        mapping = dict(zip(('_4_', '_3_', '_2_', '_5_', '_6_'),
                           (stages[name]['cell'] for name in ('capture_first', 'capture_second', 'capture_third', 'control_first', 'control_second'))))
    def mapped(text):
        for old, new in mapping.items():
            text = text.replace(old, new)
        return text
    capture = mapped('set_false_path\\\n    -from [get_ports {ena}]\\\n    -to [get_pins {_4_/D}]')
    assert baseline.count(capture) == 1
    cases = {
        'baseline': baseline,
        'capture-removed': baseline.replace(capture, ''),
        'capture-broad': baseline.replace(capture, capture.replace(mapped('[get_pins {_4_/D}]'), mapped('[get_pins {_4_/D _3_/D}]'))),
        'capture-setup-only': baseline.replace(capture, capture.replace('set_false_path', 'set_false_path -setup')),
        'capture-hold-only': baseline.replace(capture, capture.replace('set_false_path', 'set_false_path -hold')),
        'capture-rise-only': baseline.replace(capture, capture.replace('-from ', '-rise_from ')),
        'extra-relation': baseline + mapped('\nset_false_path -from [get_ports {ui_in[1]}] -to [get_pins {_6_/D}]\n'),
        'masking': baseline + mapped('\nset_disable_timing -from CLK -to Q [get_cells {_4_}]\n'),
        'no-input-delay': '\n'.join(line for line in baseline.splitlines() if not line.startswith('set_input_delay')) + '\n',
        'no-output-delay': '\n'.join(line for line in baseline.splitlines() if not line.startswith('set_output_delay')) + '\n',
        'no-clock': '\n'.join(line for line in baseline.splitlines() if not line.startswith(('create_clock', 'set_clock_', 'set_input_delay', 'set_output_delay'))) + '\n',
    }
    summary = {}
    driver = ROOT / 'acceptance/pt7c' / (a.attempt + '-driver.tcl')
    with driver.open('x') as stream:
        stream.write(mapped((ROOT / 'tooling_acceptance/timing/basic/pt7c_state_control.tcl').read_text()))
    for name, text in cases.items():
        label = a.attempt + '-' + name
        state = ROOT / 'acceptance/pt7c' / (label + '.sdc')
        with state.open('x') as stream:
            stream.write(text)
        argv = [sys.executable, '-B', str(ROOT / 'tooling_acceptance/timing/controls/pt7c_probe.py'), '--label', label,
                '--script', str(driver), '--state', str(state)]
        if a.reference:
            argv += ['--reference', str(a.reference)]
        if a.producer:
            argv += ['--producer', str(a.producer)]
        result = subprocess.run(argv, cwd=ROOT)
        directory = ROOT / 'acceptance/pt7c' / label
        log = (directory / 'stdout.log').read_text() + (directory / 'stderr.log').read_text()
        assert result.returncode == 0 and 'PT7C_STATE_CONTROL_COMPLETE' in log and 'PROBE_FAILED' not in log, label
        has_capture = {mode: 'Startpoint: ena' in (directory / f'capture-{mode}.rpt').read_text() for mode in ('min', 'max')}
        if name == 'capture-removed':
            assert all(has_capture.values())
        if name == 'baseline':
            assert not any(has_capture.values())
        if name == 'capture-setup-only':
            assert has_capture == {'min': True, 'max': False}
        if name == 'capture-hold-only':
            assert has_capture == {'min': False, 'max': True}
        if name not in ('masking', 'no-clock'):
            assert 'slack (VIOLATED)' in (directory / 'downstream-min.rpt').read_text()
        summary[name] = {'exit_code': result.returncode, 'capture_witness_present': has_capture,
                         'scope': 'bounded exact external capture witness only; no exhaustive effect claim'}
    with (ROOT / 'acceptance/pt7c' / (a.attempt + '-summary.json')).open('x') as stream:
        json.dump(summary, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
