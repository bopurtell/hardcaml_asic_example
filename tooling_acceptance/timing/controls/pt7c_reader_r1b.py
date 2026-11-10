#!/usr/bin/env python3
"""Reader-only final qualification: retained native-v2 replay and raw CR negatives.

Never emits a bundle or runs EDA. Originals are mounted read-only for public
commands; altered diagnostic copies are resealed to reach semantic validation.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

from pt7c_probe import ROOT, digest
from pt7c_v2_review_controls import load, reseal

PARSER = 'f141b57575d48c4c09678fea34aa499f1adfc797a20b0839c3269928fd9b9f07'


def inventory(root):
    return {str(p.relative_to(root)): digest(p) for p in root.rglob('*') if p.is_file()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generation', type=Path, required=True)
    p.add_argument('--attempt', required=True)
    a = p.parse_args()
    generation = a.generation.resolve(strict=True)
    out = ROOT / 'acceptance/pt7c' / a.attempt
    out.mkdir(exist_ok=False)
    original = ROOT / '.dev/asic-pt7c/runs/20261028T183412758171Z_83a02bdc'
    prior_restore = ROOT / 'acceptance/pt7c/public-v2-01/restored'
    execution_generation = ROOT / '.dev/asic-pt7c/provider/generations/4d4316e3a33942c2a577d6f55acaa34a'
    assert (ROOT / '.dev/asic-pt7c/provider/current').resolve() == execution_generation
    parser = generation / 'lib/hardcaml_asic/execution/results/timing_native_coverage.ml'
    assert digest(parser) == PARSER
    unchanged = {}
    for name in ('lib/hardcaml_asic/elaboration/timing_coverage_tcl.ml',
                 'lib/hardcaml_asic/flow/hardcaml_asic_flow/timing_intent_runtime.py'):
        assert (generation / name).read_bytes() == (execution_generation / name).read_bytes()
        unchanged[name] = digest(generation / name)
    before = {'original': inventory(original), 'prior_restored': inventory(prior_restore)}
    (out / 'protection-before.json').write_text(json.dumps(before, indent=2) + '\n')
    baseline = load(ROOT / 'acceptance/pt7c/public-v2-01/inspect/stdout.log')
    baseline_collect = load(ROOT / 'acceptance/pt7c/public-v2-01/collect/stdout.log')
    corner = baseline['executed_corners'][0]
    provider = generation / 'bin/hardcaml-asic-flow'
    receipts = {}
    readonly = ['bwrap', '--ro-bind', '/', '/', '--unshare-user',
                '--unshare-net', '--die-with-parent', '--tmpfs', '/tmp',
                '--bind', str(out), str(out), '--chdir', '/tmp', '--']

    def command(label, args, expected, diagnostic=None, prefix=None):
        argv = (readonly if prefix is None else prefix) + [str(provider), *map(str, args)]
        result = subprocess.run(argv, capture_output=True, timeout=120)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        receipts[label] = dict(argv=argv, exit_code=result.returncode, expected=expected,
                               diagnostic=diagnostic, stdout_sha256=digest(out / (label + '.stdout')),
                               stderr_sha256=digest(out / (label + '.stderr')))
        (out / 'commands.json').write_text(json.dumps(receipts, indent=2) + '\n')
        assert result.returncode == expected, (label, result.returncode, result.stderr.decode())
        if diagnostic:
            assert diagnostic in (result.stdout + result.stderr).decode(), (label, result.stderr.decode())
        return json.loads(result.stdout) if expected in (0, 1) and result.stdout else None

    def replay(label, root, prefix=None):
        assert command(label + '-inspect', ['timing-intent-inspect', root, '--kind', 'coarse_run', '--json'], 1, prefix=prefix) == baseline
        assert command(label + '-collect', ['collect', root, '--stdout', '--json'], 0, prefix=prefix) == baseline_collect
        assert command(label + '-report', ['report', root, '--json'], 0, prefix=prefix) == baseline_collect

    replay('original', original)
    replay('prior-restored', prior_restore)
    assert command('standalone', ['timing-intent-inspect', original / 'timing-intent/corners' / corner, '--json'], 1) == baseline['corners'][0]
    # Archive's supervised gzip uses the ordinary host process environment. Run it
    # only on a NEW retained-source copy; original evidence is never a write target.
    archive_source = out / 'archive-source'
    shutil.copytree(prior_restore, archive_source)
    command('archive', ['archive', archive_source, '--output', out / 'archive-output', '--json'], 0, prefix=[])
    restored = out / 'restored'
    restored.mkdir()
    for path in (out / 'archive-output').glob('*.tar.gz'):
        with tarfile.open(path) as stream:
            stream.extractall(restored, filter='data')
    for source in (restored / 'bundle').rglob('*'):
        if source.is_file():
            target = restored / 'project' / source.relative_to(restored / 'bundle')
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    for name in ('run.json', 'results.json', 'preflight.json'):
        source = out / 'archive-output' / name
        if source.exists():
            shutil.copyfile(source, restored / name)
    hidden = ['bwrap', '--ro-bind', '/', '/', '--unshare-user', '--unshare-net',
              '--die-with-parent', '--tmpfs', str(ROOT), '--tmpfs', str(ROOT.parent / 'hardcaml_asic'),
              '--ro-bind', str(generation), str(generation), '--ro-bind', str(restored), str(restored),
              '--tmpfs', '/tmp', '--chdir', '/tmp', '--']
    replay('new-archive-sandbox', restored, hidden)

    source_state = (original / 'timing-intent/corners' / corner / 'native-state.sdc').read_bytes()
    assert b'\r' not in source_state
    extra = b'set_false_path -from [get_ports {ena}] -to [get_pins {_05_/D}]\n'
    masking = b'set_disable_timing -from {CLK} -to {Q} [get_cells {_06_}]\n'
    design = b'current_design unrelated_top\n'
    cr = 'CR in native SDC'
    cases = {
        'LF-original': (source_state, None),
        'LF-ordinary-comment': (source_state + b'# ordinary LF comment\n', None),
        'bare-CR-extra-scope': (source_state + b'# comment\r' + extra, cr),
        'bare-CR-masking': (source_state + b'# comment\r' + masking, cr),
        'bare-CR-design': (source_state + b'# comment\r' + design, cr),
        'CRLF': (source_state.replace(b'\n', b'\r\n'), cr),
        'mixed-CRLF': (source_state + b'# mixed comment\r\n', cr),
        'CR-only': (source_state.replace(b'\n', b'\r'), cr),
        'CR-braced-value': (source_state + b'set_load {note\rcontinued} [get_ports {uo_out[0]}]\n', cr),
        'CR-quoted-value': (source_state + b'set_load "note\rcontinued" [get_ports {uo_out[0]}]\n', cr),
        'CRLF-native-continuation': (source_state.replace(b'set_false_path\\\n', b'set_false_path\\\r\n', 1), cr),
        'LF-extra-scope': (source_state + b'# comment\n' + extra, 'extra exception relations'),
        'LF-masking': (source_state + b'# comment\n' + masking, 'unsupported native SDC command: set_disable_timing'),
        'LF-design': (source_state + b'# comment\n' + design, 'repeated/ambiguous current_design selection'),
    }
    case_summary = {}
    for name, (raw, diagnostic) in cases.items():
        root = out / 'cases' / name
        root.parent.mkdir(exist_ok=True)
        shutil.copytree(prior_restore, root)
        directory = root / 'timing-intent/corners' / corner
        # Binary writes and hashes preserve CR bytes; no universal-newline input.
        (directory / 'native-state.sdc').write_bytes(raw)
        reseal(root, corner)
        expected = 2 if diagnostic else 1
        view = command(name + '-inspect', ['timing-intent-inspect', root, '--kind', 'coarse_run', '--json'], expected, diagnostic)
        inner = command(name + '-standalone', ['timing-intent-inspect', directory, '--json'], expected, diagnostic)
        if not diagnostic:
            assert view['corners'][0]['native_coverage'] == baseline['corners'][0]['native_coverage']
            assert inner['native_coverage'] == baseline['corners'][0]['native_coverage']
        command(name + '-collect', ['collect', root, '--stdout', '--json'], 0, diagnostic)
        command(name + '-report', ['report', root, '--json'], 1 if diagnostic else 0, diagnostic)
        command(name + '-archive', ['archive', root, '--output', out / (name + '-archive'), '--json'], 2 if diagnostic else 0, diagnostic, prefix=[])
        case_summary[name] = dict(cr_bytes=raw.count(b'\r'), native_sdc_sha256=digest(directory / 'native-state.sdc'), diagnostic=diagnostic)
    # Tcl source-channel oracle for the three concrete CR-comment bypasses.
    oracle = out / 'oracle'
    oracle.mkdir()
    prelude = 'set paths 0\nset disables 0\nset designs {}\nproc get_ports {args} {return $args}\nproc get_pins {args} {return $args}\nproc get_cells {args} {return $args}\nproc set_false_path {args} {incr ::paths}\nproc set_disable_timing {args} {incr ::disables}\nproc current_design {name} {lappend ::designs $name}\n'
    driver = oracle / 'driver.tcl'
    driver.write_text(prelude + 'source [lindex $argv 0]\nputs [list $paths $disables $designs]\n')
    oracle_results = {}
    for name, tail, expected in (('extra', extra, '2 0 tt_um_pt7_timing'),
                                 ('masking', masking, '1 1 tt_um_pt7_timing'),
                                 ('design', design, '1 0 {tt_um_pt7_timing unrelated_top}')):
        fixture = oracle / (name + '.tcl')
        fixture.write_bytes(b'current_design tt_um_pt7_timing\nset_false_path -from [get_ports {ena}] -to [get_pins {_06_/D}]\n# comment\r' + tail)
        result = subprocess.run(['tclsh', str(driver), str(fixture)], capture_output=True, timeout=30)
        (oracle / (name + '.stdout')).write_bytes(result.stdout)
        (oracle / (name + '.stderr')).write_bytes(result.stderr)
        oracle_results[name] = dict(exit_code=result.returncode, observed=result.stdout.decode().strip(), expected=expected)
        assert result.returncode == 0 and result.stdout.decode().strip() == expected, oracle_results[name]

    after = {'original': inventory(original), 'prior_restored': inventory(prior_restore)}
    assert after == before
    assert load(original / 'run.json')['status'] == 'completed'
    assert (ROOT / '.dev/asic-pt7c/provider/current').resolve() == execution_generation
    summary = dict(scope='reader-only replay; zero EDA/emission; no execution reattribution',
                   original_execution=dict(generation=str(execution_generation), receipt_sha256=digest(execution_generation / 'receipt.json'),
                       provider=load(execution_generation / 'receipt.json'), run_id=load(original / 'run.json')['run_id'],
                       run_record_sha256=digest(original / 'run.json'), native_producer_sha256=digest(original / 'timing-intent/corners' / corner / 'native-producer.tcl')),
                   corrected_inspector=dict(generation=str(generation), receipt_sha256=digest(generation / 'receipt.json'),
                       provider=load(generation / 'receipt.json'), parser_sha256=digest(parser), executable_sha256=digest(provider)),
                   unchanged_producer_runtime=unchanged, replay_public_commands=11, native_cases=case_summary,
                   semantic_public_assertions=len(cases) * 5, source_channel_oracles=oracle_results,
                   protection=dict(original_files=len(before['original']), restored_files=len(before['prior_restored']), changed=[]))
    (out / 'protection-after.json').write_text(json.dumps(after, indent=2) + '\n')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
