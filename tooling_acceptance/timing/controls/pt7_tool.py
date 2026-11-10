#!/usr/bin/env python3
"""Bounded PT.7 tools; receipts only, no timing interpretation.

Run sequentially with builds: the caller owns the six-job allocation. Every
invocation takes a global PT.7 tool lock, including synthesis and version probes.
Only a new output directory is accepted; failed/timeout attempts are retained.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


IMAGE = "sha256:d109140b8f17fc54f4fca998beb8124f4949404ec52e339eebd2250854a18b5a"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(path):
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"input is not a regular file: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", choices=("yosys", "openroad", "sta"), required=True)
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--work", type=Path, required=True,
                        help="existing writable PT.7 scratch directory")
    parser.add_argument("--output", type=Path, required=True, help="new receipt directory")
    parser.add_argument("--read-only", type=Path, action="append", default=[])
    parser.add_argument("--input", type=Path, action="append", required=True,
                        help="each actual script/SDC/netlist/Liberty input, repeatable")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        parser.error("--image must be an exact local image ID")
    if not 1 <= args.timeout <= 600:
        parser.error("--timeout must be between 1 and 600 seconds")
    work = args.work.resolve(strict=True)
    if not work.is_dir():
        parser.error("--work must be an existing directory")
    mounts = [p.resolve(strict=True) for p in args.read_only]
    # Avoid giving the container a writable view of the provider or old evidence.
    root = Path(__file__).resolve().parents[3]
    scratch = root / ".dev/asic-pt7"
    if not work.is_relative_to(scratch) or work == scratch:
        parser.error("--work must be a child of .dev/asic-pt7")
    inputs = [identity(p) for p in args.input]
    for record in inputs:
        path = Path(record["path"])
        if not path.is_relative_to(work) and not any(
                path == m or path.is_relative_to(m) for m in mounts):
            parser.error(f"input has no container mount: {path}")
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    # One tool thread and one CPU leave room for bounded ancillary processes.
    command = ["docker", "run", "--rm", "--pull=never", "--network=none",
               "--read-only", "--cpus=1", "--memory=4g", "--pids-limit=128",
               "--user", f"{os.getuid()}:{os.getgid()}",
               "--tmpfs", "/tmp:rw,nosuid,size=256m",
               "--mount", f"type=bind,src={work},dst={work}", "--workdir", str(work)]
    for mount in mounts:
        command += ["--mount", f"type=bind,src={mount},dst={mount},readonly"]
    for variable in ("OMP_NUM_THREADS", "OPENROAD_THREADS", "OPENBLAS_NUM_THREADS",
                     "MKL_NUM_THREADS", "_OPENLANE_MAX_CORES"):
        command += ["--env", variable + "=1"]
    command += ["--entrypoint", args.tool, args.image]
    if args.tool == "openroad" and arguments != ["-version"]:
        command += ["-threads", "1"]
    if args.tool == "sta" and arguments not in (["-version"], ["-help"]):
        command += ["-threads", "1"]
    command += arguments
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": 1, "scope": "pt7-tool-launch-only",
               "status": "prepared", "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "argv": command, "inputs_before": inputs, "timeout_seconds": args.timeout,
               "limits": {"container_cpus": 1, "tool_threads": 1, "memory_bytes": 4294967296,
                          "pids": 128, "serialized_tools": True},
               "launcher": identity(Path(__file__)), "dry_run": args.dry_run}
    receipt_path = args.output / "launch.json"
    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    save()
    if args.dry_run:
        return
    with Path("/tmp/opencode/example-pt7-sta.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        started = time.monotonic()
        # Hash again after waiting for the lock; fail before consuming changed inputs.
        if inputs != [identity(Path(r["path"])) for r in inputs]:
            receipt["status"] = "inputs-changed-before-launch"
            save()
            raise SystemExit(1)
        name = "asic-example-pt7-" + str(os.getpid())
        command[2:2] = ["--name", name]
        try:
            with (args.output / "stdout.log").open("wb") as out, (args.output / "stderr.log").open("wb") as err:
                result = subprocess.run(command, stdout=out, stderr=err, timeout=args.timeout)
            receipt.update(status="completed", exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            # Killing docker's client alone would leave the tool using the allocation.
            cleanup = subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            (args.output / "cleanup.stdout").write_bytes(cleanup.stdout)
            (args.output / "cleanup.stderr").write_bytes(cleanup.stderr)
            receipt.update(status="timeout", exit_code=124, cleanup_exit_code=cleanup.returncode)
        except OSError as exc:
            receipt.update(status="launch-failed", exit_code=127, error=str(exc))
        finally:
            receipt["elapsed_seconds"] = time.monotonic() - started
            receipt["inputs_after"] = [identity(Path(r["path"])) for r in inputs]
            receipt["inputs_unchanged"] = receipt["inputs_after"] == inputs
            save()
    raise SystemExit(receipt["exit_code"] if receipt["inputs_unchanged"] else 1)


if __name__ == "__main__":
    main()
