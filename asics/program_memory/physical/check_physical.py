#!/usr/bin/env python3
"""Offline physical/full-postcheck acceptance audit and fresh evidence capture.

Requires a successful public run, hash-bound physical policy records and completed
external TT/gate postchecks. Scope is abstract boundary LVS and zero-delay replay;
no tool is launched, and timed SRAM/internal-device/IR/EM claims are excluded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from physical_contract import check_contract
from physical_records import verify_physical, verify_postcheck


MACRO = "RM_IHPSG13_1P_256x16_c2_bm_bist"
TOP = "tt_um_program_memory"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root), "artifact path escapes root: " + relative)
    return path


def audit(bundle, runroot, generation):
    manifest = json.loads((bundle / "manifest.json").read_text())
    contract = manifest["macro_contract"]
    require(manifest["operation"] == "Hardening" and contract["schema_version"] == 2
            and contract["execution"] == "fresh_full", "requires a schema-2 fresh-full Hardening bundle")
    plan = contract["physical_plan"]
    require(plan["schema_version"] == 1 and plan["strategy"] == "cmos5l_m4_edge_access_v1",
            "supported physical strategy")
    require(plan["plan_file"] == "physical/macro-plan.json" and plan["pdn_tcl"] == "physical/pdn.tcl",
            "generated physical inputs")
    payload = {k: v for k, v in manifest.items() if k != "identity"}
    require(hashlib.sha256(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            == manifest["identity"], "bundle identity")
    inventory = manifest["files"]
    require(len({entry["path"] for entry in inventory}) == len(inventory), "duplicate bundle paths")
    require({entry["path"] for entry in inventory} ==
            {str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file()} - {"manifest.json"},
            "complete bundle inventory")
    for entry in inventory:
        require(sha(contained(bundle, entry["path"])) == entry["sha256"], "bundle hash: " + entry["path"])
    for relative in (plan["plan_file"], plan["pdn_tcl"]):
        require(contained(bundle, relative).stat().st_size > 0, "nonempty physical input")
    check_contract(contract, json.loads((bundle / "src/config.json").read_text()),
                   {entry["path"]: contained(bundle, entry["path"]).read_bytes() for entry in inventory})
    macro, = contract["macros"]
    require((macro["resource"], macro["instance"], macro["module"]) ==
            ("program", "hc_resource_7_program", MACRO), "one actual stock program SRAM")
    intent = macro["physical_intent"]
    require(intent["location_um"] == [40.0, 81.0] and intent["orientation"] == "R0"
            and intent["halo_um"] == 2.0, "explicit physical candidate")
    require(intent["power"] == {"VDD!": "VPWR", "VDDARRAY!": "VPWR", "VSS!": "VGND"},
            "both positive rails and ground declared")
    run = json.loads((runroot / "run.json").read_text())
    require(run["status"] == "completed" and run["completed_stage"] == "full", "completed full run")
    require(run["build_identity"] == manifest["identity"], "run/bundle binding")
    project = runroot / "project"
    require((project / "manifest.json").read_bytes() == (bundle / "manifest.json").read_bytes(),
            "staged manifest matches bundle")
    for entry in inventory:
        require(sha(contained(project, entry["path"])) == entry["sha256"], "staged input: " + entry["path"])
    flow = project / "runs/asic"
    metrics = json.loads((flow / "final/metrics.json").read_text())
    # Positive presence matters: absent metrics cannot masquerade as zero failures.
    for key in ("design__inferred_latch__count", "design__instance_unmapped__count",
                "synthesis__check_error__count", "design__lint_error__count",
                "design__max_slew_violation__count", "design__max_cap_violation__count",
                "timing__setup_vio__count", "timing__hold_vio__count"):
        require(key in metrics and metrics[key] == 0, "required zero metric: " + key)
        for corner_key, value in metrics.items():
            if corner_key.startswith(key + "__corner:"):
                require(value == 0, "corner violation: " + corner_key)
    mapped = json.loads((flow / "06-yosys-synthesis" / f"{TOP}.nl.v.json").read_text())
    cells = mapped["modules"][TOP]["cells"]
    require({name: cell["type"] for name, cell in cells.items() if cell["type"].startswith("RM_")} ==
            {"hc_resource_7_program": MACRO}, "one synthesized stock SRAM")
    require(sum(cell["type"] == "sg13cmos5l_dfrbpq_1" for cell in cells.values()) == 16,
            "16 original synthesis staging flip-flops")
    final_netlist = flow / f"final/nl/{TOP}.nl.v"
    rtl = final_netlist.read_text()
    require(len(re.findall(r"\b" + MACRO + r"\s+hc_resource_7_program\s*\(", rtl)) == 1,
            "final netlist retains actual macro")
    require(not re.search(r"\b(always|reg)\b", rtl), "mapped final netlist")
    # dlygate* are combinational hold-delay cells, not dl* latches. Keep every
    # other df/sdf/dl/latch family in the storage inventory so new state rejects.
    sequential = re.findall(r"\b(sg13cmos5l_(?:s?df|dl(?!ygate)|latch)\w*)\s+\S+\s*\(", rtl)
    require(len(sequential) == 16 and all(re.fullmatch(r"sg13cmos5l_dfrbpq_\d+", cell) for cell in sequential),
            "final netlist preserves exactly the 16 original staging flip-flops")
    receipt = json.loads((generation / "receipt.json").read_text())
    require(Path(receipt["generation"]).resolve() == generation, "generation receipt binding")
    retained = {"bundle/manifest.json": bundle / "manifest.json",
                "provider-receipt.json": generation / "receipt.json",
                "run.json": runroot / "run.json", "preflight.json": runroot / "preflight.json",
                "metrics.json": flow / "final/metrics.json", "mapped.v": final_netlist,
                "mapped.json": flow / "06-yosys-synthesis" / f"{TOP}.nl.v.json",
                "resolved-config.json": flow / "resolved.json",
                "check_physical.py": Path(__file__).resolve(),
                "physical_contract.py": Path(__file__).with_name("physical_contract.py").resolve()}
    retained.update({"bundle/" + entry["path"]: contained(bundle, entry["path"]) for entry in inventory})
    retained["physical_records.py"] = Path(__file__).with_name("physical_records.py").resolve()
    evidence = verify_physical(runroot, generation, run, manifest, metrics, retained)
    directories = sorted(p.parent for p in (runroot / "checks").glob("*/postcheck.json"))
    require(directories, "external postcheck required; run flow exit alone is not acceptance")
    postchecks = [verify_postcheck(p, run, flow, generation, retained) for p in directories]
    return {"scope": "public physical policy and external TT/zero-delay gate acceptance",
            "physical_acceptance": True, "bundle_identity": manifest["identity"],
            "run_id": run["run_id"], "run_root": str(runroot), "provider_generation": str(generation),
            "lvs_scope": evidence["lvs_scope"], "gate_replay_scope": "zero_delay_gate_functional_not_timing_conformance",
            "magic_raw_count": evidence["magic_raw_count"], "magic_disposition": evidence["magic_disposition"],
            "postcheck_ids": [p.name for p in directories],
            "postcheck_count": len(postchecks),
            "not_established": ["internal-device LVS", "IR/EM adequacy", "SDF/timed SRAM conformance",
                                "negative oracle (not part of public postcheck)"]}, retained


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--provider-generation", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, help="optional NEW directory; copies evidence only")
    args = parser.parse_args()
    if args.evidence_dir:
        require(not args.evidence_dir.exists(), "evidence directory must be new")
    summary, retained = audit(args.bundle.resolve(), args.run_root.resolve(), args.provider_generation.resolve())
    if args.evidence_dir:
        # Check all sources before reserving the destination. Never overwrite history.
        for path in retained.values():
            require(path.is_file(), "missing evidence source: " + str(path))
        args.evidence_dir.mkdir()
        checksums = []
        for relative, source in sorted(retained.items()):
            destination = args.evidence_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            checksums.append({"path": relative, "source": str(source), "sha256": sha(destination),
                              "bytes": destination.stat().st_size})
        destination = args.evidence_dir / "summary.json"
        destination.write_text(json.dumps(summary, indent=2) + "\n")
        checksums.append({"path": "summary.json", "sha256": sha(destination), "bytes": destination.stat().st_size})
        (args.evidence_dir / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
