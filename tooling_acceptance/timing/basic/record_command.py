#!/usr/bin/env python3
"""Retain one command attempt, including failure, in a new directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--generation", type=Path)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("argv", nargs=argparse.REMAINDER)
    a = p.parse_args()
    argv = a.argv[1:] if a.argv[:1] == ["--"] else a.argv
    a.output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    receipt = {"argv": argv, "cwd": os.getcwd(), "generation": None}
    if a.generation:
        generation = a.generation.resolve(strict=True)
        receipt["generation"] = str(generation)
        receipt["provider_receipt_sha256"] = sha(generation / "receipt.json")
        env["OCAMLPATH"] = str(generation / "lib") + (":" + env["OCAMLPATH"] if env.get("OCAMLPATH") else "")
        env["PATH"] = str(generation / "bin") + ":" + env["PATH"]
        env["HARDCAML_ASIC_TEST_PROVIDER"] = str(generation / "bin/hardcaml-asic-flow")
    start = time.monotonic()
    with (a.output / "stdout.log").open("wb") as out, (a.output / "stderr.log").open("wb") as err:
        try:
            result = subprocess.run(argv, stdout=out, stderr=err, env=env, timeout=a.timeout)
            receipt["exit_code"] = result.returncode
        except subprocess.TimeoutExpired:
            receipt["exit_code"] = 124
    receipt["elapsed_seconds"] = time.monotonic() - start
    receipt["logs"] = {name: sha(a.output / name) for name in ("stdout.log", "stderr.log")}
    (a.output / "command.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    raise SystemExit(receipt["exit_code"])


if __name__ == "__main__":
    main()
