"""Exercise the installed provider CLI against an isolated copy of the real designs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def run(cwd, *argv, error=None):
    p = subprocess.run(argv, cwd=cwd, text=True, capture_output=True)
    if error:
        assert p.returncode != 0 and not p.stdout, (argv, p)
        assert all(word in p.stderr.lower() for word in error), (argv, p.stderr)
        return
    assert p.returncode == 0, (argv, p.stderr)
    return json.loads(p.stdout)


def check(provider, root):
    # Mutate only the copy: the removed target remains a normal Dune executable.
    for name in ['dune-project', 'hardcaml-asic-targets.json']:
        shutil.copy(ROOT / name, root)
    for name in ['asics', 'ip']:
        shutil.copytree(ROOT / name, root / name)
    path = root / 'hardcaml-asic-targets.json'
    manifest = json.loads(path.read_text())
    catalog = run(root, provider, 'list')
    assert catalog == manifest
    entries = {entry['id']: entry for entry in catalog['targets']}
    assert run(root, provider, 'select') == entries['fifo_demo']
    expected = {
        'fifo_demo': ('controlled_fifo_specimen', 'standard', 'balanced'),
        'program_memory': ('program_memory_specimen', 'stock256-r0', 'qualification'),
    }
    for chip, (name, flow, profile) in expected.items():
        assert entries[chip]['executable'] == f'asics/{chip}/cli/chip.exe'
        assert run(root, provider, 'select', '--target', chip) == entries[chip]
        invoke = [provider, 'exec', '--target', chip, '--']
        assert run(root, *invoke, 'describe', '--json')['project_name'] == name
        flows = run(root, *invoke, 'flow', 'list', '--json')['declaration']
        assert flows['default'] == {'flow': flow, 'profile': profile}

    manifest['targets'].append(entries['program_memory'])
    path.write_text(json.dumps(manifest))
    run(root, provider, 'list', error=['duplicate', 'program_memory'])
    manifest['targets'] = [entry for entry in manifest['targets'] if entry['id'] != 'program_memory']
    path.write_text(json.dumps(manifest))
    assert run(root, provider, 'list')['targets'] == manifest['targets']
    run(root, provider, 'select', '--target', 'program_memory', error=['unknown', 'program_memory', 'fifo_demo'])
    run(root, provider, 'exec', '--target', 'program_memory', '--', 'describe', '--json',
        error=['unknown', 'program_memory'])
    subprocess.run(['dune', 'clean', '--root', '.'], cwd=root, check=True)
    direct = './' + entries['program_memory']['executable']
    assert run(root, 'dune', 'exec', '--root', '.', direct, '--', 'describe', '--json')['project_name'] == expected['program_memory'][0]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', default='hardcaml-asic-targets',
                        type=lambda value: shutil.which(value) or parser.error(f'not executable: {value}'))
    with tempfile.TemporaryDirectory(prefix='asic-target-catalog-') as tmp:
        # Keep Dune builds and the clean-rebuild check inside the disposable project.
        os.environ['DUNE_BUILD_DIR'] = str(Path(tmp) / '_build')
        check(Path(parser.parse_args().provider).resolve(strict=True), Path(tmp))
