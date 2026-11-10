#!/usr/bin/env python3
"""Retain a correction-round receipt without relabelling failures as acceptance."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
from real_tools import ROOT, EVIDENCE, dump
from record_command import sha


def identity(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generation", type=Path, required=True)
    p.add_argument("--round", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    generation = a.generation.resolve(strict=True)
    a.output.mkdir()
    old = json.loads((EVIDENCE / "closeout-01/checksums.json").read_text())
    for f in old["files"]:
        assert sha(EVIDENCE / f["path"]) == f["sha256"], f["path"]
    dump(a.output / "prior-evidence-verification.json", {"status": "pass", "checked_files": len(old["files"]),
         "baseline": "closeout-01/checksums.json", "baseline_sha256": sha(EVIDENCE / "closeout-01/checksums.json")})
    shutil.copyfile(generation / "receipt.json", a.output / "provider-receipt.json")
    for name in ("pt7-library-handoff.md", "pt7-evidence-handoff.md"):
        shutil.copyfile(ROOT.parent / "hardcaml_asic/docs/development" / name, a.output / name)
    sources = a.output / "consumer-sources"
    sources.mkdir()
    for path in sorted((ROOT / "tooling_acceptance/timing").rglob("*")):
        if path.is_file():
            target = sources / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    shutil.copyfile(ROOT / "tooling_acceptance/timing/controls/pt7_tool.py", sources / "pt7_tool.py")
    libsources = a.output / "installed-library-sources"
    libsources.mkdir()
    for name in ("timing_tcl.ml", "timing_intent.ml"):
        shutil.copyfile(generation / "lib/hardcaml_asic/elaboration" / name, libsources / name)
    for name in ("pt7_timing_corrected.md", "pt7_timing_findings.md"):
        shutil.copyfile(ROOT / "docs" / name, a.output / name)
    binaries = [identity(path) for path in sorted((generation / "bin").iterdir()) if path.is_file()]
    binaries += [identity(ROOT / "_build_pt7/default/tooling_acceptance/timing/basic/timing_cli.exe")]
    dump(a.output / "binary-identities.json", binaries)
    attempts = []
    for kind in ("bit", "scalar"):
        bundle = EVIDENCE / f"synth-{kind}-{a.round}-bundle"
        audit = EVIDENCE / f"sta-{kind}-{a.round}"
        manifest = json.loads((bundle / "manifest.json").read_text())
        for f in manifest["files"]:
            assert sha(bundle / f["path"]) == f["sha256"], f["path"]
        process = json.loads((audit / "process-result.json").read_text())
        log = (audit / "tool.log").read_text()
        attempts.append({"kind": kind, "build_identity": manifest["identity"],
                         "manifest_sha256": sha(bundle / "manifest.json"),
                         "sdc_sha256": sha(audit / "top.sdc"), "process": process,
                         "validated_records": log.count('"event":"validated"'),
                         "applied_records": log.count('"event":"applied"'),
                         "complete_records": log.count('"event":"complete"'),
                         "source_binding": json.loads((audit / "receipt.json").read_text())})
    summary = {"schema": 1, "scope": "pt7-corrected-provider-native-round",
               "recorded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "status": "blocked_by_native_top_pin_internal_net_conversion",
               "provider": json.loads((generation / "receipt.json").read_text()), "attempts": attempts,
               "finding": "A-REAL-2; get_port_pin succeeds but Pin.net is NULL; Pin.term.net is connected",
               "prepared": ["17 native connectivity fixtures including buffered positive/depth boundary",
                            "corrected whole-SDC/full-manifest evidence semantic test runner"],
               "skipped_due_to_failed_positive_baseline": ["corrected downstream min/max acceptance",
                    "qualification of connectivity negatives and buffered source positives",
                    "new successful B CLI audit and semantic fixture suite"],
               "targeted_B_negative": "inspect-old-scalar-with-r2: exit 2, old SDC rejected by current library replay",
               "limits": {"dune_jobs": 6, "tool_threads": 1, "container_cpus": 1,
                          "container_memory_bytes": 4294967296, "container_pids": 128,
                          "serialized_tools": True, "place_route_jobs": 0}}
    assert all(r["process"]["exit_code"] == 1 and not r["validated_records"] and not r["applied_records"] and not r["complete_records"] for r in attempts)
    dump(a.output / "summary.json", summary)
    inventory = [dict(path=str(path.relative_to(EVIDENCE)), bytes=path.stat().st_size, sha256=sha(path))
                 for path in sorted(EVIDENCE.rglob("*")) if path.is_file()]
    dump(a.output / "checksums.json", {"files": inventory, "file_count": len(inventory),
         "total_bytes": sum(r["bytes"] for r in inventory), "scope": "all PT.7 files before this checksum file"})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
