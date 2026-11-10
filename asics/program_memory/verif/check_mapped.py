#!/usr/bin/env python3
"""Inspect an existing public synthesis run and replay its mapped netlist (no EDA/build)."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

MACRO = "RM_IHPSG13_1P_256x16_c2_bm_bist"
TOP = "tt_um_program_memory"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--pdk-root", type=Path, required=True)
    parser.add_argument("--provider-generation", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True,
                        help="standalone public preflight report preceding this run")
    parser.add_argument("--evidence-dir", type=Path, required=True, help="must not exist")
    args = parser.parse_args()
    runroot, bundle = args.run_root.resolve(), args.bundle.resolve()
    evidence = args.evidence_dir.resolve()
    require(not evidence.exists(), "evidence destination must be new")
    flow = runroot / "project/runs/asic"
    stage = flow / "06-yosys-synthesis"
    netlist = flow / f"final/nl/{TOP}.nl.v"
    manifest = json.loads((bundle / "manifest.json").read_text())
    run = json.loads((runroot / "run.json").read_text())
    require(run["status"] == "completed" and run["completed_stage"] == "synthesis", "completed public synthesis")
    require(run["build_identity"] == manifest["identity"], "run/bundle identity")
    require((runroot / "project/manifest.json").read_bytes() == (bundle / "manifest.json").read_bytes(),
            "run staged the exact retained manifest")
    # Verify the immutable source bundle before doing anything to the evidence store.
    for item in manifest["files"]:
        require(sha(bundle / item["path"]) == item["sha256"], "bundle hash: " + item["path"])
    require(netlist.read_bytes() == (stage / f"{TOP}.nl.v").read_bytes(), "final/stage mapped netlist agreement")
    mapped = json.loads((stage / f"{TOP}.nl.v.json").read_text())
    cells = mapped["modules"][TOP]["cells"]
    counts = dict(sorted(Counter(c["type"] for c in cells.values()).items()))
    macros = {n: c for n, c in cells.items() if c["type"].startswith("RM_")}
    require(list(macros) == ["hc_resource_7_program"], "one actual SRAM instance")
    require(macros["hc_resource_7_program"]["type"] == MACRO, "stock SRAM type")
    require(counts.get("sg13cmos5l_dfrbpq_1") == 16, "16 original staging flip-flops")
    require(all(t == MACRO or t.startswith("sg13cmos5l_") for t in counts), "fully mapped cell types")
    require(not re.search(r"\b(always|reg)\b", netlist.read_text()), "gate netlist, not behavioral RTL")
    stat = json.loads((stage / "reports/stat.json").read_text())
    require(stat["design"]["num_cells_by_type"] == counts, "raw netlist/stat histogram agreement")
    metrics = json.loads((flow / "final/metrics.json").read_text())
    for key in ("design__inferred_latch__count", "design__instance_unmapped__count",
                "synthesis__check_error__count", "design__lint_error__count"):
        require(metrics[key] == 0, "synthesis metric " + key)

    pdk = args.pdk_root.resolve() / "ihp-sg13cmos5l"
    simulation = manifest["macro_contract"]["implementation_simulation"]
    require(simulation["defines"] == ["FUNCTIONAL"], "vendor functional simulation contract")
    models = []
    for ref in simulation["models"]:
        require(ref.startswith("pdk_dir::"), "PDK-relative model reference")
        models.append(pdk / ref.removeprefix("pdk_dir::"))
    models += [pdk / "libs.ref/sg13cmos5l_stdcell/verilog/sg13cmos5l_stdcell.v",
               pdk / "libs.ref/sg13cmos5l_stdcell/verilog/sg13cmos5l_udp.v"]
    for model in models:
        require(model.is_file(), "model exists: " + str(model))
    # Match macro models to the preflight hashes retained in the public run.
    references = {x["reference"]: x["sha256"] for x in run["environment"]["references"] if "reference" in x}
    for ref, model in zip(simulation["models"], models):
        require(sha(model) == references[ref], "run-bound vendor macro model hash")

    evidence.mkdir(parents=True)
    inventory = []

    def retain(source, relative):
        destination = evidence / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        inventory.append({"path": relative, "source": str(source), "sha256": sha(destination),
                          "bytes": destination.stat().st_size})

    raw = {
        "run.json": runroot / "run.json",
        "run-preflight.json": runroot / "preflight.json",
        "public-preflight.json": args.preflight.resolve(),
        "manifest.json": bundle / "manifest.json",
        "bundle-config.json": bundle / "src/config.json",
        "resolved-config.json": flow / "resolved.json",
        "synthesis-config.json": stage / "config.json",
        "stat.json": stage / "reports/stat.json",
        "metrics.json": flow / "final/metrics.json",
        "synthesis.log": stage / "yosys-synthesis.log",
        "lint.log": flow / "01-verilator-lint/verilator-lint.log",
        "mapped.v": netlist,
        "mapped.json": stage / f"{TOP}.nl.v.json",
        "provider-receipt.json": args.provider_generation.resolve() / "receipt.json",
        "replay.v": Path(__file__).with_name("replay.v"),
        "check_mapped.py": Path(__file__),
    }
    for relative, source in raw.items():
        retain(source, relative)
    for item in manifest["source_inputs"]:
        retain(bundle / item["copy"], "bundle-" + item["copy"])
    # Store the four small functional sources, not tool binaries or the PDK tree.
    for model in models:
        retain(model, "models/" + model.name)
    model_evidence = [evidence / "models" / m.name for m in models]
    # The stock CMOS5L file is a timing model: its UDP inputs are driven only by
    # $setuphold delayed-reference outputs, which Icarus does not implement.
    # Derive a zero-delay view of ONLY the used cells. Preserve the vendor logic
    # and UDP calls; omit specify blocks and bypass delayed-reference nets.
    vendor_cells = models[-2].read_text()
    functional = [vendor_cells[:vendor_cells.index("// type:")],
                  "// Derived zero-delay functional view for Icarus; not timing evidence.\n"]
    adaptations = {}
    for cell_type in sorted(t for t in counts if t != MACRO):
        match = re.search(r"\bmodule\s+" + re.escape(cell_type) + r"\s*\(.*?\bendmodule", vendor_cells, re.S)
        require(match, "vendor definition for " + cell_type)
        body = re.sub(r"\bspecify\b.*?\bendspecify\b", "", match.group(), flags=re.S)
        delayed = sorted(set(re.findall(r"\bdelayed_(\w+)\b", body)))
        if delayed:
            require(cell_type == "sg13cmos5l_dfrbpq_1" and set(delayed) == {"CLK", "D", "RESET_B"},
                    "only the reviewed staging-cell delayed references may be adapted")
        bypass = "\n".join(f"  assign delayed_{pin} = {pin};" for pin in delayed)
        functional.append(body.replace("endmodule", bypass + "\nendmodule") + "\n")
        adaptations[cell_type] = {"specify": "omitted", "delayed_pin_bypass": delayed}
    functional_path = evidence / "models/sg13cmos5l_used_functional.v"
    functional_path.write_text("\n".join(functional))
    model_evidence[-2] = functional_path
    records = []

    def execute(argv, name, expected=0):
        result = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=120)
        (evidence / (name + ".stdout")).write_text(result.stdout)
        (evidence / (name + ".stderr")).write_text(result.stderr)
        records.append({"argv": [str(x) for x in argv], "exit_code": result.returncode,
                        "expected_exit_code": expected, "stdout": name + ".stdout", "stderr": name + ".stderr"})
        require(result.returncode == expected, f"{name}: exit {result.returncode}\n{result.stdout}\n{result.stderr}")
        return result.stdout

    with tempfile.TemporaryDirectory(prefix="mapped-sram-") as tmp:
        compiled = Path(tmp) / "mapped.vvp"
        execute(["iverilog", "-g2012", "-DFUNCTIONAL", "-s", "memory_replay", "-o", compiled,
                 evidence / "replay.v", evidence / "mapped.v", *model_evidence], "compile")
        output = execute(["vvp", "-n", compiled], "replay")
        require("checks=1280" in output and "PASS memory RTL" in output, "complete mapped replay")
        negative = execute(["vvp", "-n", compiled, "+negative"], "negative", expected=1)
        require("low byte" in negative and "expected=" in negative, "negative failed on intended data mismatch")
    execute(["iverilog", "-V"], "iverilog-version")
    receipt = json.loads((evidence / "provider-receipt.json").read_text())
    macro_lib = pdk / f"libs.ref/sg13cmos5l_sram/lib/{MACRO}_typ_1p20V_25C.lib"
    macro_area = float(re.search(r"\barea\s*:\s*([0-9.]+)", macro_lib.read_text()).group(1))
    retain(macro_lib, "models/" + macro_lib.name)
    summary = {
        "schema_version": 1, "run_id": run["run_id"], "run_root": str(runroot),
        "bundle": str(bundle), "bundle_identity": manifest["identity"],
        "source_revision": manifest["source_revision"],
        "source_attribution": "Bundle copies preserve dirty/untracked source input statuses; revision is not a clean-source claim. Current README/checker edits postdate c1.",
        "dependency_attribution": {"mode": receipt["mode"], "observed_base_revision": receipt["observed_base_revision"],
            "snapshot_sha256": receipt["snapshot_sha256"], "captured_differs_from_observed_base": receipt["captured_differs_from_observed_base"],
            "note": "Captured development worktree, not released pin or generator stamp; legacy asic-dependency.json is unchanged."},
        "netlist_sha256": sha(netlist), "cells_by_type": counts,
        "macro_instances": {n: c["type"] for n, c in macros.items()},
        "flip_flops": 16, "cell_count": len(cells), "metrics": metrics,
        "area": {"reported_synthesis_um2": stat["design"]["area"],
                 "reported_sequential_um2": stat["design"]["sequential_area"],
                 "stock_macro_liberty_um2": macro_area,
                 "reported_plus_macro_um2": round(stat["design"]["area"] + macro_area, 7),
                 "scope": "Reported synthesis area omits the SRAM blackbox area; sum is a cell-area estimate, not placed/routed die area."},
        "gate_replay": {"kind": "actual technology-mapped netlist + stock standard-cell/UDP and SRAM functional models",
                        "word_checks": 1280, "negative_oracle_rejected": True, "commands": records,
                        "standard_cell_adaptation": adaptations,
                        "adaptation_scope": "Derived used-cell zero-delay vendor view; original functions and UDPs retained. specify omitted; delayed CLK/D/RESET_B bypassed. No netlist edits."},
        "limitations": ["No SDF, timing checks, STA closure or timed SRAM conformance.",
                        "No placement, routing, physical power connectivity, DRC, LVS or physical acceptance.",
                        "One lint warning: intentionally unused ui_in[7:3]."],
    }
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    # Include generated logs/summary in a complete checksum index (except the index itself).
    indexed = {x["path"] for x in inventory}
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and str(path.relative_to(evidence)) not in indexed:
            inventory.append({"path": str(path.relative_to(evidence)), "sha256": sha(path), "bytes": path.stat().st_size})
    (evidence / "checksums.json").write_text(json.dumps(inventory, indent=2) + "\n")
    print(json.dumps({"run_id": run["run_id"], "cell_count": len(cells), "cells_by_type": counts,
                      "metrics": metrics, "gate_word_checks": 1280, "negative_oracle_rejected": True,
                      "evidence": str(evidence)}, indent=2))


if __name__ == "__main__":
    main()
