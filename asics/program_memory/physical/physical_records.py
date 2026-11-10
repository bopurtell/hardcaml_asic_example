"""Offline verification of public physical and external postcheck receipts.

Only pure parsing/classification functions from the hash-bound installed checker
are used. Never call its check/audit/diagnostic/tool-launching entry points.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(root, relative):
    require(isinstance(relative, str) and not Path(relative).is_absolute()
            and ".." not in Path(relative).parts, "unsafe artifact path")
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "artifact escapes root")
    return path


def verify_hashes(root, inventory, retained, prefix):
    require(isinstance(inventory, dict) and inventory, "missing artifact hash inventory")
    paths = {}
    for name, digest in inventory.items():
        path = inside(root, name)
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
                and sha(path) == digest, "artifact hash mismatch: " + name)
        retained[prefix + name] = path
        paths[name] = path
    return paths


def zero(metrics, key):
    value = metrics.get(key)
    require(type(value) in (int, float) and math.isfinite(value) and value == 0,
            "missing/nonfinite/nonzero metric: " + key)


def unique(paths, suffix):
    matches = [p for name, p in paths.items() if name.endswith(suffix)]
    require(len(matches) == 1, "required unique hashed artifact: " + suffix)
    return matches[0]


def installed_runtime(generation):
    path = generation / "lib/hardcaml_asic/flow/hardcaml_asic_flow/physical_runtime.py"
    spec = importlib.util.spec_from_file_location("retained_physical_policy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_physical(runroot, generation, run, manifest, metrics, retained):
    project, flow = runroot / "project", runroot / "project/runs/asic"
    require(run["requested_stage"] == run["completed_stage"] == "full" and run["status"] == "completed",
            "successful public full run required; diagnostic clones cannot replace it")
    for key, name, installed in (
        ("physical_checker_sha256", "physical-runtime.py", "physical_runtime.py"),
        ("macro_flow_sha256", "macro-flow.py", "macro_flow.py"),
    ):
        path = project / name
        require(run.get(key) == sha(path) == sha(generation / "lib/hardcaml_asic/flow/hardcaml_asic_flow" / installed),
                "run/installed runtime binding: " + name)
        retained["runtime/" + name] = path
    require(run["manifest_sha256"] == sha(project / "manifest.json"), "run manifest hash")
    evidence_path = runroot / "physical-checks.json"
    require(run["physical_checks_sha256"] == sha(evidence_path), "public physical-checks hash")
    require(evidence_path.read_bytes() == (flow / "physical-checks.json").read_bytes(), "public/flow checker copy differs")
    retained["physical-checks.json"] = evidence_path
    evidence = load(evidence_path)
    require(evidence["schema_version"] == 1 and evidence["status"] == "pass"
            and evidence["checking_profile"] == "cmos5l_real_gds_v1"
            and evidence["lvs_scope"] == "abstract_macro_boundary_with_schematic_cdl"
            and evidence["internal_device_lvs"] == "not_verified", "physical checking status/profile/scope")
    require(evidence["resource_limits"] == {"workers": 6, "sta_workers": 1}, "physical worker limits")
    paths = verify_hashes(flow, evidence["artifacts"], retained, "flow/")
    gds = flow / ("final/gds/" + manifest["top_module"] + ".gds")
    require(sha(gds) == evidence["gds_sha256"], "checked/final GDS hash")
    retained["final.gds"] = gds
    report = unique(paths, "reports/drc.klayout.lyrdb")
    require(sha(report) == evidence["drc_report_sha256"], "KLayout report binding")
    root = ET.parse(report).getroot()
    require(root.tag == "report-database" and root.find("items") is not None
            and len(root.find("items")) == 0, "real-GDS KLayout report violations")
    zero(load(unique(paths, "reports/drc.klayout.json")), "total")
    state = load(unique(paths, "klayout-drc/state_in.json"))
    require(sha(Path(state["gds"])) == sha(gds), "KLayout checked a different GDS")
    for key in ("klayout__drc_error__count", "route__drc_errors", "magic__illegal_overlap__count",
                "design__lvs_error__count", "design__power_grid_violation__count",
                "design__critical_disconnected_pin__count", "antenna__violating__nets", "antenna__violating__pins"):
        zero(metrics, key)
    for corner in manifest["flow_configuration"]["STA_CORNERS"]:
        for base in ("design__max_slew_violation__count", "design__max_cap_violation__count",
                     "timing__setup_vio__count", "timing__hold_vio__count"):
            zero(metrics, base + "__corner:" + corner)
        for base in ("timing__setup__ws", "timing__hold__ws"):
            value = metrics.get(base + "__corner:" + corner)
            require(type(value) in (int, float) and math.isfinite(value) and 0 <= value < 1e30,
                    "missing/nonfinite/negative all-corner slack")
    runtime = installed_runtime(generation)
    geometry = unique(paths, "macro-power-geometry.json")
    require(sha(geometry) == evidence["power_geometry_sha256"] and
            evidence["final_power_geometry"] == "retained_in_real_gds", "power evidence binding")
    power = load(geometry)
    plan = manifest["macro_contract"]["physical_plan"]
    require(power["schema_version"] == 1 and power["strategy"] == plan["strategy"], "power geometry schema")
    require(len(power["macros"]) == len(plan["macros"]), "power geometry inventory")
    for declared, actual in zip(plan["macros"], power["macros"]):
        require(all(actual[k] == declared[k] for k in ("resource", "instance", "module", "orientation")), "power resource binding")
        units = power["dbu_per_um"]
        x, y = declared["location_um"]
        require(actual["footprint_dbu"] == [round(v * units) for v in (x, y, x + 236.8, y + 118.78)]
                and actual["halo_dbu"] == round(declared["halo_um"] * units), "placed power footprint/halo")
        require({(c["pin"], c["net"]) for c in actual["contacts"]} ==
                {("VDD!", "VPWR"), ("VDDARRAY!", "VPWR"), ("VSS!", "VGND")}
                and len(actual["contacts"]) == 3, "all three power contacts")
        for contact in actual["contacts"]:
            require(contact["measured_minimum_clearance_dbu"] >= contact["minimum_clearance_dbu"]
                    >= 0.6 * power["dbu_per_um"], "power contact clearance")
            require(contact["minimum_contact_width_dbu"] >= 1.4 * units and
                    contact["minimum_overlap_dbu"] >= 0.4 * units, "power contact width/overlap policy")
    require(len(power["public_pins"]) == 2 and {p["net"] for p in power["public_pins"]} == {"VPWR", "VGND"}
            and all(p["layer"] == "Metal4" for p in power["public_pins"]), "both public Metal4 supply pins")
    runtime.validate_public_lef(unique(paths, "final/lef/" + manifest["top_module"] + ".lef").read_text(),
                                power["public_pins"], power["dbu_per_um"])
    require(evidence["schematic_cdl_reader"] == "cmos5l_cdl_names_v1"
            and evidence["macro_boundary_pin_count"] == 109, "abstract LVS reader/pin scope")
    lvs_script = unique(paths, "lvs_script.lvs")
    require(sha(lvs_script) == evidence["lvs_script_sha256"], "LVS script binding")
    reader = load(unique(paths, "lvs-reader.json"))
    source = Path(reader["source_cdl"])
    require(sha(source) == reader["source_cdl_sha256"] == evidence["schematic_cdl_sha256"], "source CDL binding")
    retained["stock.cdl"] = source
    # This reader verifier is pure: hashes/normalization/log and Netgen JSON only.
    refs = load(runroot / "preflight.json")["references"]
    match = [r for r in refs if r.get("reference") == manifest["flow_configuration"]["EXTRA_SPICE_MODELS"][0]]
    require(len(match) == 1 and match[0]["sha256"] == sha(source), "run-bound supplied CDL")
    pdk_root = source.parents[4]  # <root>/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/cdl/file
    runtime.validate_lvs_reader(lvs_script.parent, manifest, pdk_root)
    disposition = evidence["magic_disposition"]
    raw = unique(paths, "-magic-drc/reports/drc.magic.rpt")
    require(sha(raw) == disposition["raw_report_sha256"], "raw Magic report binding")
    findings = runtime.magic_findings(raw)
    count = metrics.get("magic__drc_error__count")
    require(type(count) in (int, float) and count == len(findings) == evidence["magic_raw_count"]
            == disposition["raw_count"], "raw Magic count must remain accurate")
    if findings:
        require(disposition["status"] == "dispositioned_stock_abstract" and
                disposition["accepted_count"] == count and disposition["unclassified_count"] == 0,
                "unclassified Magic diagnostics")
        if disposition["basis"] == "exact_M2_M3_f_wide_OBS_layer_controls_clean_real_GDS_required":
            controls = disposition["controls"]
            observed = {}
            stock = unique(paths, "/stock/diagnostic.lef").read_text()
            require(hashlib.sha256(stock.encode()).hexdigest() == disposition["source_lef_sha256"], "stock LEF binding")
            lef_reference = manifest["flow_configuration"]["MACROS"][plan["macros"][0]["module"]]["lef"][0]
            recorded_lef = [r for r in refs if r.get("reference") == lef_reference]
            require(len(recorded_lef) == 1 and recorded_lef[0]["sha256"] == disposition["source_lef_sha256"],
                    "diagnostic stock LEF not bound by preflight")
            for index, (name, digest) in enumerate(sorted(disposition["baseline_input_hashes"].items())):
                source = Path(name)
                require(sha(source) == digest and any(r.get("sha256") == digest for r in refs),
                        "Magic baseline input not bound by preflight")
                retained[f"baseline-inputs/{index}-" + source.name] = source
            for label, control in controls.items():
                prefix = "/" + label + "/"
                for suffix, key in (("diagnostic.lef", "diagnostic_lef_sha256"),
                                    ("counterfactual.tcl", "script_sha256"), ("reports/drc.magic.rpt", "report_sha256")):
                    require(sha(unique(paths, prefix + suffix)) == control[key], "Magic control artifact binding")
                derived = unique(paths, prefix + "diagnostic.lef").read_text()
                layers = control["removed_wide_rectangles"]
                require(derived == (runtime.without_wide_obstructions(stock, layers) if layers else stock), "noncanonical diagnostic-only LEF")
                observed[label] = runtime.magic_findings(unique(paths, prefix + "reports/drc.magic.rpt"))
                require(len(observed[label]) == control["raw_count"], "Magic control count")
            result = runtime.validate_obstruction_controls(findings, observed, plan)
        else:
            baseline = runtime.magic_findings(unique(paths, "magic-stock-abstract-baseline/reports/drc.magic.rpt"))
            result = runtime.classify_magic(findings, baseline, plan, power)
        require(result["basis"] == disposition["basis"], "unsupported Magic checking policy")
    else:
        require(disposition["status"] == "zero_findings", "zero Magic policy")
    return evidence


def verify_postcheck(directory, run, flow, generation, retained):
    receipt_path = directory / "postcheck.json"
    check = load(receipt_path)
    require(check["schema_version"] == 1 and check["status"] == "completed"
            and check["run_id"] == run["run_id"] and check["build_identity"] == run["build_identity"],
            "external postcheck status/run/bundle binding")
    require(check["checks"] == {"precheck": "pass", "gate_level": "pass"}, "TT precheck and gate replay required")
    require(check["tools"]["replay_scope"] == "zero_delay_gate_functional_not_timing_conformance", "gate replay scope")
    limits = check["resource_limits"]
    require(all(type(limits[k]) is int and 0 < limits[k] <= 6 for k in
                ("host_cpu_affinity_max", "tool_threads", "container_cpus")), "postcheck worker limits")
    prefix = "postchecks/" + directory.name + "/"
    retained[prefix + "postcheck.json"] = receipt_path
    paths = verify_hashes(directory, check["artifacts"], retained, prefix)
    for key, path in (("gds_sha256", flow / "final/gds/tt_um_program_memory.gds"),
                      ("netlist_sha256", flow / "final/nl/tt_um_program_memory.nl.v"),
                      ("testbench_sha256", directory / "testbench.v")):
        require(check["inputs"][key] == sha(path), "postcheck input hash: " + key)
    helper = paths["physical-runtime.py"]
    require(sha(helper) == check["inputs"]["physical_runtime_sha256"] ==
            sha(generation / "lib/hardcaml_asic/flow/hardcaml_asic_flow/physical_runtime.py"), "postcheck installed helper binding")
    models = load(paths["replay-models.json"])
    require(models["scope"] == "zero_delay_gate_functional", "model scope")
    for name, digest in models["retained_hashes"].items():
        require(name in paths and sha(paths[name]) == digest, "retained replay model hash")
    require(models["source_hashes"], "source model identities missing")
    for index, (name, digest) in enumerate(sorted(models["source_hashes"].items())):
        source = Path(name)
        require(sha(source) == digest, "source replay model changed")
        retained[prefix + f"sources/{index}-" + source.name] = source
    require(sha(paths["stdcell-functional.v"]) == models["functional_sha256"] and
            sha(paths["stdcell-vendor.v"]) == models["vendor_sha256"], "derived/vendor cell view binding")
    used = sorted(set(re.findall(r"\b(sg13cmos5l_\w+)\s+(?:\\\S+|\w+)\s*\(",
                                (flow / "final/nl/tt_um_program_memory.nl.v").read_text())))
    require(used and sorted(models["adaptations"]) == used, "exact final-used-cell model closure")
    vendor = paths["stdcell-vendor.v"].read_text()
    transformed = [vendor[:vendor.index("// type:")] if "// type:" in vendor else "",
                   "`timescale 1ns/1ps\n// Reviewed zero-delay functional view; not SDF/timing evidence.\n"]
    for name in used:
        matches = re.findall(r"\bmodule\s+" + re.escape(name) + r"\s*\(.*?\bendmodule", vendor, re.S)
        require(len(matches) == 1, "unique original vendor cell")
        body = re.sub(r"\bspecify\b.*?\bendspecify\b", "", matches[0], flags=re.S)
        delayed = sorted(set(re.findall(r"\bdelayed_(\w+)\b", body)))
        require(not delayed or (name == "sg13cmos5l_dfrbpq_1" and set(delayed) == {"CLK", "D", "RESET_B"}),
                "unreviewed delayed-reference adaptation")
        require(models["adaptations"][name] == delayed, "cell adaptation receipt")
        bypass = "\n".join("assign delayed_" + pin + " = " + pin + ";" for pin in delayed)
        transformed.append(body.replace("endmodule", bypass + "\nendmodule"))
    require(paths["stdcell-functional.v"].read_text() == "\n".join(transformed), "noncanonical zero-delay model derivation")
    references = load(directory.parent.parent / "preflight.json")["references"]
    recorded = {str(Path(r["path"]).resolve()): r["sha256"] for r in references if "path" in r}
    for source, digest in models["source_hashes"].items():
        require(recorded.get(str(Path(source).resolve())) == digest, "replay source not bound by public preflight")
    results = check["process_results"]
    require(results and len(results) == len(check["processes"]) and
            all(r["outcome"] == "exited" and r["code_or_ocaml_signal"] == 0 and r["succeeded"] is True for r in results),
            "external process failed/timed out")
    for process in check["processes"]:
        for key in ("stdout", "stderr"):
            path = inside(directory, process[key])
            require(path.is_file(), "missing external process log")
            retained[prefix + process[key]] = path
    commands = [" ".join(command) for command in check["commands"]]
    require(any("iverilog" in c for c in commands) and any("vvp" in c for c in commands)
            and any("precheck.py" in c for c in commands), "external precheck/compile/replay commands missing")
    require(check["reports"], "external TT reports missing")
    for name in ["testbench.v", *check["logs"], *check["reports"]]:
        path = inside(directory, name)
        require(path.is_file(), "missing postcheck evidence: " + name)
        retained[prefix + name] = path
    return check
