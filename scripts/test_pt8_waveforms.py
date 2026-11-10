#!/usr/bin/env python3
"""Focused dump-seam and FS2 failure-publication controls (no EDA/builds)."""
import argparse
import ast
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/workbench'))
sys.path.insert(0, str(ROOT / 'tooling_acceptance/workloads/controls'))
sys.path.insert(0, str(ROOT / 'tooling_acceptance/variants/controls'))

import pt8_workloads as producer
import pt8_workbench_provider as provider


class Waveforms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='pt8-waveform-', dir='/tmp/opencode')
        cls.root = Path(cls.temp.name)
        # Exercise actual Icarus output syntax, not a hand-written VCD facsimile.
        tb = cls.root / 'tb.v'
        tb.write_text(producer.bench(producer.workload()['operations'], capture_waveform=True) + '''
module tt_um_pt8_workload(input clk, ena, rst_n, input [7:0] ui_in, uio_in,
  output [7:0] uo_out, uio_out, uio_oe);
  assign {uio_out, uo_out}=16'bx;
endmodule
''')
        subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(cls.root / 'sim'), str(tb)], check=True)
        subprocess.run(['vvp', str(cls.root / 'sim')], cwd=cls.root, check=True, stdout=subprocess.DEVNULL)
        cls.vcd = (cls.root / 'waveform.vcd').read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_default_bench_has_no_dump_and_same_stimulus(self):
        ops = producer.workload()['operations']
        default = producer.bench(ops)
        self.assertEqual(default, producer.bench(ops, capture_waveform=False))
        self.assertNotIn('$dump', default)
        enabled = producer.bench(ops, capture_waveform=True)
        self.assertEqual(default, enabled.replace('    $dumpfile("waveform.vcd");\n'
            '    $dumpvars(0, tb.clk, tb.ena, tb.rst_n, tb.ui_in, tb.uio_in, tb.q);\n', ''))

    def test_default_matches_immutable_historical_producer(self):
        old = (Path(__file__).resolve().parents[1] / '.dev/asic-pt8-workbench/'
               'session-final-review-01/provider/scripts/pt8_workloads.py')
        if not old.is_file():
            self.skipTest('historical private capture absent')
        # Execute only the pure old bench function, with no imported runner state.
        function = next(n for n in ast.parse(old.read_text()).body
                        if isinstance(n, ast.FunctionDef) and n.name == 'bench')
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(old), 'exec'), namespace)
        for ignored in (False, True):
            self.assertEqual(producer.bench(producer.workload()['operations'], ignored),
                             namespace['bench'](producer.workload()['operations'], ignored))

    def test_real_syntax_and_budgets(self):
        d = producer.validate_waveform(self.root / 'waveform.vcd', 1307)
        self.assertEqual(d['last_time'], 13070000)
        self.assertEqual(len(d['signals']), 6)
        self.assertLess(d['source']['bytes'], 8 * 1024 * 1024)
        self.assertIn(b'bx ', self.vcd)

    def test_validation_negatives(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            p = Path(directory) / 'waveform.vcd'
            for name, data in [('empty', b''), ('oversize', b' ' * (8 * 1024 * 1024 + 1)),
                ('truncated', self.vcd[:1000]), ('wrong_signal', self.vcd.replace(b' clk ', b' storage ')),
                ('wrong_time', self.vcd.replace(b'#13070000', b'#13070001')),
                ('backwards', self.vcd + b'\n#1\n'), ('bad_change', self.vcd + b'\nb1 UNKNOWN\n')]:
                with self.subTest(name=name):
                    p.write_bytes(data)
                    with self.assertRaises(ValueError):
                        producer.validate_waveform(p, 1307)
            p.unlink()
            with self.assertRaises(ValueError):
                producer.validate_waveform(p, 1307)
            p.symlink_to(self.root / 'waveform.vcd')
            with self.assertRaises(ValueError):
                producer.validate_waveform(p, 1307)

    def malformed_supported_capture(self):
        return {
            'unsupported-real-type': self.vcd.replace(b'$var reg 1 ! clk', b'$var real 1 ! clk', 1),
            'missing-upscope': self.vcd.replace(b'$upscope $end\n', b'', 1),
            'scalar-bus': self.vcd.replace(b'bx &', b'x&', 1),
            'bad-range': self.vcd.replace(b'[7:0]', b'[999:0]', 1),
        }

    def test_supported_capture_header_and_assignment_regressions(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            p = Path(directory) / 'waveform.vcd'
            for name, data in self.malformed_supported_capture().items():
                with self.subTest(name=name):
                    self.assertNotEqual(data, self.vcd, 'mutation must actually apply')
                    p.write_bytes(data)
                    with self.assertRaises(ValueError):
                        producer.validate_waveform(p, 1307)
            for name, data in {
                'unbalanced-upscope': self.vcd.replace(b'$enddefinitions', b'$upscope $end\n$enddefinitions', 1),
                'unterminated-dump': self.vcd + b'\n$dumpvars\n',
                'nested-dump': self.vcd.replace(b'$dumpvars', b'$dumpvars\n$dumpall', 1),
                'duplicate-code': self.vcd.replace(b'1 " ena', b'1 ! ena', 1),
                'unknown-header': self.vcd.replace(b'$enddefinitions', b'$unknown $end\n$enddefinitions', 1),
            }.items():
                with self.subTest(name=name):
                    p.write_bytes(data)
                    with self.assertRaises(ValueError):
                        producer.validate_waveform(p, 1307)

    def test_provider_failure_publication(self):
        malformed = self.malformed_supported_capture()
        for mode in ('missing', 'empty', 'oversize', 'changed', 'execute-failed',
                     'inspection-failed', 'cancelled', 'good', *malformed):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=self.root) as directory:
                d = Path(directory)
                output = d / 'output'
                wave_dir = output / 'flops'
                wave_dir.mkdir(parents=True)
                wave = wave_dir / 'waveform.vcd'
                wave.write_bytes(self.vcd)
                producer.write(wave_dir / 'waveform.json', producer.validate_waveform(wave, 1307))
                (output / 'result-reference.json').write_text('{}')
                if mode == 'missing':
                    wave.unlink()
                elif mode == 'empty':
                    wave.write_bytes(b'')
                elif mode == 'oversize':
                    wave.write_bytes(b' ' * (8 * 1024 * 1024 + 1))
                elif mode == 'changed':
                    wave.write_bytes(self.vcd.replace(b'Icarus', b'ICARUS'))
                elif mode in malformed:
                    wave.write_bytes(malformed[mode])
                    # Rebind the actual changed bytes, so failure must come from
                    # supported-syntax admission, not merely a stale byte digest.
                    descriptor = json.loads((wave_dir / 'waveform.json').read_text())
                    descriptor['source'] = producer.ref(wave_dir, wave)
                    (wave_dir / 'waveform.json').write_text(json.dumps(descriptor))
                request = [('protocol_version', 1), ('attempt_id', 'focused'), ('selection', [
                    ('suite', provider.SUITE), ('cases', ['flops256']), ('seed', '34097'),
                    ('parameters', []), ('asic_inputs', [])])]
                (d / 'request').write_text(provider.sexp(request))
                args = argparse.Namespace(request=d / 'request', artifact_dir=d / 'artifacts',
                    events=d / 'events', generation=d, emitter=d, model_root=d, producer_root=d)
                with patch.object(provider, 'Runner') as runner, contextlib.redirect_stderr(io.StringIO()):
                    run = runner.return_value.run
                    run.return_value = (output, {}, mode != 'inspection-failed')
                    if mode == 'execute-failed':
                        run.side_effect = RuntimeError('vvp exit 1')
                    elif mode == 'cancelled':
                        run.side_effect = provider.Cancelled('cancelled')
                    code = provider.run(args)
                events = [dict(provider.parse(line))['payload'] for line in (d / 'events').read_text().splitlines()]
                waves = [e for e in events if isinstance(e, list) and e[0] == 'Artifact'
                         and dict(e[1])['kind'] == 'trace']
                self.assertEqual(len(waves), int(mode == 'good'))
                if mode == 'cancelled':
                    # Only FS2 may turn the accepted prefix into normalized
                    # Cancelled/Incomplete state; those are not provider finishes.
                    self.assertEqual(events, ['Started', ['Case_started', 'flops256']])
                else:
                    self.assertEqual(events[-1], ['Finished', 'Passed' if mode == 'good' else 'Failed'])
                self.assertEqual(code, 130 if mode == 'cancelled' else 0)
                if mode == 'inspection-failed':
                    artifacts = [dict(e[1]) for e in events if isinstance(e, list) and e[0] == 'Artifact']
                    self.assertEqual([a['kind'] for a in artifacts], ['json'])
                    self.assertTrue((d / 'artifacts/flops256-result-reference.json').is_file())
                    self.assertFalse((d / 'artifacts/flops256-waveform.vcd').exists())
                    finished = next(dict(e[1]) for e in events if isinstance(e, list) and e[0] == 'Case_finished')
                    self.assertEqual(finished['status'], 'Failed')
                    self.assertEqual(finished['message'], ['functional failure; inspect retained result'])


if __name__ == '__main__':
    unittest.main()
