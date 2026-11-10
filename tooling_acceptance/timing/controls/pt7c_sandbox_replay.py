#!/usr/bin/env python3
"""Replay restored public evidence with original example/PDK/provider source hidden."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', required=True)
    p.add_argument('--restored', type=Path, required=True)
    p.add_argument('--public', type=Path, required=True)
    a = p.parse_args()
    generation = (ROOT / '.dev/asic-pt7c/provider/current').resolve(strict=True)
    restored = a.restored.resolve(strict=True)
    output = ROOT / 'acceptance/pt7c' / a.attempt
    output.mkdir(exist_ok=False)
    # Mount changes exist only in the child namespace. Host sources remain intact.
    prefix = ['bwrap', '--ro-bind', '/', '/', '--unshare-user', '--unshare-pid',
              '--unshare-net', '--die-with-parent', '--tmpfs', str(ROOT),
              '--tmpfs', str(ROOT.parent / 'hardcaml_asic'),
              '--ro-bind', str(generation), str(generation),
              '--ro-bind', str(restored), str(restored), '--chdir', '/tmp', '--']
    provider = str(generation / 'bin/hardcaml-asic-flow')
    summary = {}
    for label, arguments, expected in (
            ('inspect', ['timing-intent-inspect', str(restored), '--kind', 'coarse_run', '--json'], 1),
            ('collect', ['collect', str(restored), '--stdout', '--json'], 0),
            ('report', ['report', str(restored), '--json'], 0)):
        argv = prefix + [provider, *arguments]
        result = subprocess.run(argv, capture_output=True, timeout=120)
        (output / (label + '.stdout')).write_bytes(result.stdout)
        (output / (label + '.stderr')).write_bytes(result.stderr)
        summary[label] = {'argv': argv, 'exit_code': result.returncode}
        (output / 'receipt.json').write_text(json.dumps(summary, indent=2) + '\n')
        assert result.returncode == expected, (label, result.returncode, result.stderr.decode())
        if label == 'inspect':
            baseline = json.loads((a.public / 'inspect/stdout.log').read_text())
            assert json.loads(result.stdout) == baseline
        else:
            baseline = json.loads((a.public / 'collect/stdout.log').read_text())
            assert json.loads(result.stdout) == baseline


if __name__ == '__main__':
    main()
