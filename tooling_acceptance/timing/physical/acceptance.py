#!/usr/bin/env python3
"""Public physical timing preparation. Every attempt is retained, never retried."""
import argparse
import json
from pathlib import Path

from commands import ROOT, STORE, command, inventory, sha, write_new
from check_emission import check as check_emission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('capture', 'build', 'emit'))
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', type=Path)
    parser.add_argument('--stage', choices=('synthesis', 'full'), default='synthesis')
    args = parser.parse_args()
    if not args.attempt or Path(args.attempt).name != args.attempt:
        parser.error('attempt must be a single directory name')
    output = STORE / 'evidence' / args.attempt
    output.mkdir(parents=True, exist_ok=False)
    generation = args.generation.resolve(strict=True) if args.generation else None
    if args.phase == 'capture':
        code = command(output / 'capture', ['opam', 'exec', '--switch=5.2.0+ox', '--',
                       'flock', '/tmp/opencode/asic-pt7-build.lock', 'python3', '-B',
                       'scripts/asic_dependency.py', '--store', STORE / 'provider',
                       'refresh', '--source', ROOT.parent / 'hardcaml_asic',
                       '--mode', 'development', '--jobs', '6'], timeout=1200)
    else:
        if not generation or not generation.is_relative_to(STORE / 'provider/generations'):
            parser.error('exact generation in the new physical store is required')
        if args.phase == 'build':
            code = command(output / 'build', ['opam', 'exec', '--switch=5.2.0+ox', '--',
                           'flock', '/tmp/opencode/example-pt7-build.lock', 'dune', 'build',
                           '--build-dir', '_build_timing_physical', '-j6',
                           'tooling_acceptance/timing/physical/physical_timing_cli.exe'], generation=generation)
        else:
            bundle = STORE / 'bundles' / args.attempt
            code = command(output / 'emit',
                           [ROOT / '_build_timing_physical/default/tooling_acceptance/timing/physical/physical_timing_cli.exe',
                            'emit-physical', args.stage, ROOT, bundle], generation=generation)
            if code == 0:
                manifest = json.loads((bundle / 'manifest.json').read_text())
                for row in manifest['files']:
                    if sha(bundle / row['path']) != row['sha256']:
                        raise ValueError(f'emitted file hash mismatch: {row["path"]}')
                marker = manifest['timing_physical_qualification']
                assert marker['analysis_corners'] == 'all_configured'
                assert marker['sequential_inventory'] == 'exact_declared_stages'
                assert manifest['timing_intent']['resolution_policy'] == 'scalar-q-driver-cmos5l-physical-v2'
                assert len(manifest['timing_intent']['stages']) == 5
                emission_check = check_emission(bundle)
                write_new(output / 'emission-preservation.json', emission_check)
                assert emission_check['rtl_identical'] and emission_check['environment_prefix_identical']
                write_new(output / 'prepared.json', {
                    'bundle': str(bundle), 'stage': args.stage,
                    'bundle_identity': manifest['identity'], 'generation': str(generation),
                    'provider_receipt_sha256': sha(generation / 'receipt.json'),
                    'bundle_inventory': inventory(bundle)})
    raise SystemExit(code)


if __name__ == '__main__':
    main()
