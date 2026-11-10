#!/usr/bin/env python3
"""Installed public verification/comparison against actual retained RTL execution."""
import argparse
import copy
import json
from pathlib import Path
import shutil

import pt8_workloads as p


def load(path):
    return json.loads(path.read_text())


def replace(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--simulation', required=True)
    parser.add_argument('--generation', type=Path, required=True)
    args = parser.parse_args()
    output = p.EVIDENCE / args.attempt
    output.mkdir()
    generation = args.generation.resolve(strict=True)
    sim = p.EVIDENCE / args.simulation
    api = p.BUILD / 'workload_public.exe'
    cli = generation / 'bin/hardcaml-asic-flow'
    results = {}

    def inspect(label, path, reject=None):
        d = p.command(output, label, [api, 'inspect', path], generation,
                      (2,) if reject else (0,), trace=True, timeout=180)
        if reject:
            error = (d.parent / 'stderr.log').read_text()
            assert reject in error, (label, reject, error)
            results[label] = {'rejected': True, 'diagnostic': error.strip()}
            return None
        value = load(d)
        results[label] = {'outcome': value['outcome'], 'source_digest': value['source_digest']}
        return value

    def recheck(label, path, digest, reject=False):
        p.command(output, label, [api, 'recheck', path, digest], generation,
                  (2,) if reject else (0,), trace=True, timeout=180)

    def clone(label):
        directory = output / (label + '-evidence')
        shutil.copytree(sim / 'flops', directory)
        return directory, load(directory / 'result.json'), load(directory / 'simulation.json'), load(directory / 'trace.json')

    def save(directory, result, simulation, trace, reidentify=False):
        if reidentify:
            w = result['workload']
            w['identity'] = p.identity({k: v for k, v in w.items() if k != 'identity'})
            simulation['workload_identity'] = w['identity']
        replace(directory / 'trace.json', trace)
        result['trace'] = simulation['trace'] = p.ref(directory, directory / 'trace.json')
        result['stimulus'] = simulation['stimulus'] = p.ref(directory, directory / 'stimulus.json')
        replace(directory / 'simulation.json', simulation)
        result['simulation'] = p.ref(directory, directory / 'simulation.json')
        replace(directory / 'result.json', result)
        return directory / 'result.json'

    left_path, right_path = sim / 'flops/result.json', sim / 'exact/result.json'
    left = inspect('flops', left_path)
    right = inspect('exact', right_path)
    for value in (left, right):
        assert value['outcome']['functional'] == 'pass'
        assert value['outcome']['performance'] == 'available'
        assert len(value['metrics']) == 7
        assert all('firmware' not in m['metric_id'] and 'fetch' not in m['metric_id'] for m in value['metrics'])
    assert left['controls'] == right['controls'], 'same logical controls including exact tool settings'
    assert left['binding']['bundle_identity'] != right['binding']['bundle_identity']
    assert left['binding']['hardware_variant_identity'] == right['binding']['hardware_variant_identity']
    assert left['binding']['simulation_attempt_id'] != right['binding']['simulation_attempt_id']
    recheck('stable-recheck', left_path, left['source_digest'])
    for label in ('ignored-workload', 'flops-ignored'):
        value = inspect(label, sim / label / 'result.json')
        assert value['outcome']['functional'] == 'fail', value['outcome']
        assert value['outcome']['performance'] == 'unavailable'
        assert all(m['value'] is None for m in value['metrics'])

    # Wrong logical expected values remain malformed even when identities are rebound.
    d, r, s, t = clone('expected')
    r['workload']['expected'][259]['after'] ^= 1
    inspect('expected', save(d, r, s, t, True), 'expected')
    # Independently changed stimulus and trace input, coherently rehashed.
    d, r, s, t = clone('stimulus')
    stimulus = load(d / 'stimulus.json')
    stimulus['operations'][10]['data'] ^= 1
    replace(d / 'stimulus.json', stimulus)
    inspect('stimulus', save(d, r, s, t), 'stimulus')
    d, r, s, t = clone('input')
    t['rows'][10]['input']['address'] ^= 1
    inspect('input', save(d, r, s, t), 'input')
    # Coherent false counters over identical retained trace.
    for key in ('cycles', 'reads', 'writes', 'operations', 'defined_observations', 'read_latency'):
        d, r, s, t = clone('counter-' + key)
        r['counters'][key] += 1
        inspect('counter-' + key, save(d, r, s, t), 'counter')
    d, r, s, t = clone('window')
    r['workload']['window']['start'] = 300
    inspect('window', save(d, r, s, t, True), 'counter')
    d, r, s, t = clone('workload-association')
    s['workload_identity'] = '0' * 64
    inspect('workload-association', save(d, r, s, t), 'mismatch')
    for key in ('bundle_identity', 'hardware_variant_identity'):
        d, r, s, t = clone(key)
        s[key] = '0' * 64
        inspect(key, save(d, r, s, t), 'mismatch')
    d, r, s, t = clone('selected-bundle')
    r['bundle'] = load(right_path)['bundle']
    inspect('selected-bundle', save(d, r, s, t), 'mismatch')
    d, r, s, t = clone('artifact')
    source = next(a['source'] for a in s['artifacts'] if a['role'] == 'rtl')
    (d / source['path']).write_text((d / source['path']).read_text() + '\n// replaced\n')
    inspect('artifact', d / 'result.json', 'source reference mismatch')
    # Rehashed but not the bundle's implementation bytes must still reject.
    source.update(p.ref(d, d / source['path']))
    inspect('artifact-rebound', save(d, r, s, t), 'RTL')
    d, r, s, t = clone('missing-trace')
    (d / 'trace.json').unlink()
    inspect('missing-trace', d / 'result.json', 'retained')
    d, r, s, t = clone('truncated')
    (d / 'trace.json').write_bytes((d / 'trace.json').read_bytes()[:100])
    inspect('truncated', d / 'result.json', 'source reference mismatch')
    d, r, s, t = clone('short-completed')
    t['rows'] = t['rows'][:400]
    r['counters'] = p.counters(r['workload'], t)
    inspect('short-completed', save(d, r, s, t), 'completed')
    for status in ('partial', 'interrupted', 'failed'):
        d, r, s, t = clone(status)
        s['status'] = status
        t['rows'] = t['rows'][:400]
        r['counters'] = p.counters(r['workload'], t)
        value = inspect(status, save(d, r, s, t))
        assert value['outcome']['status'] == status
        assert value['outcome']['performance'] == 'unavailable'
        assert all(m['value'] is None for m in value['metrics'])
    # Same attempt's bytes changed: public generation recheck must catch it.
    d, r, s, t = clone('stale-attempt')
    path = d / 'result.json'
    captured = inspect('stale-attempt-before', path)
    s['attempt_id'] += '-replaced'
    save(d, r, s, t)
    recheck('stale-attempt-after', path, captured['source_digest'], True)
    d, r, s, t = clone('stale-source')
    captured = inspect('stale-source-before', d / 'result.json')
    (d / 'tool.json').write_text((d / 'tool.json').read_text() + ' ')
    recheck('stale-source-after', d / 'result.json', captured['source_digest'], True)

    def compare(label, lp=left_path, rp=right_path):
        lb, rb = load(lp)['bundle'], load(rp)['bundle']
        av = p.command(output, label + '-api', [api, 'compare', lb, rb, lp, rp],
                       generation, trace=True, timeout=180)
        cv = p.command(output, label + '-cli', [cli, 'compare', '--left-kind', 'bundle',
            '--left', lb, '--right-kind', 'bundle', '--right', rb, '--axis', 'resource_policy',
            '--left-workload', lp, '--right-workload', rp, '--json'],
            generation, trace=True, timeout=180)
        a, c = load(av), load(cv)
        assert a == c, 'entire installed API/CLI parity'
        return a

    comparison = compare('matched')
    p.write(output / 'matched.json', comparison)
    # Keep assertions independent of incidental presentation ordering.
    metrics = [m for m in comparison['metrics'] if m['metric_id'].startswith('workload/')]
    assert len(metrics) == 7, [m.get('metric_id') for m in comparison['metrics']]
    for m in metrics:
        assert m['comparison'] == 'comparable', m
        assert m['right_minus_left'] == 0, m
    p.write(output / 'assertions.json', {'pass': True, 'checks': results,
        'workload_comparable_zero_delta_metrics': 7, 'api_cli_parity': True,
        'generation': str(generation), 'provider_receipt_sha256': p.sha(generation / 'receipt.json'),
        'public_executable_sha256': p.sha(api), 'emitter_executable_sha256': p.sha(p.BUILD / 'workload_emit.exe')})


if __name__ == '__main__':
    main()
