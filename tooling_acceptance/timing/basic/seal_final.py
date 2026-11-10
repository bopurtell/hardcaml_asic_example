#!/usr/bin/env python3
"""Assert and seal completed correction-round native acceptance, retaining history."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
from real_tools import ROOT, EVIDENCE, dump
from record_command import sha

RENDERER = "9c53a5b75313adacd979ea5b559fd17ad0c51d2961c4df6dc0a41813a88d25d2"


def load(path):
    return json.loads(path.read_text())


def identity(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generation", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir()
    generation = a.generation.resolve(strict=True)
    prior = []
    for baseline in ("closeout-01/checksums.json", "closeout-r2/checksums.json"):
        receipt = load(EVIDENCE / baseline)
        for f in receipt["files"]:
            assert sha(EVIDENCE / f["path"]) == f["sha256"], f["path"]
        prior.append({"baseline": baseline, "sha256": sha(EVIDENCE / baseline), "checked_files": len(receipt["files"]), "status": "pass"})
    protected = load(EVIDENCE / "closeout-01/protected-closeout-observation.json")
    for f in protected["files"].values():
        assert sha(Path(f["path"])) == f["sha256"], f["path"]
    for path, target in protected["old_provider_pointers"].items():
        assert str((ROOT / path).readlink()) == target, path
    dump(a.output / "preservation.json", {"prior_evidence": prior,
         "original_protected_files_and_old_provider_pointers": "unchanged_since_closeout_01"})
    renderer = generation / "lib/hardcaml_asic/elaboration/timing_tcl.ml"
    assert sha(renderer) == RENDERER
    shutil.copyfile(generation / "receipt.json", a.output / "provider-receipt.json")
    installed = a.output / "installed-library-sources"
    installed.mkdir()
    for name in ("timing_tcl.ml", "timing_intent.ml"):
        shutil.copyfile(generation / "lib/hardcaml_asic/elaboration" / name, installed / name)
    for name in ("pt7-library-handoff.md", "pt7-evidence-handoff.md"):
        shutil.copyfile(ROOT.parent / "hardcaml_asic/docs/development" / name, a.output / name)
    for name in ("pt7_timing_final.md", "pt7_timing_findings.md"):
        shutil.copyfile(ROOT / "docs" / name, a.output / name)
    consumer = a.output / "consumer-sources"
    consumer.mkdir()
    for path in sorted((ROOT / "tooling_acceptance/timing").rglob("*")):
        if path.is_file():
            target = consumer / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    shutil.copyfile(ROOT / "tooling_acceptance/timing/controls/pt7_tool.py", consumer / "pt7_tool.py")
    binaries = [identity(path) for path in sorted((generation / "bin").iterdir()) if path.is_file()]
    archives = [identity(path) for path in sorted((generation / "lib/hardcaml_asic").rglob("*"))
                if path.is_file() and path.suffix in (".a", ".cma", ".cmxa", ".cmxs")]
    compiled = [identity(path) for path in sorted((ROOT / "_build_pt7/default/tooling_acceptance/timing/basic/.timing_cli.eobjs/native").iterdir()) if path.is_file()]
    compiled.append(identity(ROOT / "_build_pt7/default/tooling_acceptance/timing/basic/timing_cli.exe"))
    dump(a.output / "producer-identities.json", {"binaries": binaries, "archives": archives, "emitter_artifacts": compiled,
         "identity_scope": "local captured dirty-development bytes, not authenticated execution or a clean-source stamp"})
    audits = []
    for kind in ("bit", "scalar"):
        bundle = EVIDENCE / f"synth-{kind}-r3-bundle"
        audit_dir = EVIDENCE / f"sta-{kind}-r3"
        manifest = load(bundle / "manifest.json")
        for f in manifest["files"]:
            assert sha(bundle / f["path"]) == f["sha256"], f["path"]
        for f in manifest["source_inputs"]:
            assert sha(ROOT / f["path"]) == f["sha256"], f["path"]
        assert sha(bundle / "constraints/top.sdc") == sha(audit_dir / "top.sdc")
        audit = load(audit_dir / "audit.json")
        for f in audit["sources"]:
            assert sha(audit_dir / f["path"]) == f["sha256"], f["path"]
        assert load(audit_dir / "process-result.json")["exit_code"] == 0
        launch = load(EVIDENCE / f"sta-{kind}-r3-launch/launch.json")
        assert launch["inputs_unchanged"] and launch["limits"]["tool_threads"] == 1
        assert launch["argv"][launch["argv"].index("-threads") + 1] == "1"
        checked = load(EVIDENCE / f"checked-{kind}-r3/summary.json")
        assert checked["status"] == "pass_with_coverage_unavailable" and checked["public_inspector_exit"] == 1
        assert len(checked["downstream_sampled_paths"]) == 6 and len(checked["evidence_negatives"]) == 7
        graph = load(EVIDENCE / f"connectivity-{kind}-r3/summary.json")
        taps = load(EVIDENCE / f"taps-{kind}-r3/summary.json")
        semantic = load(EVIDENCE / f"semantic-{kind}-r3/summary.json")
        assert graph["status"] == taps["status"] == semantic["status"] == "pass"
        assert len(graph["cases"]) == 17 and len(taps["cases"]) == 3 and len(semantic["cases"]) == 9
        for case in graph["cases"]:
            if case["expected_exit"] == 1:
                assert case["exit_code"] == 1 and not case["validated"] and not case["applied_records"] and not case["complete"]
        audits.append({"kind": kind, "build_identity": manifest["identity"], "audit_id": audit["audit_id"],
                       "audit_sha256": sha(audit_dir / "audit.json"), "receipt_sha256": sha(audit_dir / "receipt.json"),
                       "sources": audit["sources"], "sampled_paths": checked["downstream_sampled_paths"],
                       "public_inspection_exit": 1, "native_coverage": "unavailable"})
    envelope = load(EVIDENCE / "semantic-envelope-bit-r3/summary.json")
    assert envelope["status"] == "pass" and len(envelope["cases"]) == 8
    assert all(case["exit_code"] == 2 for case in envelope["cases"])
    native = load(EVIDENCE / "native-negatives-summary-r3.json")
    assert len(native["cases"]) == 5
    for case in native["cases"]:
        assert case["exit_code"] == 1 and case["diagnostic_found"] and case["zero_application_records"] and case["no_complete"]
        for suffix in ("stdout.log", "stderr.log"):
            assert '"event":"validated"' not in (EVIDENCE / ("negative-" + case["case"] + "-r3-launch") / suffix).read_text()
    unconstrained = (EVIDENCE / "native-unconstrained-r3-launch/stdout.log").read_text()
    assert "5 unclocked register/latch pins" in unconstrained and "7 unconstrained endpoints" in unconstrained
    summary = {"schema": 1, "status": "bounded_native_bit_and_scalar_acceptance_complete_with_coverage_unavailable",
               "recorded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "provider": load(generation / "receipt.json"), "renderer_sha256": RENDERER, "audits": audits,
               "counts": {"native_baseline_audits": 2, "connectivity_fixtures": 34,
                          "connectivity_pre_application_negatives": 28, "output_tap_controls": 6,
                          "additional_anchor_scope_negatives": 5, "evidence_rejections": 36,
                          "semantic_equivalence_controls": 4, "native_unconstrained_controls": 1},
               "findings": {"A-REAL-1": "closed by native bit-source run", "A-REAL-2": "closed by both native source traces",
                            "R4": "native Q/source output taps passed", "B_R5_R6": "targeted envelope negatives rejected for intended semantic diagnostics"},
               "limitations": ["native exception coverage intentionally unavailable; set_false_path completion is not exhaustive path-effect proof",
                    "three sampled hold violations per main audit remain at -0.044244 ns; setup samples +19.432287 ns",
                    "standalone typical-corner ideal-clock/no-parasitics analysis, no P&R or post-PNR qualification",
                    "no analog CDC/MTBF, reset-release protocol or Protemu qualification",
                    "controlled netlist/evidence fixtures are mutations, not additional synthesized products or authenticated executions",
                    "coordinator independent review is separate; unrelated broad suites not repeated"],
               "limits": {"dune_jobs": 6, "tool_threads": 1, "container_cpus": 1, "container_memory_bytes": 4294967296,
                          "container_pids": 128, "serialized_tools": True, "place_route_jobs": 0}}
    dump(a.output / "summary.json", summary)
    inventory = [dict(path=str(path.relative_to(EVIDENCE)), bytes=path.stat().st_size, sha256=sha(path))
                 for path in sorted(EVIDENCE.rglob("*")) if path.is_file()]
    dump(a.output / "checksums.json", {"files": inventory, "file_count": len(inventory),
         "total_bytes": sum(f["bytes"] for f in inventory), "scope": "all PT.7 evidence before this checksums file"})
    print(json.dumps({"status": summary["status"], "provider": str(generation),
                      "audits": [{k: v for k, v in audit.items() if k not in ("sources", "sampled_paths")} for audit in audits],
                      "counts": summary["counts"], "evidence_files": len(inventory)}, indent=2))


if __name__ == "__main__":
    main()
