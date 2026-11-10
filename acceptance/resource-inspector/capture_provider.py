#!/usr/bin/env python3
"""C-owned isolated PT6 capture. Run in the existing opam environment; six jobs.

Uses the public dependency-store helper with private captured-source builds. It
performs read-only Git source observation, never changes checkout/app selections.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
EXAMPLE = Path(__file__).resolve().parents[2]
WB = EXAMPLE.parent / "hardcaml_workbench"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new receipt directory")
    parser.add_argument("--preserve-current", action="store_true", help="retain the existing private PT6 selection; return generation explicitly")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.parent.is_dir():
        parser.error("receipt parent must exist")
    output.mkdir()
    g = module("pt6_groundwork", WB / "scripts/test-resource-inspector.py")
    dep = module("pt6_dependency", EXAMPLE / "scripts/asic_dependency.py")
    if args.preserve_current:
        current = EXAMPLE / ".dev/asic-pt6/current"
        g.require(current.is_symlink(), "Existing dedicated PT6 pointer required")

        class CaptureOs:
            def __getattr__(self, name):
                return getattr(os, name)

            def replace(self, source, destination):
                if Path(destination) == current:
                    # Suppress only publication of this new private selection. The
                    # generation/receipt/activation remain available by exact path.
                    Path(source).unlink()
                else:
                    os.replace(source, destination)

        dep.os = CaptureOs()
    before = g.protected(EXAMPLE)
    g.write_new(output / "protected-before.json", before)
    shutil.copyfile(Path(__file__), output / "tested-capture.py")
    receipt = dict(status="failed", scope="PT6 C private provider capture; no EDA",
                   jobs=6, preserve_current=args.preserve_current, commands=[], tested_script_sha256=g.sha(output / "tested-capture.py"))
    old_materialize = dep.materialize

    def materialize(entries, destination):
        files = {name: dict(mode=mode, sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
                 for name, (mode, raw) in sorted(entries.items())}
        g.write_new(output / "captured-source-files.json", files)
        receipt["captured_source_sha256"] = dep.checksum(entries)
        return old_materialize(entries, destination)

    dep.materialize = materialize

    def runner(argv, cwd=None, env=None):
        stem = "%03d" % len(receipt["commands"])
        started = time.monotonic()
        with (output / (stem + ".stdout")).open("wb") as out, (output / (stem + ".stderr")).open("wb") as err:
            process = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err, timeout=900)
        receipt["commands"].append(dict(argv=list(map(str, argv)), cwd=str(cwd),
                                        exit=process.returncode, seconds=time.monotonic() - started, stem=stem))
        if process.returncode:
            raise dep.Error("capture command failed; see " + str(output / (stem + ".stderr")))
        return (output / (stem + ".stdout")).read_bytes()

    try:
        provider = dep.refresh(EXAMPLE.parent / "hardcaml_asic", "development",
                               dep.store_path(EXAMPLE / ".dev/asic-pt6"),
                               dep.record_read(EXAMPLE / "asic-dependency.json"), runner=runner, jobs=6)
        g.require(provider["snapshot_sha256"] == receipt["captured_source_sha256"], "exact captured source digest")
        generation = Path(provider["generation"])
        receipt["provider"] = provider
        receipt["binaries"] = {str(p.relative_to(generation)): g.sha(p)
                               for p in sorted((generation / "bin").glob("hardcaml-asic*")) if p.is_file()}
        g.require("bin/hardcaml-asic-experimental-resource-inspect" in receipt["binaries"], "new bridge companion installed")
        receipt["status"] = "captured"
    finally:
        after = g.protected(EXAMPLE)
        g.write_new(output / "protected-after.json", after)
        old_pointers = before["current_pointers"]
        receipt["existing_pointers_unchanged"] = all(after["current_pointers"].get(k) == v for k, v in old_pointers.items())
        receipt["protected_bytes_unchanged"] = before["files"] == after["files"]
        receipt["new_pointers"] = {k: v for k, v in after["current_pointers"].items() if k not in old_pointers}
        if not receipt["existing_pointers_unchanged"] or not receipt["protected_bytes_unchanged"]:
            receipt["status"] = "failed"
        g.write_new(output / "receipt.json", receipt)
        print(json.dumps(dict(output=str(output), status=receipt["status"],
                              generation=receipt.get("provider", {}).get("generation")), indent=2))
    g.require(receipt["status"] == "captured", "private capture and protected-state checks")


if __name__ == "__main__":
    main()
