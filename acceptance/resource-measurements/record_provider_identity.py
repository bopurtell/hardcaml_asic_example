#!/usr/bin/env python3
"""Retain final provider dispatcher AND native companion byte identities."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    focused = json.loads(args.focused.read_text())
    generation = Path(focused["provider_receipt"]["generation"])
    dispatcher = focused["executable_ids"]["provider"]
    assert sha(Path(dispatcher["path"])) == dispatcher["sha256"]
    entries = {str(p.relative_to(generation)): sha(p) for p in sorted((generation / "bin").iterdir()) if p.is_file()}
    result = dict(scope="final installed provider binary identities; no execution/build",
                  generation=str(generation), focused_receipt_sha256=sha(args.focused),
                  provider_receipt=focused["provider_receipt"], binaries=entries,
                  explanation="dispatcher hash can be unchanged across source captures; native companions carry feature implementation")
    with args.receipt.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
