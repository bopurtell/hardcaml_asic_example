#!/usr/bin/env python3
"""Exercise corrected public evidence semantics with explicitly mutated copies."""
import argparse
import json
from pathlib import Path
import shutil
from check_acceptance import inspect
from real_tools import dump
from record_command import sha


def rebind(fixture, metadata, *, reorder_keys=False):
    # This is producer-receipt fixture construction, not timing interpretation.
    inputs = [{"role": s["role"], "path": s["path"], "sha256": sha(fixture / s["path"])}
              for s in metadata["sources"] if s["role"] in ("manifest", "sdc", "netlist", "liberty", "driver")]
    receipt = json.loads((fixture / "receipt.json").read_text())
    receipt["inputs"] = inputs
    if reorder_keys:
        receipt = dict(reversed(list(receipt.items())))
        receipt["producer"] = dict(reversed(list(receipt["producer"].items())))
        receipt["inputs"] = [dict(reversed(list(s.items()))) for s in inputs]
    compact = json.dumps(receipt, separators=(",", ":"))
    (fixture / "receipt.json").write_text(compact + "\n")
    log = (fixture / "tool.log").read_text()
    lines = log.splitlines(keepends=True)
    assert sum(line.startswith("PT7_AUDIT_RECEIPT ") for line in lines) == 1
    (fixture / "tool.log").write_text("".join("PT7_AUDIT_RECEIPT " + compact + "\n"
                                              if line.startswith("PT7_AUDIT_RECEIPT ") else line for line in lines))
    process = json.loads((fixture / "process-result.json").read_text())
    process["receipt_sha256"] = sha(fixture / "receipt.json")
    dump(fixture / "process-result.json", process)
    for source in metadata["sources"]:
        source["sha256"] = sha(fixture / source["path"])
    dump(fixture / "audit.json", metadata)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generation", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--envelope-only", action="store_true")
    a = p.parse_args()
    a.output.mkdir()
    provider = a.generation.resolve() / "bin/hardcaml-asic-flow"
    baseline = inspect(provider, a.audit.resolve(), a.output / "baseline")
    assert baseline.returncode == 1 and json.loads(baseline.stdout)["verdict"] == "unavailable"
    results = []
    cases = [("coherent-sdc-prefix", 2), ("schema-999", 2), ("minimal-manifest", 2),
             ("source-copy-closure", 2), ("fatal-bracketed", 2), ("fatal-ansi", 2),
             ("oversized-line", 2), ("quoted-info", 1), ("reordered-object-keys", 1)]
    envelope_diagnostics = {
        "generated-null-absent": "missing bundle configuration key: PT7_NULL_SETTING",
        "resolved-null-absent": "missing bundle configuration key: PT7_NULL_SETTING",
        "simulation-sdc": "bundle simulation RTL/top mismatch",
        "runtime-empty": "invalid bundle runtime policy:",
        "runtime-contradictory": "invalid bundle runtime policy:",
        "floorplan-object": "bundle FP_DEF_TEMPLATE/floorplan reference mismatch",
        "floorplan-missing": "missing bundle FP_DEF_TEMPLATE resolved setting",
        "floorplan-ref-wrong-source": "invalid bundle floorplan reference",
    }
    if a.envelope_only:
        cases = [(case, 2) for case in envelope_diagnostics]
    for case, expected in cases:
        fixture = a.output / case
        shutil.copytree(a.audit, fixture)
        metadata = json.loads((fixture / "audit.json").read_text())
        if case == "coherent-sdc-prefix":
            original = (fixture / "top.sdc").read_text()
            (fixture / "top.sdc").write_text("# coherent diagnostic prefix mutation\n" + original)
        elif case in ("schema-999", "minimal-manifest", "source-copy-closure"):
            manifest = json.loads((fixture / "manifest.json").read_text())
            if case == "schema-999":
                manifest["schema_version"] = 999
            elif case == "minimal-manifest":
                manifest = {key: manifest[key] for key in ("identity", "schema_version", "project", "top_module", "timing_intent")}
            else:
                manifest["source_inputs"][0]["copy"] = "inputs/not-in-member-inventory"
            dump(fixture / "manifest.json", manifest)
        elif case in envelope_diagnostics:
            manifest = json.loads((fixture / "manifest.json").read_text())
            if case == "generated-null-absent":
                manifest["generated_settings"]["PT7_NULL_SETTING"] = None
            elif case == "resolved-null-absent":
                manifest["resolved_settings"].append({"key": "PT7_NULL_SETTING", "value": None, "owner": "diagnostic"})
            elif case == "simulation-sdc":
                manifest["simulation_sources"] = ["constraints/top.sdc"]
            elif case == "runtime-empty":
                manifest["requested_tools"]["runtime_policy"] = {}
            elif case == "runtime-contradictory":
                manifest["requested_tools"]["runtime_policy"]["implementation"]["dockerized"]["image_ref"] = "ghcr.io/librelane/librelane:not-the-requested-version"
            elif case == "floorplan-object":
                next(s for s in manifest["resolved_settings"] if s["key"] == "FP_DEF_TEMPLATE")["value"] = {"diagnostic": "not-a-string"}
            elif case == "floorplan-missing":
                manifest["resolved_settings"] = [s for s in manifest["resolved_settings"] if s["key"] != "FP_DEF_TEMPLATE"]
            elif case == "floorplan-ref-wrong-source":
                next(r for r in manifest["target"]["external_references"] if r["role"] == "Floorplan_def")["source"] = "PDK"
            dump(fixture / "manifest.json", manifest)
        elif case in ("fatal-bracketed", "fatal-ansi", "quoted-info", "oversized-line"):
            extra = {"fatal-bracketed": "[ERROR STA-9999] diagnostic fixture failure",
                     "fatal-ansi": "\x1b[31m[FATAL STA-9999] diagnostic fixture failure\x1b[0m",
                     "quoted-info": 'INFO: quoted report text "[ERROR STA-9999]" is not a fatal line',
                     "oversized-line": "INFO: " + "x" * 65536}[case]
            with (fixture / "tool.log").open("a") as out:
                out.write(extra + "\n")
        rebind(fixture, metadata, reorder_keys=case == "reordered-object-keys")
        result = inspect(provider, fixture.resolve(), a.output / (case + "-inspection"))
        row = {"case": case, "exit_code": result.returncode, "expected_exit": expected,
               "diagnostic": result.stderr.decode().strip(), "kind": "evidence_semantic_fixture_not_new_native_execution"}
        results.append(row)
        dump(a.output / "partial-results.json", results)
        assert result.returncode == expected, row
        if case in envelope_diagnostics:
            assert envelope_diagnostics[case] in row["diagnostic"], row
        if expected == 1:
            assert json.loads(result.stdout)["verdict"] == "unavailable"
    assertions = (["absent configuration keys differ from present null values",
                   "simulation SDC role, runtime policy and floorplan bindings reject with intended diagnostics",
                   "negative manifest fixtures retain asserted original build identity; semantic rejection precedes payload identity verification"]
                  if a.envelope_only else ["whole SDC prefix bound to original full manifest",
                        "unsupported/minimal manifest and broken source closure rejected",
                        "bracketed and ANSI fatal diagnostics rejected; line budget enforced",
                        "quoted INFO and equivalent object-key orders remain valid/unavailable"])
    dump(a.output / "summary.json", {"status": "pass", "cases": results,
         "assertions": assertions,
         "source_authentication": "retained producer assertions, not authenticated execution"})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
