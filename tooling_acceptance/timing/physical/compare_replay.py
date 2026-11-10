#!/usr/bin/env python3
"""Compare two public JSON responses without interpreting timing facts."""
import argparse
import json
from pathlib import Path

from commands import STORE, identity, write_new


def differences(a, b, path='$'):
    if type(a) is not type(b):
        return [{'path': path, 'original': a, 'restored': b}]
    if isinstance(a, dict):
        rows = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                rows.append({'path': path + '.' + key, 'original': a.get(key), 'restored': b.get(key)})
            else:
                rows.extend(differences(a[key], b[key], path + '.' + key))
        return rows
    if isinstance(a, list):
        if len(a) != len(b):
            if all(isinstance(x, str) for x in a + b):
                return [{'path': path, 'missing_from_restore': sorted(set(a) - set(b)),
                         'only_in_restore': sorted(set(b) - set(a))}]
            return [{'path': path, 'original_length': len(a), 'restored_length': len(b)}]
        return [row for i, (x, y) in enumerate(zip(a, b)) for row in differences(x, y, path + f'[{i}]')]
    return [] if a == b else [{'path': path, 'original': a, 'restored': b}]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--restored', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert a.output.resolve().is_relative_to(STORE)
    rows = differences(json.loads(a.original.read_text()), json.loads(a.restored.read_text()))
    write_new(a.output, {'original': identity(a.original), 'restored': identity(a.restored), 'differences': rows})
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
