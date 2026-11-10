#!/usr/bin/env python3
"""Targeted native-v2 review regressions over real native output; no local reader."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from pt7c_probe import ROOT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--controls', required=True)
    p.add_argument('--resolution', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--attempt', required=True)
    a = p.parse_args()
    output = ROOT / 'acceptance/pt7c' / a.attempt
    output.mkdir(exist_ok=False)
    top = json.loads(a.manifest.read_text())['top_module']
    cases = {
        'wrong-top': 'native current_design differs from manifest top',
        'missing-top': 'missing leading native current_design',
        'repeated-top': 'repeated/ambiguous current_design selection',
        'late-top': 'missing leading native current_design',
        'continued-comment': 'continued native SDC comment is unsupported',
        'category-reassignment': 'native check report differs from diagnostic groups',
        'reserved-marker': 'diagnostic contains reserved marker line',
        'legacy-v1': 'unsupported legacy native profile 1',
        'undelimited-raw': 'native check report differs from diagnostic groups',
    }
    summary = {}
    for name, diagnostic in cases.items():
        source = ROOT / 'acceptance/pt7c' / (a.controls + ('-no-input-delay' if name in ('category-reassignment', 'reserved-marker') else '-baseline'))
        directory = output / name
        shutil.copytree(source, directory)
        state = directory / 'native-state.sdc'
        text = state.read_text()
        select = 'current_design ' + top + '\n'
        assert text.count(select) == 1
        if name == 'wrong-top':
            state.write_text(text.replace(select, 'current_design unrelated_top\n', 1))
        elif name == 'missing-top':
            state.write_text(text.replace(select, '', 1))
        elif name == 'repeated-top':
            state.write_text(text + select)
        elif name == 'late-top':
            state.write_text(text.replace(select, '', 1) + select)
        elif name == 'continued-comment':
            state.write_text(text.replace('set_false_path\\\n', '# reviewed hidden exception\\\nset_false_path\\\n', 1))
        elif name == 'undelimited-raw':
            (directory / 'native-checks.rpt').write_text('HC_ASIC_NATIVE_CHECKS_COMPLETE\n')
        else:
            data = json.loads((directory / 'native-data.json').read_text())
            if name == 'legacy-v1':
                data.update(schema=1, profile='opensta-2.7-native-state-v1')
            elif name == 'reserved-marker':
                data['categories'][0]['groups'][0]['details'].append(' \tHC_ASIC_NATIVE_CATEGORY_END no_input_delay')
            else:
                assert data['categories'][1]['groups'] == []
                data['categories'][1]['groups'] = data['categories'][0]['groups']
                data['categories'][1]['group_count'] = data['categories'][0]['group_count']
                data['categories'][0].update(groups=[], group_count=0)
            (directory / 'native-data.json').write_text(json.dumps(data) + '\n')
        argv = [str(a.reader.resolve()), str(a.resolution.resolve()), str(directory), top]
        result = subprocess.run(argv, capture_output=True, timeout=30)
        (output / (name + '.stdout')).write_bytes(result.stdout)
        (output / (name + '.stderr')).write_bytes(result.stderr)
        summary[name] = dict(argv=argv, exit_code=result.returncode, diagnostic=diagnostic)
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        assert result.returncode == 2 and diagnostic in result.stderr.decode(), (name, result.stderr.decode())
    # Actual Tcl language oracle: no STA command implementation is substituted.
    # Inert calls establish that the reviewed comment hides the complete call.
    prelude = 'set calls 0\nproc get_ports {args} {return $args}\nproc get_pins {args} {return $args}\nproc set_false_path {args} {incr ::calls}\n'
    call = 'set_false_path\\\n -from [get_ports {ena}]\\\n -to [get_pins {_06_/D}]\n'
    for label, prefix, expected in (('ordinary', '# ordinary comment\n', '1'), ('continued', '# continued comment\\\n', '0')):
        script = output / (label + '.tcl')
        script.write_text(prelude + prefix + call + 'puts $calls\n')
        result = subprocess.run(['tclsh', str(script)], capture_output=True, text=True, timeout=30)
        (output / (label + '.stdout')).write_text(result.stdout)
        (output / (label + '.stderr')).write_text(result.stderr)
        assert result.returncode == 0 and result.stdout.strip() == expected


if __name__ == '__main__':
    main()
