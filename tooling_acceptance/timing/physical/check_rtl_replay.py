#!/usr/bin/env python3
"""Check positive and negative replay against fresh emitted timing RTL."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    sources = [bundle / (source if isinstance(source, str) else source['path'])
               for source in manifest['synthesis_sources']]
    bench = Path(__file__).with_name('functional_tb.v')
    with tempfile.TemporaryDirectory(prefix='timing-rtl-replay-') as directory:
        exe = Path(directory) / 'replay.vvp'
        subprocess.run(['iverilog', '-g2012', '-DFUNCTIONAL', '-DSIM', '-s',
                        'timing_physical_replay', '-o', exe, bench, *sources], check=True)
        positive = subprocess.run(['vvp', exe], check=True, capture_output=True, text=True, timeout=60)
        negative = subprocess.run(['vvp', exe, '+negative'], capture_output=True, text=True, timeout=60)
        if ('checks=512' not in positive.stdout or negative.returncode == 0
                or 'functional mismatch check=20' not in negative.stdout):
            raise RuntimeError(f'Unexpected replay results: {positive.stdout}\n{negative.stdout}\n{negative.stderr}')
    print('PASS 512 RTL observations and corrupted-oracle rejection')


if __name__ == '__main__':
    main()
