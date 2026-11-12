"""Private program-memory named-flow/resource preparation; no tools or nested builds."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

exporter, source = (Path(p).resolve() for p in sys.argv[1:])


def invoke(*args, cwd=None):
    return subprocess.run([str(exporter), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, timeout=30)


def successful(*args, **kwargs):
    result = invoke(*args, **kwargs)
    assert result.returncode == 0, (result.args, result.stdout, result.stderr)
    return json.loads(result.stdout)


def selection(endpoint):
    return ["--flow", "stock256-r0", "--profile", "qualification", "--endpoint", endpoint,
            "--source-root", source, "--json"]


with tempfile.TemporaryDirectory(prefix="program-memory-named-", dir="/tmp/opencode") as tmp:
    root = Path(tmp)
    # Daemon discovery runs from its project cwd and supplies no source root.
    discovery = successful("flow", "list", "--json", cwd=root)
    assert discovery["contract"] == "hardcaml-asic.flow-list" and discovery["schema_version"] == 1
    declaration = discovery["declaration"]
    assert declaration["default"] == {"flow": "stock256-r0", "profile": "qualification"}
    assert len(declaration["entries"]) == 1
    entry = declaration["entries"][0]
    assert entry["methodology"]["endpoints"] == ["synthesis", "floorplan", "placement", "cts", "routing", "timing"]
    assert entry["methodology"]["input"] == "fresh"
    assert [p["id"] for p in entry["profiles"]] == ["qualification"]
    description = successful("flow", "describe", "--flow", "stock256-r0", "--json", cwd=root)
    assert description["contract"] == "hardcaml-asic.flow-describe" and description["entry"] == entry
    assert description["capabilities"]["stage_selection"] == "complete-prefix-through-declared-endpoint"
    store = root / "scoped publication with spaces"
    plans = {}
    for endpoint in ("synthesis", "floorplan", "placement", "cts", "routing", "timing"):
        preview = invoke("prepare", source, endpoint)
        assert preview.returncode == 0, preview.stderr
        preparation = json.loads(preview.stdout)
        assert preparation["kind"] == "hardcaml_asic.resource_preparation"
        assert preparation["coverage"]["measured_evidence"] is False
        assert preparation["coverage"]["collateral_files_verified"] is False
        assert preparation["coverage"]["compiled_source_proven"] is False
        bundle = root / endpoint
        emitted = invoke("export", source, bundle, endpoint)
        assert emitted.returncode == 0, emitted.stderr
        result = json.loads(emitted.stdout)
        assert result["preparation"] == preparation
        plan = successful("flow", "plan", *selection(endpoint), cwd=root)
        plans[endpoint] = plan
        assert plan == result["plan"]
        assert plan["methodology"]["recipe"] == {"schema_version": 4, "initial_boundary": None,
            "stages": entry["methodology"]["endpoints"][:entry["methodology"]["endpoints"].index(endpoint) + 1]}
        if endpoint == "synthesis":
            assert not store.exists()  # plan is nonpublishing
        receipt = successful("flow", "emit", *selection(endpoint), "--results-root", store,
                             "--expected-plan-identity", plan["plan_identity"], cwd=root)
        assert receipt["kind"] == "bundle_emission" and receipt["schema_version"] == 1
        assert receipt["plan"] == plan and receipt["plan_identity"] == plan["plan_identity"]
        publication = Path(receipt["output_dir"])
        assert publication.is_relative_to(store / "bundles") and publication.is_dir()
        assert receipt["bundle_identity"] == plan["bundle_identity"]
        again = successful("flow", "emit", *selection(endpoint), "--results-root", store,
                           "--expected-plan-identity", plan["plan_identity"], cwd=root)
        assert again["reused"] is True and again["output_dir"] == str(publication)
        manifest = json.loads((bundle / "manifest.json").read_text())
        assert result["plan"]["bundle_identity"] == manifest["identity"]
        contract = manifest["macro_contract"]
        assert contract["schema_version"] == 2 and contract["execution"] == "fresh_full"
        assert len(contract["macros"]) == 1
        macro = contract["macros"][0]
        assert macro["resource"] == "program" and macro["instance"] == "hc_resource_7_program"
        assert macro["module"] == "RM_IHPSG13_1P_256x16_c2_bm_bist"
        assert contract["physical_plan"]["macros"][0]["location_um"] == [40., 81.]
        assert json.loads((publication / "manifest.json").read_text()) == manifest
        assert {"asics/program_memory/verif/segmented_consumer.ml", "asics/program_memory/verif/dune"} <= {
            row["path"] for row in manifest["source_inputs"]}
        for file in manifest["files"]:
            assert hashlib.sha256((publication / file["path"]).read_bytes()).hexdigest() == file["sha256"]
        rtl = (bundle / "src" / (manifest["top_module"] + ".v")).read_text()
        assert rtl.count("RM_IHPSG13_1P_256x16_c2_bm_bist") == 1
        before = {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in bundle.rglob("*") if p.is_file()}
        refused = invoke("export", source, bundle, endpoint)
        assert refused.returncode != 0
        assert before == {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in bundle.rglob("*") if p.is_file()}
    rejected = invoke("export", source, root / "signoff", "signoff")
    assert rejected.returncode != 0 and not (root / "signoff").exists()
    assert "endpoint" in rejected.stderr.lower() or "signoff" in rejected.stderr.lower()
    for command in ("plan", "emit"):
        rejected = invoke("flow", command, *selection("signoff"),
                          *( ["--results-root", root / "no-signoff-publication"] if command == "emit" else []))
        assert rejected.returncode != 0 and not (root / "no-signoff-publication").exists()
    rejected = invoke("flow", "emit", *selection("timing"), "--results-root", root / "stale",
                      "--expected-plan-identity", "0" * 64)
    assert rejected.returncode != 0 and not (root / "stale").exists()
    changed = successful("flow", "plan", *selection("timing"), "--set", "SYNTH_ABC_BUFFERING=true")
    assert changed["plan_identity"] != plans["timing"]["plan_identity"]
    config = json.loads(changed["configuration_bytes"])
    assert config["SYNTH_ABC_BUFFERING"] is True
    rejected = invoke("flow", "emit", *selection("timing"), "--set", "SYNTH_ABC_BUFFERING=true",
                      "--results-root", root / "wrong-selection", "--expected-plan-identity", plans["timing"]["plan_identity"])
    assert rejected.returncode != 0 and not (root / "wrong-selection").exists()
    unknown_profile = selection("timing")
    unknown_profile[3] = "missing"
    for args in (("flow", "describe", "--flow", "missing", "--json"),
                 ("flow", "plan", *selection("timing"), "--set", "SYNTH_ABC_BUFFERING=1"),
                 ("flow", "plan", *selection("timing"), "--flow", "stock256-r0"),
                 ("flow", "plan", *unknown_profile),
                 ("flow", "plan", *selection("timing"), "--set", "UNKNOWN=true"),
                 ("flow", "plan", *selection("timing"), "--project-root", root),
                 ("flow", "run", *selection("timing"))):
        assert invoke(*args).returncode != 0, args
    preview = successful("preview", *selection("timing"))
    assert preview == successful("prepare", source, "timing")
    prepared = invoke("prepare", *selection("timing"), "--results-root", root / "resource-preparation")
    assert prepared.returncode == 0, prepared.stderr
    allocated, terminal = map(json.loads, prepared.stdout.splitlines())
    assert allocated["event"] == "allocated" and terminal["event"] == "terminal"
    assert terminal["record"]["status"] == "completed" and terminal["record"]["exit_code"] == 0
    attempt = Path(terminal["attempt"])
    assert attempt.is_relative_to(root / "resource-preparation")
    assert json.loads((attempt / "resources.json").read_text()) == preview
    snapshot = terminal["record"]["snapshot"]
    assert hashlib.sha256((attempt / snapshot["path"]).read_bytes()).hexdigest() == snapshot["sha256"]
print("Private program-memory CLI: production flow discovery/description, six schema-4 plans, "
      "scoped verified publication/reuse, source closure, request/preview mismatch vetoes, "
      "prepare lifecycle and legacy compatibility, unsupported Signoff/run; no EDA")
