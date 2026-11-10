#!/usr/bin/env python3
"""Correction-era preservation and unchanged execution reuse, with fresh receipts."""
import argparse
import json
import os
from pathlib import Path
import shutil

import pt8_workloads as p
from pt8_workloads_acceptance import load


def inventory(paths):
    files, links = {}, {}
    for base in paths:
        for directory, dirs, names in os.walk(base, followlinks=False):
            d = Path(directory)
            for name in names + [n for n in dirs if (d / n).is_symlink()]:
                f = d / name
                key = str(f.relative_to(p.ROOT))
                if f.is_symlink():
                    links[key] = str(f.readlink())
                elif f.is_file():
                    files[key] = p.sha(f)
    return {'files': files, 'symlinks': links}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('phase', choices=['baseline', 'verify'])
    ap.add_argument('--output', required=True)
    ap.add_argument('--prior-reader-receipt', default='final-receipt.json')
    ap.add_argument('--baseline', default='correction-baseline-01/baseline.json')
    a = ap.parse_args()
    out = p.EVIDENCE / a.output
    out.mkdir()
    if a.phase == 'baseline':
        prior = load(p.EVIDENCE / 'final-receipt.json')
        reader = load(p.EVIDENCE / a.prior_reader_receipt)
        snapshot = inventory([p.EVIDENCE, Path(prior['provider_generation']), Path(reader['provider_generation'])])
        p.write(out / 'baseline.json', snapshot)
        shutil.copyfile(p.ROOT / 'docs/pt8_workloads_final.md', out / 'original-final.md')
        for name in ('workload_emit.exe', 'workload_public.exe'):
            path = p.BUILD / name
            assert p.sha(path) == reader['binaries'][str(path)]
            shutil.copyfile(path, out / ('original-' + name))
        checks = {}
        for label in ('flops', 'exact', 'flops-ignored', 'ignored-workload'):
            directory = p.EVIDENCE / 'simulation-04' / label
            # Every retained simulation byte, including raw trace and tool outputs,
            # must agree with the original sealed evidence, not just JSON meaning.
            for f in directory.rglob('*'):
                if f.is_file():
                    assert p.sha(f) == prior['retained_attempt_inventory'][str(f.relative_to(p.EVIDENCE))]
            r = load(directory / 'result.json')
            manifest = load(Path(r['bundle']) / 'manifest.json')
            source_hashes = {}
            for source in manifest['source_inputs']:
                assert p.sha(p.ROOT / source['path']) == source['sha256']
                source_hashes[source['path']] = source['sha256']
            simulation = load(directory / 'simulation.json')
            for artifact in simulation['artifacts']:
                f = directory / artifact['source']['path']
                assert p.sha(f) == artifact['source']['sha256']
            assert (directory / 'testbench.v').read_text() == p.bench(
                r['workload']['operations'], label == 'ignored-workload')
            for source in manifest['synthesis_sources']:
                assert p.sha(Path(r['bundle']) / source) == p.sha(directory / Path(source).name)
            checks[label] = {'source_hashes': source_hashes,
                             'result_sha256': p.sha(directory / 'result.json'),
                             'testbench_sha256': p.sha(directory / 'testbench.v'),
                             'bundle': r['bundle'], 'attempt_id': simulation['attempt_id']}
        p.write(out / 'reuse.json', {'pass': True, 'additional_simulations': 0,
            'simulation_producer_generation': prior['provider_generation'],
            'simulation_producer_snapshot': prior['provider_receipt']['snapshot_sha256'],
            'original_binaries': prior['binaries'], 'checks': checks})
    else:
        baseline = load(p.EVIDENCE / a.baseline)
        failures = [s for s, h in baseline['files'].items()
                    if not (p.ROOT / s).is_file() or (p.ROOT / s).is_symlink() or p.sha(p.ROOT / s) != h]
        failures += [s for s, t in baseline['symlinks'].items()
                     if not (p.ROOT / s).is_symlink() or str((p.ROOT / s).readlink()) != t]
        # Original task baseline includes all pre-existing external/consumer data.
        import pt8_workloads_preserve as preserve
        original = load(p.EVIDENCE / 'preservation-baseline.json')
        failures += [s for s, h in original['files'].items()
                     if not (p.ROOT / s).is_file() or (p.ROOT / s).is_symlink() or preserve.sha(p.ROOT / s) != h]
        failures += [s for s, t in original['symlinks'].items()
                     if not (p.ROOT / s).is_symlink() or str((p.ROOT / s).readlink()) != t]
        p.write(out / 'preservation.json', {'failures': failures,
            'original_files': len(original['files']), 'original_symlinks': len(original['symlinks']),
            'correction_files': len(baseline['files']), 'correction_symlinks': len(baseline['symlinks'])})
        assert not failures, failures


if __name__ == '__main__':
    main()
