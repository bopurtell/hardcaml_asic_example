#!/usr/bin/env python3
"""Seal corrected inspector identity separately from the historical native producer."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from pt7c_probe import ROOT, digest
from pt7c_reader_r1b import PARSER, inventory


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generation', type=Path, required=True)
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--attempt', required=True)
    a = p.parse_args()
    out = ROOT / 'acceptance/pt7c' / a.attempt
    out.mkdir(exist_ok=False)
    generation = a.generation.resolve(strict=True)
    summary = json.loads((a.replay / 'summary.json').read_text())
    assert str(generation) == summary['corrected_inspector']['generation']
    assert summary['corrected_inspector']['parser_sha256'] == PARSER
    execution = Path(summary['original_execution']['generation'])
    assert (ROOT / '.dev/asic-pt7c/provider/current').resolve() == execution
    subprocess.run([sys.executable, '-B', str(ROOT / 'tooling_acceptance/timing/controls/pt7c_preservation.py'), 'verify',
                    '--baseline', str(ROOT / 'acceptance/pt7c/original-history.json'),
                    '--output', str(out / 'original-protection.json')], check=True)
    subprocess.run([sys.executable, '-B', str(ROOT / 'tooling_acceptance/timing/controls/pt7c_v2_preserve.py'), 'verify',
                    '--baseline', str(ROOT / 'acceptance/pt7c/r1b-history-baseline-01'),
                    '--output', str(out / 'prior-evidence-protection')], check=True)
    for name, expected in json.loads((a.replay / 'commands.json').read_text()).items():
        assert digest(a.replay / (name + '.stdout')) == expected['stdout_sha256']
        assert digest(a.replay / (name + '.stderr')) == expected['stderr_sha256']
    identities = {
        'scope': 'reader-only correction; existing native execution remains attributed to original generation',
        'original_native_execution': summary['original_execution'],
        'corrected_inspector': summary['corrected_inspector'],
        'corrected_inspector_installed_files': inventory(generation),
        'original_execution_installed_files': inventory(execution),
        'unchanged_producer_runtime': summary['unchanged_producer_runtime'],
        'original_provider_pointer': str((ROOT / '.dev/asic-pt7c/provider/current').readlink()),
        'native_launches': 0, 'bundle_emissions': 0,
        'replay_summary_sha256': digest(a.replay / 'summary.json'),
    }
    (out / 'identities.json').write_text(json.dumps(identities, indent=2) + '\n')
    (out / 'tested-reader.ml').write_bytes((generation / 'lib/hardcaml_asic/execution/results/timing_native_coverage.ml').read_bytes())
    for name in ('pt7c-native-handoff.md', 'pt7c-flow-handoff.md', 'pt7c-native-review.md', 'pt7c-flow-review.md'):
        source = ROOT.parent / 'hardcaml_asic/docs/development' / name
        (out / name).write_bytes(source.read_bytes())
    (out / 'git-status.txt').write_bytes(subprocess.check_output(['git', 'status', '--short'], cwd=ROOT))
    paths = list((ROOT / 'acceptance/pt7c').rglob('*'))
    paths += list((ROOT / 'tooling_acceptance/timing/controls').glob('pt7c_*.py'))
    paths += list((ROOT / 'tooling_acceptance/timing/basic').glob('pt7c_*'))
    paths += list((ROOT / 'docs').glob('pt7c_*.md'))
    paths += [ROOT / 'acceptance/pt7c/native_reader.ml']
    checksums = {str(path.relative_to(ROOT)): digest(path) for path in sorted(paths) if path.is_file()}
    (out / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n')


if __name__ == '__main__':
    main()
