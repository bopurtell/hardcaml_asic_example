#!/usr/bin/env python3
"""Package a finalized evidence capture and verify/replay the actual restored archive."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "verif"))
from complete_physical import seal
from physical_records import load, require, sha
from replay_snapshot import replay, verify


def package(root, archive, proof):
    root, archive, proof = root.resolve(), archive.resolve(), proof.resolve()
    require(not archive.exists() and not proof.exists(), "archive/proof outputs must be fresh")
    require(not archive.is_relative_to(root) and not proof.is_relative_to(root), "archive/proof must be outside evidence")
    verify(root)
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])
    sources = {r["path"]: r["source"] for r in load(root / "checksums.json") if "source" in r}
    summary = load(root / "summary.json")
    runroot = Path(summary["run_root"])
    results = load(runroot / "results.json")
    require(results["run_id"] == summary["run_id"] and results["build_identity"] == summary["bundle_identity"]
            and results["process_status"] == "completed" and results["errors"] == []
            and results["timing_goal"] == "pass", "public collection binding/errors/timing")
    require(all(results["checks"][key]["status"] == "pass" for key in
                ("drc", "lvs", "antenna", "max_slew", "max_cap")), "public collection checks")
    additions = {"results.json": runroot / "results.json", "execution.log": runroot / "execution.log",
                 "physical-checks.log": runroot / "physical-checks.log",
                 "metrics.csv": runroot / "project/runs/asic/final/metrics.csv"}
    before = {str(path): sha(path) for path in additions.values()}
    for name, source in additions.items():
        require(not (root / name).exists(), "additional public evidence already exists")
        shutil.copyfile(source, root / name)
        sources[name] = str(source)
    for name, source in (("README.md", Path(__file__).with_name("EVIDENCE.md")),
                         ("verify.py", Path(__file__).resolve().parents[3] / "acceptance/sram/verify.py")):
        require(not (root / name).exists(), "new portable file already exists")
        shutil.copyfile(source, root / name)
        sources[name] = str(source)
    seal(root, sources)
    inventory_hash = verify(root)
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname=root.name)
    archive_hash = sha(archive)
    with tempfile.TemporaryDirectory(prefix="sram-final-archive-", dir="/tmp/opencode") as tmp:
        work = Path(tmp)
        with tarfile.open(archive) as tar:
            tar.extractall(work, filter="data")
        restored = work / root.name
        require(verify(restored) == inventory_hash, "restored final archive inventory mismatch")
        result = replay(restored, work / "replay")
        shutil.copytree(work / "replay", proof, ignore=shutil.ignore_patterns("gate.vvp"))
    require(sha(archive) == archive_hash and verify(root) == inventory_hash, "archive/snapshot changed")
    require(all(sha(Path(path)) == digest for path, digest in before.items()), "original public record changed")
    records = load(root / "checksums.json")
    receipt = {"scope": "final_archive_restore_and_portable_positive_negative_gate_replay",
               "archive": str(archive), "archive_sha256": archive_hash, "archive_bytes": archive.stat().st_size,
               "evidence_files": len(records), "evidence_bytes": sum(r["bytes"] for r in records),
               "restored_inventory_sha256": inventory_hash, "word_checks": result["word_checks"],
               "negative_oracle_rejected": result["negative_oracle_rejected"], "original_snapshot_unchanged": True,
               "additional_public_sources_unchanged_sha256": before}
    (proof / "summary.json").write_text(json.dumps(receipt, indent=2) + "\n")
    seal(proof, {})
    verify(proof)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--proof-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.evidence_dir, args.archive, args.proof_dir), indent=2))
