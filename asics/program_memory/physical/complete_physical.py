#!/usr/bin/env python3
"""Finalize a NEW physical evidence capture with replay controls and compact history.

Never changes retained runs/bundles. Executes only Icarus/vvp (four CPUs), not EDA.
The current provider executable runs read-only in its recorded, already-local image.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "verif"))
from physical_records import load, require, sha
import replay_snapshot
from replay_snapshot import replay, verify


def seal(root, sources):
    records = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != root / "checksums.json":
            relative = str(path.relative_to(root))
            record = {"path": relative, "bytes": path.stat().st_size, "sha256": sha(path)}
            if relative in sources:
                record["source"] = sources[relative]
            records.append(record)
    (root / "checksums.json").write_text(json.dumps(records, indent=2) + "\n")


def complete(root, workspace):
    root, workspace = root.resolve(), workspace.resolve()
    verify(root)
    require(not (root / "supplemental").exists(), "supplemental evidence must be new")
    original = load(root / "checksums.json")
    sources = {r["path"]: r["source"] for r in original if "source" in r}
    # Hash original run/PDK/bundle artifacts before and after every replay.
    before = {name: sha(Path(name)) for name in set(sources.values())}
    summary = load(root / "summary.json")
    runroot = Path(summary["run_root"])
    check = runroot / "checks" / summary["postcheck_ids"][0]
    postcheck = load(check / "postcheck.json")
    gate = check / "gate.out"
    before[str(gate)] = sha(gate)
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])
    supplemental = root / "supplemental"
    supplemental.mkdir()
    negative_dir = supplemental / "current-compiled"
    negative_dir.mkdir()
    image = postcheck["tools"]["simulator_image"]
    command = ["docker", "run", "--rm", "--pull=never", "--cpus=4", "--network=none", "--read-only",
               "--user", f"{os.getuid()}:{os.getgid()}", "--mount", f"type=bind,src={runroot},dst={runroot},readonly",
               "--entrypoint", "vvp", image, "-n", str(gate), "+negative"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (negative_dir / "negative.stdout").write_text(result.stdout)
    (negative_dir / "negative.stderr").write_text(result.stderr)
    require(result.returncode == 1 and "low byte addr=19 expected=" in result.stdout,
            "current compiled gate did not reject corrupted expected low byte")
    receipt = {"scope": "original_public_postcheck_compiled_gate_negative_oracle",
               "argv": command, "exit_code": result.returncode, "expected_exit_code": 1,
               "gate_out_sha256": before[str(gate)], "testbench_sha256": sha(check / "testbench.v"),
               "final_netlist_sha256": postcheck["inputs"]["netlist_sha256"], "cpu_limit": 4}
    (negative_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")

    attempts = []
    for label, dirname, bundle_name, generation in (
        ("p1", "20261025T010527676274Z_9c439718", "program-memory-exact-physical-p1", "dd1ac48f0f5c4f03ae4580edb722ce47"),
        ("p2", "20261025T011729961662Z_79df6b00", "program-memory-exact-physical-p2", "5ce7fdbb5a1443b89943d35946eb168d"),
        ("p3", "20261025T023413976323Z_cf909599", "program-memory-exact-physical-p3", "bd7bf3ff861a48a5bf3df6a50b2a1f93"),
    ):
        run = workspace / "_flow_results/sram-physical/runs" / dirname
        record = load(run / "run.json")
        require(record["status"] == "failed", "historical failed run must remain failed")
        bundle = workspace / ".dev" / bundle_name
        manifest = load(bundle / "manifest.json")
        require(record["build_identity"] == manifest["identity"], "failed attempt bundle binding")
        destination = root / "failed-attempts" / label

        def retain(source, relative):
            require(source.is_file(), "missing historical source: " + str(source))
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            require(sha(source) == sha(target), "historical source/copy mismatch")
            sources[str(target.relative_to(root))] = str(source)
            before[str(source)] = sha(source)

        retain(run / "run.json", "run.json")
        retain(run / "preflight.json", "preflight.json")
        retain(bundle / "manifest.json", "bundle/manifest.json")
        for item in manifest["files"]:
            require(sha(bundle / item["path"]) == item["sha256"], "historical bundle inventory changed")
            retain(bundle / item["path"], "bundle/" + item["path"])
        retain(workspace / ".dev/asic-sram/generations" / generation / "receipt.json", "provider-receipt.json")
        flow = run / "project/runs/asic"
        for name in ("execution.log", "physical-checks.log", "results.json"):
            if (run / name).is_file():
                retain(run / name, name)
        for name in ("physical-runtime.py", "macro-flow.py"):
            if (run / "project" / name).is_file():
                retain(run / "project" / name, "runtime/" + name)
        for name in ("error.log", "warning.log", "flow.log", "resolved.json", "final/metrics.json", "final/metrics.csv"):
            if (flow / name).is_file():
                retain(flow / name, "flow/" + name)
        for pattern in ("*-openroad-generatepdn/*.log", "*-netgen-lvs/netgen-lvs.log", "*-netgen-lvs/lvs_script.lvs",
                        "*-netgen-lvs/lvs-reader.json", "*-netgen-lvs/reports/*", "*-magic-drc/reports/drc.magic.rpt",
                        "*-klayout-drc/reports/drc.klayout.json"):
            for source in flow.glob(pattern):
                if source.is_file():
                    retain(source, "flow/" + str(source.relative_to(flow)))
        final_hashes = {str(p.relative_to(flow)): sha(p) for pattern in ("final/gds/*", "final/nl/*")
                        for p in flow.glob(pattern) if p.is_file()}
        attempts.append({"attempt": label, "run_id": record["run_id"], "status": record["status"],
                         "bundle_identity": record["build_identity"], "original_run": str(run),
                         "final_artifacts_not_duplicated_sha256": final_hashes})
    (root / "failed-attempts/chronology.json").write_text(json.dumps(attempts, indent=2) + "\n")
    for name in ("replay_snapshot.py", "complete_physical.py"):
        source = (Path(replay_snapshot.__file__) if name == "replay_snapshot.py"
                  else Path(__file__).with_name(name))
        shutil.copyfile(source, root / name)
        sources[name] = str(source)
    # Seal the capture before a tar/restore test, so the portable replay itself
    # can verify a complete inventory without consulting any absolute source path.
    seal(root, sources)
    with tempfile.TemporaryDirectory(prefix="sram-portable-", dir="/tmp/opencode") as tmp:
        work = Path(tmp)
        archive = work / "snapshot.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(root, arcname="physical-p4")
        restored = work / "restored"
        restored.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(restored, filter="data")
        replayed = replay(restored / "physical-p4", work / "replay")
        portable = supplemental / "portable-replay"
        shutil.copytree(work / "replay", portable, ignore=shutil.ignore_patterns("gate.vvp"))
        restoration = {"archive_sha256": sha(archive), "tested_inventory_sha256": replayed["snapshot_inventory_sha256"],
                       "scope": "pre-finalization_capture_tar_restore_and_snapshot_only_replay",
                       "word_checks": replayed["word_checks"], "negative_oracle_rejected": True,
                       "inputs_sha256": replayed["input_sha256"], "restored_inventory_verified": True}
        (supplemental / "restoration.json").write_text(json.dumps(restoration, indent=2) + "\n")
    unchanged = {name: value for name, value in before.items() if sha(Path(name)) == value}
    require(len(unchanged) == len(before), "original run/PDK/bundle artifact changed")
    (supplemental / "original-artifacts-unchanged.json").write_text(json.dumps(
        {"status": "pass", "before_sha256": before, "after_sha256": unchanged}, indent=2) + "\n")
    metrics = load(root / "metrics.json")
    cell_types = Counter(re.findall(r"\b(sg13cmos5l_\w+|RM_IHPSG13_\w+)\s+(?:\\\S+|\w+)\s*\(", (root / "mapped.v").read_text()))
    summary.update({"final_cell_types": dict(sorted(cell_types.items())), "final_cell_count": sum(cell_types.values()),
                    "timing_ns": {"setup_worst": metrics["timing__setup__ws"], "hold_worst": metrics["timing__hold__ws"]},
                    "supplemental_negative_oracle": "supplemental/current-compiled/receipt.json",
                    "portable_replay": "supplemental/portable-replay/replay.json",
                    "restoration": "supplemental/restoration.json", "failed_attempts": attempts,
                    "not_established": ["internal-device LVS", "IR/EM adequacy", "SDF/timed SRAM conformance"]})
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    seal(root, sources)
    verify(root)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(complete(args.evidence_dir, args.workspace), indent=2))
