#!/usr/bin/env python3
"""Historical native-v1 truth versus explicit current-reader unsupported status."""
import argparse
import json
from pathlib import Path
import subprocess

from pt7c_probe import ROOT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', required=True)
    a = p.parse_args()
    output = ROOT / 'acceptance/pt7c' / a.attempt
    output.mkdir(exist_ok=False)
    current = (ROOT / '.dev/asic-pt7c/provider/current/bin/hardcaml-asic-flow').resolve()
    historical = ROOT / '.dev/asic-pt7c/provider/generations/df6eaa70174c44d280bcb9c724917121/bin/hardcaml-asic-flow'
    run = ROOT / '.dev/asic-pt7c/runs/20261028T173519344419Z_48ac4fc8'
    corner = run / 'timing-intent/corners/nom_typ_1p20V_25C'
    summary = {}
    cases = (
        ('current-v1-coarse', current, [str(run), '--kind', 'coarse_run'], 2, 'unsupported legacy/native producer declaration'),
        ('current-v1-inner', current, [str(corner)], 2, 'unsupported legacy native producer profile'),
        ('historical-v1-coarse', historical, [str(run), '--kind', 'coarse_run'], 1, None),
        ('original-schema1', current, [str(ROOT / 'acceptance/timing/sta-scalar-r3')], 1, None),
    )
    for label, provider, arguments, expected, diagnostic in cases:
        argv = [str(provider), 'timing-intent-inspect', *arguments, '--json']
        result = subprocess.run(argv, capture_output=True, timeout=120)
        (output / (label + '.stdout')).write_bytes(result.stdout)
        (output / (label + '.stderr')).write_bytes(result.stderr)
        summary[label] = dict(argv=argv, exit_code=result.returncode, diagnostic=diagnostic)
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        assert result.returncode == expected, (label, result.stderr.decode())
        if diagnostic:
            assert diagnostic in result.stderr.decode()
        elif label == 'historical-v1-coarse':
            view = json.loads(result.stdout)
            assert view['status'] == 'completed'
            assert view == json.loads((ROOT / 'acceptance/pt7c/public-02/inspect/stdout.log').read_text())
        else:
            assert json.loads(result.stdout)['verdict'] == 'unavailable'
    assert json.loads((run / 'run.json').read_text())['status'] == 'completed'


if __name__ == '__main__':
    main()
