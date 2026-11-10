"""Standalone FS2v1 codec; event shape adapted from hardcaml_workbench's
demo/synthetic_flow/simulation_wire.py and protocol/simulation.ml (2026-10-17).
No Workbench imports. Parsing rejects unconsumed bytes and duplicate record keys.
"""
import json
import re


def sexp(value):
    if isinstance(value, (list, tuple)):
        return '(' + ' '.join(map(sexp, value)) + ')'
    return json.dumps(str(value), ensure_ascii=False)


def parse(text):
    pos = 0

    def item():
        nonlocal pos
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos == len(text):
            raise ValueError('truncated S-expression')
        if text[pos] == '(':
            pos += 1
            out = []
            while True:
                while pos < len(text) and text[pos].isspace():
                    pos += 1
                if pos == len(text):
                    raise ValueError('unclosed list')
                if text[pos] == ')':
                    pos += 1
                    return out
                out.append(item())
        if text[pos] == '"':
            pos += 1
            out = bytearray()
            while pos < len(text):
                c = text[pos]
                pos += 1
                if c == '"':
                    return out.decode('utf-8', 'strict')
                if c == '\\':
                    if pos == len(text):
                        raise ValueError('truncated escape')
                    c = text[pos]
                    pos += 1
                    escapes = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', '\\': '\\', '"': '"'}
                    if c in escapes:
                        out.extend(escapes[c].encode())
                    elif c.isascii() and c.isdigit():
                        digits = c + text[pos:pos + 2]
                        if not re.fullmatch('[0-9]{3}', digits) or int(digits) > 255:
                            raise ValueError('invalid decimal escape')
                        pos += 2
                        out.append(int(digits))
                    else:
                        raise ValueError('invalid escape')
                else:
                    out.extend(c.encode())
            raise ValueError('unclosed string')
        match = re.match(r'[^\s()";]+', text[pos:])
        if not match:
            raise ValueError('invalid atom')
        pos += len(match[0])
        return match[0]

    value = item()
    if text[pos:].strip():
        raise ValueError('trailing data')
    return value


def record(value, keys):
    if not isinstance(value, list):
        raise ValueError('expected record')
    out = {}
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str) or pair[0] in out:
            raise ValueError('invalid or duplicate record field')
        out[pair[0]] = pair[1]
    if set(out) != set(keys):
        raise ValueError('unexpected record fields')
    return out


class Events:
    def __init__(self, stream, attempt):
        self.stream, self.attempt, self.sequence = stream, attempt, 0

    def emit(self, payload):
        self.stream.write(sexp([('protocol_version', 1), ('attempt_id', self.attempt),
                                ('sequence', self.sequence), ('payload', payload)]) + '\n')
        self.stream.flush()
        self.sequence += 1

    def progress(self, case, completed, total):
        self.emit(['Progress', [('case_id', [case]), ('completed', completed),
                               ('total', [total]), ('unit_', 'FIFO edges')]])

    def artifact(self, case, path, kind, media):
        self.emit(['Artifact', [('id', path), ('case_id', [case]), ('label', path),
                               ('kind', kind), ('media_type', media), ('path', path)]])
