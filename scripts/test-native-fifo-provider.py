#!/usr/bin/env python3
"""Compare a prebuilt native adapter to the independent Python reference. No builds."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/workbench'))
from wire import parse, sexp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--simulator', type=Path, required=True)
    args = parser.parse_args()
    commands = [
        [str(args.provider.resolve()), '--simulator', str(args.simulator.resolve())],
        [sys.executable, '-B', str(ROOT / 'ip/controlled_fifo/verif/simulation/provider.py'),
         '--simulator', str(args.simulator.resolve())],
    ]
    discovery = [subprocess.run(c + ['discover', '--protocol-version', '1'],
                               check=True, capture_output=True, text=True) for c in commands]
    assert parse(discovery[0].stdout) == parse(discovery[1].stdout), 'discovery differs'
    scenarios = [
        (['directed'], '42', 'normal'),
        (['seeded'], '0', 'normal'),
        (['directed', 'seeded'], '65536', 'normal'),
        (['directed', 'seeded'], '18446744073709551615', 'mismatch'),
        (['seeded', 'directed'], '18446744073709551615', 'normal'),
    ]
    mismatches = []
    with tempfile.TemporaryDirectory(prefix='fifo-native-equivalence-') as temporary:
        root = Path(temporary)
        project = root / 'private-project'
        project.mkdir()
        spec = importlib.util.spec_from_file_location(
            'fifo_installer', ROOT / 'scripts/install-fifo-simulation.py')
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with contextlib.redirect_stdout(io.StringIO()):
            installer.main(['--provider', str(args.provider.resolve()),
                            '--simulator', str(args.simulator.resolve())], root=project)
        installed = json.loads((project / '.dev/fifo-simulation-install.json').read_text())
        # Exercise the installed adjacent-simulator default as well as explicit prefix args.
        commands.append([str(Path(installed['generation']) / 'test_provider.exe')])
        for index, (cases, seed, checker) in enumerate(scenarios):
            parameters = [('checker', checker), ('cycles', '64')]
            if index == len(scenarios) - 1:
                # Deliberately exercise non-catalog case and parameter ordering too.
                parameters.reverse()
            selection = [('suite', 'controlled-fifo'), ('cases', cases), ('seed', seed),
                         ('parameters', parameters),
                         ('asic_inputs', [])]
            request = root / 'request.sexp'
            request.write_text(sexp([('protocol_version', 1), ('attempt_id', 'equivalence'),
                                     ('selection', selection)]))
            results = []
            for language, command in enumerate(commands):
                output = root / f'{index}-{language}'
                output.mkdir()
                artifacts = output / 'artifacts'
                artifacts.mkdir()
                events = output / 'events.sexp'
                result = subprocess.run(command + [
                    'run', '--protocol-version', '1', '--request', str(request),
                    '--events', str(events), '--artifact-dir', str(artifacts)],
                    check=True, capture_output=True, text=True)
                results.append((
                    [parse(line) for line in events.read_text().splitlines()],
                    {p.name: p.read_bytes() for p in artifacts.iterdir()}, result.stdout))
            for component, label in enumerate(('events', 'artifact bytes', 'stdout')):
                for native in (0, 2):
                    if results[native][component] != results[1][component]:
                        mismatches.append((index, label, native))
            outcome = 'DIFFERS' if any(item[0] == index for item in mismatches) else 'equivalent'
            print(f'{outcome}: cases={cases} seed={seed} checker={checker}')
        invalid = [
            [('suite', 'unknown')], [('cases', ['directed', 'directed'])],
            [('cases', [])],
            [('seed', '01')], [('seed', '18446744073709551616')],
            [('parameters', [('cycles', '65'), ('checker', 'normal')])],
            [('parameters', [('cycles', '64'), ('checker', 'unknown')])],
            [('asic_inputs', [[
                ('run', [('backend', 'test'), ('id', 'test'), ('build', []), ('label', [])]),
                ('attempt', 'test'), ('artifact_id', 'test'), ('sha256', '0' * 64)]])],
        ]
        for index, overrides in enumerate(invalid):
            changed = dict(selection)
            changed.update(overrides)
            request.write_text(sexp([('protocol_version', 1), ('attempt_id', 'invalid'),
                                     ('selection', list(changed.items()))]))
            for language, command in enumerate(commands):
                events = root / f'invalid-{index}-{language}.sexp'
                result = subprocess.run(command + [
                    'run', '--protocol-version', '1', '--request', str(request),
                    '--events', str(events), '--artifact-dir', str(root)], capture_output=True)
                assert result.returncode != 0, (index, 'invalid request accepted')
                assert not events.exists() or events.stat().st_size == 0
        print('invalid requests rejected before events')
    assert not mismatches, mismatches


if __name__ == '__main__':
    main()
