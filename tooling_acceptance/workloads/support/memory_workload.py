"""Directed memory workload, RTL replay and waveform validation."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import uuid

from command_receipts import sha, write, command


def ref(directory, path):
    return {'path': str(path.relative_to(directory)), 'sha256': sha(path),
            'bytes': path.stat().st_size}


def workload():
    ops = []
    def op(e, w, a, low=0):
        ops.append(dict(enable=bool(e), write=bool(w), address=a, data=(a << 8) | low))
    # Unknown initial reads/holds, and disabled writes before initialization.
    op(1, 0, 255); op(0, 1, 0, 255); op(0, 0, 127)
    for a in range(256):
        op(1, 1, a, (a * 73 + 0x5b) & 255)
    for n in range(256):
        a = (n * 73 + 19) & 255
        op(1, 0, a)
        op(0, 1, a, 0xff)  # must neither write nor disturb registered output
        op(0, 0, a ^ 255)
    for a in range(255, -1, -1):
        op(1, 0, a)
    # Rewrites on both sides of each capacity boundary, with immediate reads.
    for a in (0, 127, 128, 255, 0, 255):
        op(1, 1, a, 0x36); op(1, 0, a); op(0, 1, a, 0x99); op(1, 0, a)
    memory, known, expected = {}, None, []
    for o in ops:
        before = known
        if o['enable']:
            if o['write']:
                memory[o['address']] = o['data']
                known = None
            else:
                known = memory.get(o['address'])
        expected.append({'before': before, 'after': known})
    return {'protocol': 'memory-1rw-latency1-v1', 'seed': 0x8531,
            'depth': 256, 'width': 16, 'window': {'start': 0, 'stop': len(ops)},
            'operations': ops, 'expected': expected}


def identity(value):
    # Identity_json uses recursively sorted keys and compact JSON.
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def bench(ops, ignore_workload=False, capture_waveform=False):
    rows = []
    for n, o in enumerate(ops):
        data = 0 if ignore_workload else o['data'] & 255
        rows.append(f'    step({n}, 1\'b{int(o["enable"])}, 1\'b{int(o["write"])}, '
                    f'8\'d{o["address"]}, 8\'d{data});')
    return '''`timescale 1ns/1ps
module tb;
  reg clk=0, ena=0, rst_n=1;
  reg [7:0] ui_in=0, uio_in=0;
  wire [7:0] uo_out, uio_out, uio_oe;
  wire [15:0] q={uio_out,uo_out};
  reg [15:0] prior;
  tt_um_pt8_workload dut(.*);
  task step(input integer cycle, input e, input w, input [7:0] a, input [7:0] d);
  begin
    clk=0; ena=e; rst_n=~w; ui_in=a; uio_in=d;
    #4; prior=q;
    #1; clk=1;
    #4; $display("TRACE %0d %h %h", cycle, prior, q);
    #1; clk=0;
  end endtask
  initial begin
''' + ('''    $dumpfile("waveform.vcd");
    $dumpvars(0, tb.clk, tb.ena, tb.rst_n, tb.ui_in, tb.uio_in, tb.q);
''' if capture_waveform else '') + '\n'.join(rows) + '''
    $finish;
  end
endmodule
'''


def parse_trace(path, ops):
    def word(s):
        return None if any(c in s.lower() for c in 'xz') else int(s, 16)
    rows = []
    for line in path.read_text().splitlines():
        if line.startswith('TRACE '):
            _, n, before, after = line.split()
            n = int(n)
            rows.append({'cycle': n, 'input': ops[n],
                         'before': word(before), 'after': word(after)})
    assert len(rows) == len(ops)
    return {'rows': rows}


def counters(w, trace):
    rows = [r for r in trace['rows'] if w['window']['start'] <= r['cycle'] < w['window']['stop']]
    reads = sum(r['input']['enable'] and not r['input']['write'] for r in rows)
    writes = sum(r['input']['enable'] and r['input']['write'] for r in rows)
    defined = sum(w['expected'][r['cycle']][p] is not None for r in rows for p in ('before', 'after'))
    latency = 1 if any(r['input']['enable'] and not r['input']['write'] and
                      w['expected'][r['cycle']]['after'] is not None for r in rows) else None
    return dict(cycles=len(rows), reads=reads, writes=writes, operations=reads+writes,
                defined_observations=defined, read_latency=latency)


def validate_waveform(path, cycles):
    """Admit the six-signal Icarus dump protocol, not arbitrary VCD dialects."""
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 8 * 1024 * 1024:
        raise ValueError('missing, empty, nonregular or oversize waveform')
    text = path.read_text(encoding='ascii')
    expected = {'clk': 1, 'ena': 1, 'rst_n': 1, 'ui_in': 8, 'uio_in': 8, 'q': 16}
    tokens = iter(re.finditer(r'[^ \t\r\n]+', text))

    def next_token():
        match = next(tokens, None)
        if match is None:
            return None
        token = match[0]
        if len(token) > 8192 or any(not 33 <= ord(c) <= 126 for c in token):
            raise ValueError('unsupported waveform token')
        return token

    def required():
        token = next_token()
        if token is None:
            raise ValueError('truncated waveform')
        return token

    def directive_body():
        parts = []
        while True:
            token = required()
            if token == '$end':
                return parts
            if len(parts) >= 8192:
                raise ValueError('waveform directive token limit')
            parts.append(token)

    scope, declarations, codes = [], {}, {}
    scope_count, scale = 0, None
    while True:
        directive = required()
        parts = directive_body()
        if directive in ('$date', '$version', '$comment'):
            continue
        if directive == '$timescale':
            if scale is not None or parts not in (['1ps'], ['1', 'ps']):
                raise ValueError('waveform requires a single 1ps timescale')
            scale = '1ps'
        elif directive == '$scope':
            if scope or parts != ['module', 'tb']:
                raise ValueError('waveform scope must be top-level tb only')
            scope.append('tb')
            scope_count += 1
        elif directive == '$upscope':
            if parts or scope != ['tb']:
                raise ValueError('unbalanced waveform scope')
            scope.pop()
        elif directive == '$var':
            if scope != ['tb'] or len(parts) not in (4, 5):
                raise ValueError('malformed interface declaration')
            kind, width_text, code, name = parts[:4]
            if kind not in ('reg', 'wire') or not re.fullmatch(r'[0-9]+', width_text):
                raise ValueError('unsupported interface variable kind/width')
            width = int(width_text)
            if name not in expected or width != expected[name] or name in declarations or code in codes:
                raise ValueError('unexpected or duplicate interface declaration')
            # This instrumentation declares only scalars and descending zero-based
            # buses. Requiring its exact range also enforces viewer width agreement.
            ranges = [] if width == 1 else [f'[{width - 1}:0]']
            if parts[4:] != ranges:
                raise ValueError('interface range disagrees with declared width')
            declarations[name] = width
            codes[code] = width
        elif directive == '$enddefinitions':
            if parts or scope:
                raise ValueError('unclosed waveform scope/enddefinitions')
            break
        else:
            raise ValueError('unsupported waveform header directive')
    if declarations != expected or scope_count != 6 or scale != '1ps':
        raise ValueError('waveform is not the six-signal 1ps interface capture')
    timestamps, changes, values = [], 0, 0
    seen, in_dump = set(), False
    while (token := next_token()) is not None:
        if token == '$comment':
            directive_body()
            continue
        if token in ('$dumpvars', '$dumpall'):
            if in_dump:
                raise ValueError('nested waveform dump directive')
            in_dump = True
            continue
        if token == '$end':
            if not in_dump:
                raise ValueError('unexpected waveform end')
            in_dump = False
            continue
        if token.startswith('#'):
            if in_dump or not re.fullmatch(r'#[0-9]+', token):
                raise ValueError('invalid waveform timestamp')
            timestamp = int(token[1:])
            if timestamp > cycles * 10_000 or (timestamps and timestamp < timestamps[-1]):
                raise ValueError('nonmonotonic waveform time')
            timestamps.append(timestamp)
            continue
        scalar = re.fullmatch(r'([01xXzZ])(\S+)', token)
        vector = re.fullmatch(r'[bB]([01xXzZ]+)', token)
        if scalar:
            value, code = scalar.groups()
        elif vector:
            value, code = vector[1], required()
        else:
            raise ValueError('unsupported waveform change')
        if code not in codes or len(value) > codes[code]:
            raise ValueError('undeclared or overwidth waveform change')
        if scalar and codes[code] != 1:
            raise ValueError('scalar waveform assignment to a bus')
        seen.add(code)
        changes += 1
        values += codes[code]
        if changes > 500_000 or values > 64 * 1024 * 1024:
            raise ValueError('waveform exceeds viewer event/value limits')
    if (in_dump or seen != set(codes) or not timestamps or timestamps[0] != 0 or
            timestamps[-1] != cycles * 10_000 or changes <= cycles * 2):
        raise ValueError('incomplete waveform execution')
    return dict(source=ref(path.parent, path), signals=expected, changes=changes,
                timescale='1ps', last_time=timestamps[-1], cycles=cycles)


def simulate(output, label, emitted, w, ignored=False, alias=False, capture_waveform=False):
    directory = output / label
    directory.mkdir()
    bundle = Path(emitted['bundle'])
    manifest = json.loads((bundle / 'manifest.json').read_text())
    sources = manifest['synthesis_sources']
    # Bundle source descriptors inspected explicitly rather than guessing filenames.
    rtl = []
    for source in sources:
        p = bundle / (source if isinstance(source, str) else source['path'])
        dst = directory / p.name
        shutil.copyfile(p, dst)
        rtl.append(dst)
    tb = directory / 'testbench.v'
    tb.write_text(bench(w['operations'], ignored, capture_waveform=capture_waveform))
    model_paths = []
    if label.startswith('exact'):
        # Explicit stock vendor models, located from the selected macro collateral.
        model_root = Path(os.environ.get('PT8_VENDOR_MODEL_ROOT', '/nonexistent'))
        for name in ('RM_IHPSG13_1P_256x16_c2_bm_bist.v',
                     'RM_IHPSG13_1P_core_behavioral_bm_bist.v'):
            p = model_root / name
            dst = directory / p.name
            shutil.copyfile(p, dst)
            model_paths.append(dst)
        assert model_paths, 'stock macro functional Verilog models are required'
    else:
        model = directory / 'no-macro-model.txt'
        model.write_text('Flops uses only emitted implementation RTL; no external primitive model.\n')
        model_paths.append(model)
    command(directory, 'iverilog-version', ['iverilog', '-V'])
    command(directory, 'vvp-version', ['vvp', '-V'])
    settings = directory / 'tool.json'
    write(settings, {'iverilog': shutil.which('iverilog'), 'vvp': shutil.which('vvp'),
        'iverilog_sha256': sha(Path(shutil.which('iverilog'))),
        'vvp_sha256': sha(Path(shutil.which('vvp'))), 'flags': ['-g2012', '-DFUNCTIONAL', '-s', 'tb'],
        'timescale': '1ns/1ps', 'period_ns': 10, 'before_ns': 4, 'edge_ns': 5,
        'after_ns': 9, 'initialization': 'none', 'max_parallel_processes': 1,
        'iverilog_version_stdout': (directory / 'iverilog-version/stdout.log').read_text(),
        'vvp_version_stderr': (directory / 'vvp-version/stderr.log').read_text()})
    command(directory, 'compile', ['iverilog', '-g2012', '-DFUNCTIONAL', '-s', 'tb', '-o', directory / 'sim.vvp',
        *rtl, *[p for p in model_paths if p.suffix == '.v'], tb])
    # The relative dumpfile belongs to the actual simulator cwd, never the caller.
    raw = command(directory, 'execute', ['vvp', directory / 'sim.vvp'],
                  **({'cwd': directory} if capture_waveform else {}))
    if capture_waveform:
        write(directory / 'waveform.json', validate_waveform(directory / 'waveform.vcd', len(w['operations'])))
    trace = parse_trace(raw, w['operations'])
    mismatches = [{'cycle': r['cycle'], 'phase': p, 'expected': w['expected'][r['cycle']][p],
                   'actual': r[p]} for r in trace['rows'] for p in ('before', 'after')
                  if w['expected'][r['cycle']][p] is not None and
                  w['expected'][r['cycle']][p] != r[p]]
    write(directory / 'oracle-check.json', {'mismatches': mismatches, 'pass': not mismatches})
    assert bool(mismatches) == (ignored or alias), (label, mismatches[:3])
    write(directory / 'trace.json', trace)
    write(directory / 'stimulus.json', {'operations': w['operations']})
    write(directory / 'expected.json', {'expected': w['expected']})
    artifacts = ([{'role': 'rtl', 'source': ref(directory, p)} for p in rtl] +
                 [{'role': 'model', 'source': ref(directory, p)} for p in model_paths] +
                 [{'role': 'testbench', 'source': ref(directory, tb)},
                  {'role': 'tool', 'source': ref(directory, settings)}])
    simulation = dict(contract='hardcaml-asic.workload-simulation', schema_version=1,
        attempt_id=label + '-' + uuid.uuid4().hex, status='completed',
        bundle_identity=emitted['bundle_identity'],
        hardware_variant_identity=emitted['hardware_variant']['identity'],
        workload_identity=w['identity'], stimulus=ref(directory, directory / 'stimulus.json'),
        trace=ref(directory, directory / 'trace.json'), rtl_mode='implementation', artifacts=artifacts,
        adapter='memory-1rw-latency1-v1', clock='posedge-single-clock-v1',
        model='memory-1rw-undefined-init-write-hold-v1', measurement='memory-1rw-window-v1')
    write(directory / 'simulation.json', simulation)
    write(directory / 'result.json', dict(contract='hardcaml-asic.workload-result', schema_version=1,
        bundle=str(bundle), workload=w, simulation=ref(directory, directory / 'simulation.json'),
        stimulus=simulation['stimulus'], trace=simulation['trace'], counters=counters(w, trace)))


