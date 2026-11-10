#!/usr/bin/env python3
"""Isolate actual public precheck path-policy rejection without modifying inputs."""
import argparse
import json
from pathlib import Path
from pt7named_acceptance import EVIDENCE, ROOT, command, sha, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--paths', type=Path, required=True)
    args = parser.parse_args()
    output = EVIDENCE / args.attempt
    output.mkdir(exist_ok=False)
    generation = args.generation.resolve(strict=True)
    paths = json.loads(args.paths.read_text())
    aliases = [{'declared': path, 'target': str(Path(path).resolve(strict=True)),
                'file_symlink': Path(path).is_symlink(), 'bytes': Path(path).stat().st_size}
               for path in paths if str(Path(path).resolve(strict=True)) != path]
    assert aliases
    witness = next(row for row in aliases if '/_flow_tools/pdk/' in row['declared'])
    adapter = ROOT / '_build_pt7named/default/tooling_acceptance/timing/named_flow/reader/named_precheck.exe'
    write_new(output / 'single-declared.json', [witness['declared']])
    write_new(output / 'single-target.json', [witness['target']])
    # Diagnostic only: the production closure retains declared aliases and has no
    # checked alias mapping. This is not a substitute production input inventory.
    canonical = sorted({str(Path(path).resolve(strict=True)) for path in paths})
    write_new(output / 'canonical-targets-diagnostic.json', canonical)
    command(output, 'declared-alias-reject', [adapter, output / 'single-declared.json'], generation, (2,))
    command(output, 'same-target-admit', [adapter, output / 'single-target.json'], generation)
    command(output, 'canonical-targets-diagnostic', [adapter, output / 'canonical-targets-diagnostic.json'], generation)
    write_new(output / 'diagnosis.json', {
        'status': 'actual_declared_alias_rejected_canonical_target_admitted',
        'original_inventory': str(args.paths.resolve()), 'original_inventory_sha256': sha(args.paths),
        'declared_paths': len(paths), 'linked_paths': len(aliases), 'canonical_target_count': len(canonical),
        'pdk_witness': witness,
        'aliases': aliases, 'production_inventory_changed': False,
        'scope': 'diagnostic public API path admission only; not native acceptance or relocation support'})


if __name__ == '__main__':
    main()
