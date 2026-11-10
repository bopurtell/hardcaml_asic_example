#!/usr/bin/env python3
"""Early native qualification of provider-owned literal producer (before capture)."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from pt7c_probe import ROOT, digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', required=True)
    a = p.parse_args()
    source = ROOT.parent / 'hardcaml_asic/lib/elaboration/timing_coverage_tcl.ml'
    raw = source.read_text()
    prefix = 'let render () = {|'
    assert raw.count(prefix) == 1 and raw.endswith('|}\n')
    directory = ROOT / 'acceptance/pt7c' / a.attempt
    directory.mkdir(exist_ok=False)
    (directory / 'timing_coverage_tcl.ml').write_bytes(source.read_bytes())
    producer = directory / 'producer.tcl'
    producer.write_text(raw.split(prefix, 1)[1][:-3])
    (directory / 'source.json').write_text(json.dumps({'source': str(source), 'sha256': digest(source),
        'scope': 'early literal source qualification, not emitted bundle or final provider capture'}, indent=2) + '\n')
    subprocess.run([sys.executable, '-B', str(ROOT / 'tooling_acceptance/timing/controls/pt7c_controls.py'),
                    '--attempt', a.attempt, '--producer', str(producer)], check=True)


if __name__ == '__main__':
    main()
