#!/usr/bin/env python3
"""Close out a NEW evidence generation with retained identities and checksums."""
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
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir()
    generation = a.generation.resolve(strict=True)
    shutil.copyfile(generation / "receipt.json", a.output / "provider-receipt.json")
    source = ROOT.parent / "hardcaml_asic/docs/development"
    for name in ("pt7-timing-intent.md", "pt7-library-handoff.md", "pt7-evidence-handoff.md"):
        shutil.copyfile(source / name, a.output / name)
    scripts = a.output / "consumer-sources"
    scripts.mkdir()
    for path in sorted((ROOT / "tooling_acceptance/timing").rglob("*")):
        if path.is_file():
            target = scripts / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    shutil.copyfile(ROOT / "tooling_acceptance/timing/controls/pt7_tool.py", scripts / "pt7_tool.py")
    for name in ("pt7_timing_findings.md", "pt7_timing_acceptance.md"):
        shutil.copyfile(ROOT / "docs" / name, a.output / name)
    binaries = [identity(p) for p in sorted((generation / "bin").iterdir()) if p.is_file()]
    libraries = [identity(p) for p in sorted((generation / "lib/hardcaml_asic").rglob("*"))
                 if p.is_file() and p.suffix in (".a", ".cmxa", ".cma", ".cmxs")]
    compiled = [identity(p) for p in sorted((ROOT / "_build_pt7/default/tooling_acceptance/timing/basic/.timing_cli.eobjs/native").iterdir())]
    compiled += [identity(ROOT / "_build_pt7/default/tooling_acceptance/timing/basic/timing_cli.exe")]
    dump(a.output / "producer-identities.json", {"installed_binaries": binaries,
         "installed_archives": libraries, "emitter_compiled_artifacts": compiled,
         "identity_scope": "local dirty development capture; not authenticated execution or a clean-source stamp"})
    bundle = EVIDENCE / "synth-scalar-01-bundle"
    manifest = json.loads((bundle / "manifest.json").read_text())
    for f in manifest["files"]:
        assert sha(bundle / f["path"]) == f["sha256"]
    for f in manifest["source_inputs"]:
        assert sha(ROOT / f["path"]) == f["sha256"], f["path"]
    protected = {str(p.relative_to(ROOT)): identity(p) for p in
                 [ROOT / ".gitignore", ROOT / "README.md", ROOT / "hardcaml-workbench-asic.sexp",
                  ROOT / "docs/resource_measurements.md", ROOT / "scripts/check_resource_measurements.py"]}
    pointers = {str(p.relative_to(ROOT)): str(p.readlink()) for p in sorted((ROOT / ".dev").glob("*/current")) if p.is_symlink()}
    dump(a.output / "protected-closeout-observation.json", {"files": protected, "old_provider_pointers": pointers,
         "scope": "read-only closeout observation; no earlier hash baseline is asserted"})
    checked = json.loads((EVIDENCE / "checked-scalar-02/summary.json").read_text())
    summary = {"schema": 1, "scope": "pt7-independent-example-bounded-real-tools",
               "recorded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "status": "scalar_actual_acceptance_with_open_bit_lookup_bug",
               "provider": json.loads((generation / "receipt.json").read_text()),
               "build_identity": manifest["identity"], "audit": "sta-scalar-02",
               "assertions": checked["assertions"], "sampled_paths": checked["downstream_sampled_paths"],
               "native_negatives": "native-negatives-summary-02.json",
               "public_inspection_exit_code": 1, "native_coverage": "unavailable",
               "unresolved": ["A-REAL-1: generated escaped bus-bit get_ports query returns no objects in OpenSTA 2.7.0",
                              "three sampled pre-layout hold violations: -0.044244 ns each",
                              "native exception coverage unavailable; sampled paths are not exhaustive",
                              "coordinator independent review remains separate"],
               "limits": {"build_jobs": 6, "serialized_tools": True, "container_cpus": 1,
                          "tool_threads": 1, "container_memory_bytes": 4294967296,
                          "container_pids": 128, "physical_place_route_jobs": 0},
               "regressions": ["regression-01/command.json", "emission-regression-01/command.json"],
               "scope_limits": ["standalone mapped-netlist ideal-clock/no-parasitics STA, typical corner only",
                                "no P&R, CDC/MTBF/reset-protocol or Protemu qualification",
                                "retained hash-bound producer assertions, not cryptographic execution attestation"]}
    dump(a.output / "summary.json", summary)
    inventory = [dict(path=str(p.relative_to(EVIDENCE)), bytes=p.stat().st_size, sha256=sha(p))
                 for p in sorted(EVIDENCE.rglob("*")) if p.is_file()]
    dump(a.output / "checksums.json", {"files": inventory, "file_count": len(inventory),
         "total_bytes": sum(f["bytes"] for f in inventory),
         "scope": "all retained PT.7 evidence files before this checksums file; no historical SRAM association"})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
