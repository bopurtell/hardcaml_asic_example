#!/usr/bin/env python3
"""Installed pair control/association checks on explicitly labelled evidence copies."""
import argparse
import json
from pathlib import Path
import shutil

import pt8_workloads as p
from pt8_workloads_acceptance import load, replace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--simulation', required=True)
    args = parser.parse_args()
    output = p.EVIDENCE / args.attempt
    output.mkdir()
    generation = args.generation.resolve(strict=True)
    sim = p.EVIDENCE / args.simulation
    lp = sim / 'flops/result.json'
    rp = sim / 'exact/result.json'
    api = p.BUILD / 'workload_public.exe'
    cli = generation / 'bin/hardcaml-asic-flow'
    checks = {}

    def pair(label, right, reject=False, wrong_bundle=False):
        lb, rb = load(lp)['bundle'], load(right)['bundle']
        if wrong_bundle:
            lb = load(rp)['bundle']
        av = p.command(output, label + '-api', [api, 'compare', lb, rb, lp, right], generation,
                       (2,) if reject else (0,), trace=True, timeout=180)
        cv = p.command(output, label + '-cli', [cli, 'compare', '--left-kind', 'bundle',
            '--left', lb, '--right-kind', 'bundle', '--right', rb, '--axis', 'resource_policy',
            '--left-workload', lp, '--right-workload', right, '--json'], generation,
            (2,) if reject else (0,), trace=True, timeout=180)
        if reject:
            ae = (av.parent / 'stderr.log').read_text()
            ce = (cv.parent / 'stderr.log').read_text()
            diagnostic = 'match' if wrong_bundle else 'unsupported'
            assert diagnostic in ae and diagnostic in ce, (ae, ce)
            checks[label] = {'rejected': True, 'api_error': ae, 'cli_error': ce}
            return
        a = load(av)
        assert a == load(cv)
        metrics = [m for m in a['metrics'] if m['metric_id'].startswith('workload/')]
        assert len(metrics) == 7
        assert all(m['comparison'] != 'comparable' and m['right_minus_left'] is None for m in metrics), metrics
        checks[label] = [{k: m[k] for k in ('metric_id', 'comparison', 'reasons', 'right_minus_left')}
                         for m in metrics]

    pair('wrong-target-association', rp, reject=True, wrong_bundle=True)
    pair('ignored-workload', sim / 'ignored-workload/result.json')
    pair('ignored-hardware', sim / 'flops-ignored/result.json')
    for field in ('adapter', 'clock', 'model', 'measurement', 'workload'):
        directory = output / (field + '-fixture-not-a-new-execution')
        shutil.copytree(sim / 'exact', directory)
        r, s = load(directory / 'result.json'), load(directory / 'simulation.json')
        if field == 'workload':
            r['workload']['seed'] += 1
            r['workload']['identity'] = p.identity({k: v for k, v in r['workload'].items() if k != 'identity'})
            s['workload_identity'] = r['workload']['identity']
        else:
            s[field] += '-changed-control'
        replace(directory / 'simulation.json', s)
        r['simulation'] = p.ref(directory, directory / 'simulation.json')
        replace(directory / 'result.json', r)
        pair(field, directory / 'result.json', reject=field in ('adapter', 'clock', 'measurement'))
    p.write(output / 'assertions.json', {'pass': True, 'api_cli_parity': True,
        'checks': checks, 'scope': 'negative-only copied metadata, no execution claims',
        'generation': str(generation)})


if __name__ == '__main__':
    main()
