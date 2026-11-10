#!/usr/bin/env python3
"""Independent, bounded native API probes; no provider evidence interpretation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
IMAGE = "sha256:d109140b8f17fc54f4fca998beb8124f4949404ec52e339eebd2250854a18b5a"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--label", required=True)
    p.add_argument("--script", type=Path, required=True)
    p.add_argument("--state", type=Path)
    p.add_argument("--producer", type=Path)
    p.add_argument("--reference", type=Path, default=ROOT / "acceptance/timing/sta-scalar-r3")
    p.add_argument("--tool", choices=("sta", "openroad", "python3"), default="sta")
    a = p.parse_args()
    work = ROOT / ".dev/asic-pt7c" / a.label
    output = ROOT / "acceptance/pt7c" / a.label
    work.mkdir(parents=True, exist_ok=False)
    output.mkdir(parents=True, exist_ok=False)
    script = a.script.resolve(strict=True)
    old = a.reference.resolve(strict=True)
    libraries = [old / "cells.lib"] if (old / "cells.lib").exists() else sorted(old.glob("library-*.lib"))
    inputs = [script, old / "mapped.v", old / "top.sdc", *libraries]
    before = {str(path): digest(path) for path in inputs}
    command = ["docker", "run", "--rm", "--name", "pt7c-probe-" + str(os.getpid()),
               "--pull=never", "--network=none", "--read-only", "--cpus=1", "--memory=4g",
               "--pids-limit=128", "--user", f"{os.getuid()}:{os.getgid()}",
               "--tmpfs", "/tmp:rw,nosuid,size=256m", "--workdir", str(work),
               "--mount", f"type=bind,src={work},dst={work}",
               "--mount", f"type=bind,src={old},dst=/old,readonly",
               "--mount", f"type=bind,src={script},dst=/probe.tcl,readonly"]
    for name in ("OMP_NUM_THREADS", "OPENROAD_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "_OPENLANE_MAX_CORES"):
        command += ["--env", name + "=1"]
    for source, destination in ((a.state, "/state.sdc"), (a.producer, "/producer.tcl")):
        if source:
            source = source.resolve(strict=True)
            inputs.append(source)
            command += ["--mount", f"type=bind,src={source},dst={destination},readonly"]
    before = {str(path): digest(path) for path in inputs}
    command += ["--entrypoint", a.tool, IMAGE]
    if a.tool == "python3":
        command += ["/probe.tcl"]
    else:
        command += ["-threads", "1"]
        command += (["-no_init"] if a.tool == "sta" else []) + ["-exit", "/probe.tcl"]
    receipt = {"schema": 1, "argv": command, "inputs_before": before,
               "limits": {"cpus": 1, "threads": 1, "pids": 128, "timeout_seconds": 180}}
    (output / "probe.tcl").write_bytes(script.read_bytes())
    with Path("/tmp/opencode/example-pt7-sta.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        start = time.monotonic()
        try:
            with (output / "stdout.log").open("wb") as out, (output / "stderr.log").open("wb") as err:
                result = subprocess.run(command, stdout=out, stderr=err, timeout=180)
            receipt["exit_code"] = result.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", "pt7c-probe-" + str(os.getpid())], check=False, timeout=30)
            receipt["exit_code"] = 124
        receipt["elapsed_seconds"] = time.monotonic() - start
    receipt["inputs_after"] = {str(path): digest(path) for path in inputs}
    receipt["inputs_unchanged"] = receipt["inputs_after"] == before
    for path in work.iterdir():
        if path.is_file():
            (output / path.name).write_bytes(path.read_bytes())
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(receipt["exit_code"] if receipt["inputs_unchanged"] else 1)


if __name__ == "__main__":
    main()
