#!/usr/bin/env python3
"""Verify the complete checksum inventory of a retained SRAM evidence snapshot."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    root = args.snapshot.resolve()
    entries = json.loads((root / "checksums.json").read_text())
    expected = {entry["path"] for entry in entries}
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    if len(expected) != len(entries) or actual != expected | {"checksums.json"}:
        raise RuntimeError("duplicate, missing or unexpected evidence files")
    for entry in entries:
        path = root / entry["path"]
        if not path.resolve().is_relative_to(root):
            raise RuntimeError("evidence path escapes snapshot")
        contents = path.read_bytes()
        if len(contents) != entry["bytes"] or hashlib.sha256(contents).hexdigest() != entry["sha256"]:
            raise RuntimeError("checksum/size mismatch: " + entry["path"])
    print(f"PASS {len(entries)} evidence files, {sum(e['bytes'] for e in entries)} bytes; complete SHA-256 inventory")


if __name__ == "__main__":
    main()
