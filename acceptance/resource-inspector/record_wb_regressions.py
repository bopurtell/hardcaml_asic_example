#!/usr/bin/env python3
"""Close C's WB-only broad/native regression receipts; no build or provider query."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
WB = ROOT.parents[2] / "hardcaml_workbench"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("pt6_wb_closeout", WB / "scripts/test-resource-inspector.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    stages = {"broad": "wb-broad-01", "unified": "wb-unified-01", "checklist": "wb-checklist-01",
              "layout": "wb-layout-04", "saved-layout": "wb-saved-layout-01"}
    counts = {"unified": 99, "checklist": 83, "layout": 72, "saved-layout": 16}
    receipts = {key: g.load(ROOT / directory / "receipt.json") for key, directory in stages.items()}
    binaries = receipts["broad"]["binaries_after"]
    protected = g.protected(g.DEFAULT_EXAMPLE)
    result = dict(status="passed", scope="PT6 C WB-only broad and native layout/control regressions",
                  phases={}, binaries=binaries, protected=protected, protected_unchanged=True,
                  source_inventory_sha256={}, recorder_sha256=g.sha(Path(__file__)))
    for phase, receipt in receipts.items():
        g.require(receipt["status"] == "passed" and receipt["exit"] == 0 and receipt["protected_unchanged"], phase + " passed")
        g.require(receipt["sources_unchanged_during_run"], phase + " stable product sources during run")
        g.require(receipt["binaries_after"] == binaries, phase + " matching tested binary identities")
        if phase != "broad":
            g.require(receipt["binaries_before"] == binaries, phase + " binary identity before native suite")
            native = receipt["native_result"]
            g.require(native["status"] == "passed" and len(native["checks"]) == counts[phase]
                      and all(c["passed"] for c in native["checks"]), phase + " assertion outcomes")
        directory = ROOT / stages[phase]
        g.require(protected == g.load(directory / "protected-after.json"), phase + " full protected-state closure")
        g.require(g.sha(directory / "command.stdout") == receipt["command.stdout_sha256"]
                  and g.sha(directory / "command.stderr") == receipt["command.stderr_sha256"], phase + " command byte closure")
        result["source_inventory_sha256"][phase] = hashlib.sha256(json.dumps(
            receipt["sources_after"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        files = {str(p.relative_to(directory)): g.sha(p) for p in sorted(directory.rglob("*")) if p.is_file() and not p.is_symlink()}
        entry = dict(receipt=str(directory / "receipt.json"), receipt_sha256=g.sha(directory / "receipt.json"),
                     seconds=receipt["seconds"], exit=0, checks=counts.get(phase), receipt_files=files)
        if phase != "broad":
            native_root = Path(receipt["native_evidence"])
            entry["native_evidence"] = str(native_root)
            entry["native_files"] = {str(p.relative_to(native_root)): g.sha(p)
                                     for p in sorted(native_root.rglob("*")) if p.is_file() and not p.is_symlink()}
        result["phases"][phase] = entry
    result["same_product_sources_across_phases"] = len(set(result["source_inventory_sha256"].values())) == 1
    result["historical_layout_harness_failures"] = {
        name: g.sha(ROOT / name / "receipt.json") for name in ("wb-layout-01", "wb-layout-02", "wb-layout-03")}
    result["no_new_asic_capture"] = True
    g.write_new(args.receipt.resolve(), result)
    print(json.dumps(dict(receipt=str(args.receipt.resolve()), status=result["status"],
                          phases={k: dict(checks=v["checks"], seconds=v["seconds"]) for k, v in result["phases"].items()},
                          binaries=binaries, same_product_sources_across_phases=result["same_product_sources_across_phases"]), indent=2))


if __name__ == "__main__":
    main()
