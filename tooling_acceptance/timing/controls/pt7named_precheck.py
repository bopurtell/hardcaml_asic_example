#!/usr/bin/env python3
"""Enumerate mandatory host paths for the provider's public stat-only admission."""
import argparse
from pathlib import Path
from pt7named_acceptance import write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = set()

    def walk(path, ancestors=()):
        resolved = path.resolve(strict=True)
        assert resolved not in ancestors, f'cyclic PDK tree: {path}'
        if path.is_dir():
            for child in sorted(path.iterdir()):
                walk(child, (*ancestors, resolved))
        else:
            paths.add(str(path.absolute()))

    walk(args.pdk)
    # Bundle.publish exposes a stable symlink; Stage_preparation resolves/copies it
    # into a canonical project directory. Admit the current frozen object inputs.
    walk(args.bundle.resolve(strict=True))
    paths.add(str(args.plan.absolute()))
    # Exact provisioned support reference selected by this specimen's manifest.
    import json
    manifest = json.loads((args.bundle / 'manifest.json').read_text())
    root = Path(__file__).resolve().parents[3]
    for reference in manifest['target']['external_references']:
        if reference['source'] == 'Support_tools':
            walk(root / '_flow_tools/tt' / reference['path'])
    write_new(args.output, sorted(paths))
    print(f'Enumerated {len(paths)} mandatory existing PDK/bundle/plan/support paths; provider admission follows')


if __name__ == '__main__':
    main()
