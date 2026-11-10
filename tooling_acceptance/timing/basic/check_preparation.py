#!/usr/bin/env python3
"""Check the provider-independent PT.7 core and retain an exact new receipt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"scope": "provider-independent-hardware-preparation", "commands": [],
               "limits": {"dune_jobs": 6, "concurrent_builds_or_tools": 1},
               "sources": {str(p.relative_to(root)): sha(p)
                           for p in sorted((root / "tooling_acceptance/timing/fixture").rglob("*")) if p.is_file()},
               "assertions": [], "status": "started"}
    command = ["opam", "exec", "--switch=5.2.0+ox", "--", "flock",
               "/tmp/opencode/example-pt7-build.lock", "dune", "build",
               "--build-dir", "_build_pt7", "-j6", "tooling_acceptance/timing/fixture/verif/core_test.exe"]
    env = dict(os.environ)
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    for label, argv in (("build", command),
                        ("core", [str(root / "_build_pt7/default/tooling_acceptance/timing/fixture/verif/core_test.exe")])):
        result = subprocess.run(argv, cwd=root, env=env, capture_output=True, timeout=120)
        for suffix, data in (("stdout", result.stdout), ("stderr", result.stderr)):
            (args.output / f"{label}.{suffix}").write_bytes(data)
        receipt["commands"].append({"argv": argv, "exit_code": result.returncode})
        if result.returncode:
            receipt["status"] = "failed"
            break
    else:
        receipt["status"] = "pass"
        receipt["executable_sha256"] = sha(root / "_build_pt7/default/tooling_acceptance/timing/fixture/verif/core_test.exe")
        receipt["assertions"] = ["five scalar anchor callbacks in declaration order",
                                 "three-edge asynchronous-input capture latency",
                                 "two-edge synchronous-control latency",
                                 "five plain asynchronous-reset nodes: active-low, reset-to-zero",
                                 "Cyclesim reset clears empty and filled pipelines"]
    receipt["logs"] = {p.name: sha(p) for p in sorted(args.output.iterdir()) if p.is_file()}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(0 if receipt["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
