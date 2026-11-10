#!/usr/bin/env python3
"""Public real-attempt substitution controls; original sources stay untouched."""
import argparse
import copy
import json
from pathlib import Path

from pt7named_acceptance import EVIDENCE, ROOT, STORE, command, inventory, sha, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--execution', type=Path, required=True)
    parser.add_argument('--other-execution', type=Path, required=True)
    args = parser.parse_args()
    generation = args.generation.resolve(strict=True)
    assert generation.is_relative_to(STORE / 'provider/generations')
    first = args.execution.resolve(strict=True)
    second = args.other_execution.resolve(strict=True)
    assert first != second
    original = json.loads(first.read_text())
    other = json.loads(second.read_text())
    assert original['timing_intent']['attempt_id'] != other['timing_intent']['attempt_id']
    assert original['methodology'] != other['methodology'], 'use distinct actual profiles'
    output = EVIDENCE / args.attempt
    output.mkdir(exist_ok=False)
    protected = {str(path): inventory(path) for path in {first.parent, second.parent}}
    provider = generation / 'bin/hardcaml-asic-flow'
    controls = {'unchanged-snapshot': copy.deepcopy(original),
                'other-real-expectation': copy.deepcopy(original),
                'other-real-methodology': copy.deepcopy(original),
                'other-real-checkpoint': copy.deepcopy(original),
                'other-real-occurrence': copy.deepcopy(original),
                'missing-required-expectation': copy.deepcopy(original)}
    controls['other-real-expectation']['timing_intent'] = other['timing_intent']
    controls['other-real-methodology']['methodology'] = other['methodology']
    controls['other-real-checkpoint']['artifacts'] = other['artifacts']
    controls['other-real-occurrence']['occurrences'] = other['occurrences']
    del controls['missing-required-expectation']['timing_intent']
    summary = {}
    for name, record in controls.items():
        directory = output / name
        directory.mkdir()
        target = directory / 'execution.json'
        write_new(target, record)
        valid = name == 'unchanged-snapshot'
        inspected = command(directory, 'snapshot',
                            [ROOT / '_build_pt7named/default/tooling_acceptance/timing/named_flow/reader/named_snapshot.exe',
                             first, target], generation, (0,) if valid else (2,))
        if valid:
            view = json.loads(inspected.read_text())
            assert view['status'] == 'completed'
            public = command(directory, 'public-inspect', [provider, 'timing-intent-inspect', first,
                             '--kind', 'execution', '--json'], generation, (1,))
            reported = command(directory, 'public-report', [provider, 'report', first, '--json'],
                               generation, (0, 1))
            assert json.loads(public.read_text()) == view
            assert json.loads(reported.read_text())['timing_intent'] == view
        else:
            # An allowed nonzero exit by itself is not a sufficient rejection witness.
            inspect_error = (directory / 'snapshot/stderr.log').read_text() + inspected.read_text()
            assert inspect_error.strip()
            assert 'exact execution JSON path required' not in inspect_error
            assert 'changed from captured snapshot' not in inspect_error
        summary[name] = {'execution_sha256': sha(target), 'positive_control': valid,
                         'snapshot_stdout_sha256': sha(inspected),
                         'diagnostic': None if valid else inspect_error.strip()}
    for directory, before in protected.items():
        assert before == inventory(Path(directory)), 'control changed original source files'
    write_new(output / 'controls.json', {'original': str(first), 'other': str(second),
              'controls': summary, 'original_sources_unchanged': True,
              'scope': 'public captured-snapshot API controls; exact original execution/checkpoint paths retained'})


if __name__ == '__main__':
    main()
