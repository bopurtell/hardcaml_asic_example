#!/usr/bin/env python3
"""Replay a retained physical snapshot using only its files and installed Icarus.

Writes only a fresh output directory. Positive replay and corrupted expected data
must respectively exit 0/1; input/checksum bytes are checked before and afterward.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root):
    inventory = json.loads((root / "checksums.json").read_text())
    expected = {entry["path"] for entry in inventory}
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    if len(expected) != len(inventory) or actual != expected | {"checksums.json"}:
        raise RuntimeError("incomplete snapshot inventory")
    for entry in inventory:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise RuntimeError("snapshot changed: " + entry["path"])
    return digest(root / "checksums.json")


def replay(root, output):
    root, output = root.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(root):
        raise RuntimeError("replay output must be fresh and outside snapshot")
    inventory_hash = verify(root)
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])
    summary = json.loads((root / "summary.json").read_text())
    post = root / "postchecks" / summary["postcheck_ids"][0]
    inputs = [post / "testbench.v", root / "mapped.v", *[post / f"model-{i}.v" for i in range(3)],
              post / "stdcell-functional.v"]
    original_hashes = {str(p.relative_to(root)): digest(p) for p in inputs}
    output.mkdir()
    commands = []

    def run(label, argv, expected):
        result = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=120,
                                env={**os.environ, "OMP_NUM_THREADS": "4"})
        (output / (label + ".stdout")).write_text(result.stdout)
        (output / (label + ".stderr")).write_text(result.stderr)
        commands.append({"argv": list(map(str, argv)), "exit_code": result.returncode,
                         "expected_exit_code": expected, "stdout": label + ".stdout", "stderr": label + ".stderr"})
        if result.returncode != expected:
            raise RuntimeError(f"{label}: expected exit {expected}, got {result.returncode}")
        return result

    run("iverilog-version", ["iverilog", "-V"], 0)
    run("vvp-version", ["vvp", "-V"], 0)
    executable = output / "gate.vvp"
    run("compile", ["iverilog", "-g2012", "-DFUNCTIONAL", "-DSIM", "-s", "memory_replay",
                    "-o", executable, *inputs], 0)
    positive = run("positive", ["vvp", "-n", executable], 0)
    negative = run("negative", ["vvp", "-n", executable, "+negative"], 1)
    if "checks=1280" not in positive.stdout or "low byte addr=19 expected=" not in negative.stdout:
        raise RuntimeError("replay did not reach expected positive/negative oracle")
    if verify(root) != inventory_hash or any(digest(root / name) != value for name, value in original_hashes.items()):
        raise RuntimeError("snapshot/input changed during replay")
    receipt = {"scope": "snapshot_only_zero_delay_gate_functional", "word_checks": 1280,
               "negative_oracle_rejected": True, "input_sha256": original_hashes,
               "snapshot_inventory_sha256": inventory_hash, "snapshot_unchanged": True,
               "cpu_affinity_max": 4, "commands": commands}
    (output / "replay.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.snapshot, args.output_dir), indent=2))
