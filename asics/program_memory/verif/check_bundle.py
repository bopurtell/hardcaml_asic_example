#!/usr/bin/env python3
"""Real-checkout bundle/CLI and vendor functional RTL acceptance; no Git writes, builds or EDA."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "physical"))
from physical_contract import check_contract, electrical_settings


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(args, code=0):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=60)
    require(result.returncode == code, f"{args}: exit {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


MACRO = "RM_IHPSG13_1P_256x16_c2_bm_bist"


def check_selection(args, selection, operation):
    cli, source = args.cli.resolve(), args.source_root.resolve()
    exact = selection == "exact"
    options = ["--selection", selection, "--operation", operation]
    check = json.loads(run([cli, "check", *options]).stdout)
    require(("Exact_mapping" if exact else "Explicit_flops") in check["resources_sexp"], "CLI selection")
    with tempfile.TemporaryDirectory(prefix=f"memory-{selection}-{operation}-", dir=source / ".dev") as tmp:
        work = Path(tmp)
        first, second = work / "first", work / "second"
        for output in (first, second):
            response = json.loads(run([cli, "emit", *options,
                                       "--source-root", source, "--output-dir", output]).stdout)
            manifest = json.loads((output / "manifest.json").read_text())
            require(response == {"identity": manifest["identity"], "output_dir": str(output)}, "emission receipt")
        files = tree(first)
        require(files == tree(second), "whole-bundle deterministic repeat emission")
        m = json.loads(files["manifest.json"])
        require(m["operation"] == operation.capitalize(), "explicit operation")
        payload = {k: v for k, v in m.items() if k != "identity"}
        require(digest(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()) == m["identity"],
                "manifest identity digest")
        require(m["project"] == "program_memory_specimen" and m["top_module"] == "tt_um_program_memory", "project/top")
        require(m["target"]["technology"] == "ihp-sg13cmos5l" and m["target"]["tiles"] == "6x4", "production target")
        require(m["source_revision"] == run(["git", "-C", source, "rev-parse", "HEAD"]).stdout.strip(), "actual revision")
        require({x["path"] for x in m["files"]} == set(files) - {"manifest.json"}, "complete file inventory")
        for item in m["files"]:
            require(digest(files[item["path"]]) == item["sha256"], f"file digest {item['path']}")
        inputs = sorted(["asic-dependency.json", "dune-project", "asics/program_memory/README.md", "asics/program_memory/project/dune",
                         "asics/program_memory/project/memory_cli.ml", "asics/program_memory/project/program_memory.ml"])
        require([x["path"] for x in m["source_inputs"]] == inputs, "complete generation input inventory")
        for item in m["source_inputs"]:
            require(files[item["copy"]] == (source / item["path"]).read_bytes(), "copied source bytes")
            require(digest(files[item["copy"]]) == item["sha256"], "source input hash")
            status = run(["git", "-C", source, "status", "--porcelain=v1", "--untracked-files=all", "--", item["path"]]).stdout.rstrip("\n")
            require(item["git_status"] == status, f"actual Git status {item['path']}")
        request = "((kind single_port_ram) (contract ((width 16) (depth 256) (read_latency 1) (port 1rw) (disabled_output hold) (write_output unspecified))))"
        for key, elaborated, role in (("resources", "Selected_implementation", "Generated_synthesis_rtl"),
                                      ("simulation_resources", "Behavioral_model", "Generated_behavioral_model")):
            require(len(m[key]) == 1, "one program resource")
            r = dict(m[key][0])
            r["request"] = " ".join(r["request"].split())
            expected_selection = (f"((implementation (Macro {MACRO})) (reason (Exact_mapping (technology ihp-sg13cmos5l))))"
                                  if exact else "((implementation Flops) (reason Explicit_flops))")
            require(r["id"] == "program" and r["request"] == request, "stable resource contract")
            require(r["requirement"] == ("Exact" if exact else "Flops"), "explicit requirement")
            require(" ".join(r["selection"].split()) == expected_selection, "selection without fallback")
            require(r["policy"] == "(Rule (Instance program))" and r["elaborated_as"] == elaborated, "policy/mode")
            if not exact or key == "simulation_resources":
                require(r["source_roles"] == [role], "generated source role")
            else:
                require(len(r["source_roles"]) == 11, "complete macro collateral roles")
        require(m["synthesis_sources"] == ["src/tt_um_program_memory.v"] and
                m["simulation_sources"] == ["simulation/tt_um_program_memory.v"], "separate RTL sets")
        require(files[m["synthesis_sources"][0]] != files[m["simulation_sources"][0]], "distinct implementation/behavioral RTL")
        config = json.loads(files["src/config.json"])
        require(config["DESIGN_NAME"] == m["top_module"] and config["PDK"] == "ihp-sg13cmos5l", "config target agreement")
        if not (exact and operation == "hardening"):
            for key, value in {"RUN_KLAYOUT_DRC": 0, "FP_PDN_VPITCH": 50.0,
                               "FP_PDN_VWIDTH": 2.1, "FP_PDN_MULTILAYER": 0}.items():
                require(config[key] == value, "nonphysical path retains template default: " + key)
            require(not (set(electrical_settings([])) & set(config)),
                    "nonphysical paths do not inherit physical electrical repair settings")
        models, defines = [], []
        if exact:
            contract = m["macro_contract"]
            physical = operation == "hardening"
            require(contract["schema_version"] == (2 if physical else 1), "operation-specific contract schema")
            require(contract["execution"] == ("fresh_full" if physical else "synthesis_only"),
                    "public execution boundary")
            if physical:
                check_contract(contract, config, files)
            else:
                require("physical_plan" not in contract and not any(p.startswith("physical/") for p in files),
                        "schema-1 synthesis has no physical execution inputs")
            require(len(contract["macros"]) == 1, "one macro contract")
            macro = contract["macros"][0]
            require((macro["resource"], macro["module"], macro["instance"]) ==
                    ("program", MACRO, "hc_resource_7_program"), "logical/actual macro identity")
            location = [40.0 if physical else 42.0, 81.0]
            intent = macro["physical_intent"]
            for key, expected in {
                "location_um": location, "orientation": "R0", "halo_um": 2.0,
                "power": {"VDD!": "VPWR", "VDDARRAY!": "VPWR", "VSS!": "VGND"},
            }.items():
                require(intent[key] == expected, "explicit physical intent: " + key)
            if not physical:
                require(intent["execution"] == "unsupported_pending_verified_power_geometry",
                        "synthesis intent does not authorize physical execution")
            require(len(macro["collateral"]) == 11, "complete typed collateral")
            require(len(contract["blackbox_sources"]) == 1, "one synthesis stub")
            rtl = files[m["synthesis_sources"][0]].decode()
            require(len(re.findall(r"\b" + MACRO + r"\s+hc_resource_7_program\s*\(", rtl)) == 1,
                    "one actual stock macro instance")
            require(len(re.findall(r"\balways\s*@", rtl)) == 2 and
                    re.findall(r"\breg\s+(\[[^]]+\])\s+\w+;", rtl) == ["[7:0]", "[7:0]"],
                    "only the two existing byte staging registers")
            simulation = contract["implementation_simulation"]
            defines = simulation["defines"]
            require(defines == ["FUNCTIONAL"] and len(simulation["models"]) == 2, "functional model closure")
            for reference in simulation["models"]:
                require(reference.startswith("pdk_dir::"), "typed PDK-relative model")
                path = args.pdk_root.resolve() / "ihp-sg13cmos5l" / reference.removeprefix("pdk_dir::")
                require(path.is_file(), f"vendor model exists: {path}")
                models.append(path)
            require("MACROS" in config and "EXTRA_VERILOG_MODELS" in config, "public synthesis macro config")
            require(config["MACROS"][MACRO]["instances"] == {
                "hc_resource_7_program": {"location": location, "orientation": "R0"}}, "config placement")
            corners = {"nom_fast_1p32V_m40C": "fast_1p32V_m55C",
                       "nom_slow_1p08V_125C": "slow_1p08V_125C",
                       "nom_typ_1p20V_25C": "typ_1p20V_25C"}
            require(set(config["STA_CORNERS"]) == set(corners), "exact STA corners")
            require(config["MACROS"][MACRO]["lib"] == {
                k: [f"pdk_dir::libs.ref/sg13cmos5l_sram/lib/{MACRO}_{v}.lib"]
                for k, v in corners.items()}, "exact Liberty bindings")
            require(contract["fast_temperature_difference"] == "standard_cells_m40C_macro_m55C",
                    "fast temperature difference retained")
        else:
            require("macro_contract" not in m, "flops have no macro contract")
        if args.compare_bundle:
            baseline = tree(args.compare_bundle.resolve())
            previous = json.loads(baseline["manifest.json"])
            require(previous["operation"] == "Hardening" and
                    previous["macro_contract"] == m["macro_contract"], "refresh retains physical contract")
            for item in previous["files"]:
                require(digest(baseline[item["path"]]) == item["sha256"], "baseline hash: " + item["path"])
            for path in ("physical/macro-plan.json", "constraints/top.sdc",
                         *m["synthesis_sources"], *m["simulation_sources"]):
                require(files[path] == baseline[path], "refresh preserves bytes: " + path)
            path = "physical/pdn.tcl"
            if args.compare_profile == "runtime":
                require(files == baseline, "runtime-only refresh preserves every bundle byte and identity")
                print("PASS runtime-only refresh: every bundle byte and identity unchanged")
            elif args.compare_profile == "pdn":
                require(files["src/config.json"] == baseline["src/config.json"], "PDN-only refresh retains config")
                require(files[path] != baseline[path], "refresh must update generated PDN Tcl")
                print("PASS refresh: unchanged contract/config/plan/SDC/RTL; updated Tcl and bundle identity")
            else:
                require(files[path] == baseline[path], "electrical refresh retains PDN Tcl")
                old_config = json.loads(baseline["src/config.json"])
                expected = electrical_settings(config["STA_CORNERS"])
                changed = {key for key in old_config.keys() | config.keys()
                           if old_config.get(key) != config.get(key)}
                expected_changes = {key for key, value in expected.items() if old_config.get(key) != value}
                require(changed == expected_changes and bool(changed), "only canonical electrical settings change")
                require(config == {**old_config, **expected}, "exact canonical electrical configuration delta")
                print("PASS refresh: unchanged contract/plan/Tcl/SDC/RTL; only canonical electrical settings change")
                print("Changed settings:", ", ".join(sorted(changed)))
            if args.compare_profile != "runtime":
                require(m["identity"] != previous["identity"], "refresh updates bundle identity")
            for path in ("physical/macro-plan.json", "physical/pdn.tcl"):
                print(f"SHA256 {path}: baseline={digest(baseline[path])} current={digest(files[path])}")
        saved = tree(first)
        run([cli, "emit", *options, "--source-root", source, "--output-dir", first], code=1)
        require(tree(first) == saved, "nonempty bundle refusal preserves bytes")
        if args.skip_rtl:
            print("SKIP RTL replay: explicit --skip-rtl; structural register checks remain enabled")
        elif shutil.which("iverilog") and shutil.which("vvp"):
            for key in ("synthesis_sources", "simulation_sources"):
                compiled = work / (key + ".vvp")
                implementation = exact and key == "synthesis_sources"
                run(["iverilog", "-g2012", *["-D" + x for x in defines if implementation],
                     "-s", "memory_replay", "-o", compiled,
                     source / "asics/program_memory/verif/replay.v", *[first / x for x in m[key]],
                     *(models if implementation else [])])
                print(selection, operation, key, run(["vvp", "-n", compiled]).stdout.strip())
                run(["vvp", "-n", compiled, "+negative"], code=1)
            if exact:
                core = work / "core.v"
                core_rtl = run([args.core_exporter.resolve(), "--export-exact-core"]).stdout
                require(not re.search(r"\b(reg|always)\b", core_rtl), "no architectural registers added to core")
                core.write_text(core_rtl)
                compiled = work / "core.vvp"
                run(["iverilog", "-g2012", *["-D" + x for x in defines], "-s", "memory_core_replay",
                     "-o", compiled, source / "asics/program_memory/verif/core_replay.v", core, *models])
                print(run(["vvp", "-n", compiled]).stdout.strip())
                run(["vvp", "-n", compiled, "+negative"], code=1)
            print(f"PASS {selection} {operation} generated RTL and negative oracles")
        else:
            require(not args.require_rtl, "--require-rtl requires iverilog and vvp")
            print("SKIP generated RTL: iverilog/vvp unavailable")
    print(f"PASS {selection} {operation} bundles: repeat bytes, hashes/provenance, explicit program policy, separate RTL, nonempty refusal")
    return {key: files[m[key][0]] for key in ("synthesis_sources", "simulation_sources")}


def check_unsupported_hardening(args):
    """Explicit transitional mode: never silently skip a supported physical route."""
    cli, source = args.cli.resolve(), args.source_root.resolve()
    options = ["--selection", "exact", "--operation", "hardening"]
    with tempfile.TemporaryDirectory(prefix="memory-unsupported-", dir=source / ".dev") as tmp:
        output = Path(tmp) / "bundle"
        for command in ([cli, "check", *options],
                        [cli, "emit", *options, "--source-root", source, "--output-dir", output]):
            result = run(command, code=1)
            require("SRAM hardening is unsupported" in result.stderr, "expected old-provider physical gate")
            require(not output.exists(), "unsupported operation must not emit a bundle")
    print("PASS expected old-provider Exact Hardening rejection; physical acceptance remains pending")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--core-exporter", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--pdk-root", type=Path, required=True)
    parser.add_argument("--require-rtl", action="store_true")
    parser.add_argument("--operations", nargs="+", choices=("synthesis", "hardening"),
                        default=["synthesis", "hardening"])
    parser.add_argument("--selections", nargs="+", choices=("flops", "exact"), default=["flops", "exact"])
    parser.add_argument("--skip-rtl", action="store_true", help="focused emission audit without repeating RTL replay")
    parser.add_argument("--compare-bundle", type=Path,
                        help="refresh regression against an immutable Exact Hardening bundle")
    parser.add_argument("--compare-profile", choices=("pdn", "electrical", "runtime"), default="pdn",
                        help="expected refresh delta (default: PDN Tcl only)")
    parser.add_argument("--expect-hardening-unsupported", action="store_true",
                        help="require the old provider's Exact Hardening rejection, not a skip")
    args = parser.parse_args()
    require(not (args.skip_rtl and args.require_rtl), "--skip-rtl conflicts with --require-rtl")
    if args.compare_bundle:
        require(args.operations == ["hardening"] and args.selections == ["exact"],
                "--compare-bundle requires --operations hardening --selections exact")
    require((args.source_root / ".dev").is_dir(), "existing consumer .dev required")
    run([args.cli.resolve(), "--help"])
    for bad in ([], ["check"], ["check", "--selection", "auto"],
                ["check", "--selection", "exact"],
                ["check", "--operation", "synthesis"],
                ["check", "--selection", "exact", "--operation", "full"],
                ["check", "--selection", "exact", "--operation", "synthesis", "--operation", "hardening"],
                ["check", "--selection", "flops", "--selection", "exact"],
                ["emit", "--selection", "flops"],
                ["check", "--selection", "flops", "--output-dir", "unused"]):
        run([args.cli.resolve(), *bad], code=2)
    circuits = {}
    for operation in args.operations:
        for selection in args.selections:
            if operation == "hardening" and selection == "exact" and args.expect_hardening_unsupported:
                check_unsupported_hardening(args)
            else:
                circuits[selection, operation] = check_selection(args, selection, operation)
    for selection in ("flops", "exact"):
        if (selection, "synthesis") in circuits and (selection, "hardening") in circuits:
            require(circuits[selection, "synthesis"] == circuits[selection, "hardening"],
                    selection + " operation must not change implementation or simulation hardware")
            print(f"PASS {selection} operation-independent RTL bytes")


if __name__ == "__main__":
    main()
