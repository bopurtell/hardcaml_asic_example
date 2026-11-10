#!/usr/bin/env python3
"""Record C's initial PT6 acceptance closure; read-only except a new receipt file."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
EXAMPLE = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
WB = EXAMPLE.parent / "hardcaml_workbench"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, required=True)
    args = parser.parse_args()
    g = module("pt6_closeout_groundwork", WB / "scripts/test-resource-inspector.py")
    dep = module("pt6_closeout_dependency", EXAMPLE / "scripts/asic_dependency.py")
    g.verify(EXAMPLE, g.FIXTURES)
    capture = g.load(ROOT / "capture-01/receipt.json")
    protected = g.protected(EXAMPLE)
    g.require(protected == g.load(ROOT / "capture-01/protected-after.json"), "all existing pointers/configuration and protected bytes unchanged")
    generation = Path(capture["provider"]["generation"])
    for name, digest in capture["binaries"].items():
        g.require(g.sha(generation / name) == digest, "captured installed companion unchanged: " + name)
    receipts = {"public": ROOT / "public-04", "retained_http_pty": ROOT / "pty-05", "synthetic_http_pty": args.synthetic.resolve()}
    expected = {"public": "public_bridge_passed_ui_pending", "retained_http_pty": "retained_http_and_initial_pty_passed",
                "synthetic_http_pty": "http_and_synthetic_pty_passed"}
    results = {}
    for name, directory in receipts.items():
        result = g.load(directory / "result.json")
        g.require(result["status"] == expected[name] and result["protected_unchanged"], "passing protected receipt: " + name)
        g.require(all(check["passed"] for check in result["checks"]), "all recorded checks: " + name)
        results[name] = dict(directory=str(directory), status=result["status"], checks=len(result["checks"]),
                             receipt_sha256=g.sha(directory / "result.json"))
    # Independent replay of already captured real screen bytes, not another UI run.
    screen_checks = []
    screens = sorted((ROOT / "pty-05").glob("*timing-native*.txt"))
    for label, token in (
        ("actual output reported load", '"reported_load": 0.004815'),
        ("absent reported input load stays null", '"reported_load": null'),
        ("actual fast analysis label", '"analysis_corner": "nom_fast_1p32V_m40C"'),
        ("distinct recorded SRAM model temperature", "fast_1p32V_m55C.lib"),
        ("external model reference is not retained verification", "recorded_external_model_not_read")):
        matches = [p for p in screens if token in p.read_text()]
        g.require(matches, "retained actual PTY screen replay: " + label)
        screen_checks.append(dict(assertion=label, token=token, screen=str(matches[0].relative_to(ROOT)), sha256=g.sha(matches[0])))
    # Freeze every retained receipt byte, including diagnostic fixtures and failed attempts.
    archive = {str(p.relative_to(ROOT)): g.sha(p) for p in sorted(ROOT.rglob("*"))
               if p.is_file() and p != args.receipt.resolve() and not p.is_symlink()}
    synthetic = {str(p.relative_to(args.synthetic)): g.sha(p) for p in sorted(args.synthetic.rglob("*"))
                 if p.is_file() and not p.is_symlink()}
    moving = dep.development(EXAMPLE.parent / "hardcaml_asic", EXAMPLE / ".dev/asic-pt6")
    current_digest = dep.checksum(moving)
    output = dict(status="initial_acceptance_passed", scope="C initial PT6 public/native HTTP/PTY acceptance; independent-review source freeze pending",
                  results=results, retained_screen_replay=screen_checks,
                  provider=capture["provider"], binaries=capture["binaries"],
                  captured_source_files_sha256=g.sha(ROOT / "capture-01/captured-source-files.json"),
                  moving_source_sha256=current_digest,
                  moving_source_matches_capture=current_digest == capture["provider"]["snapshot_sha256"],
                  protected=protected, all276_and333_unchanged=True,
                  receipt_files=archive, synthetic_files=synthetic,
                  retained_timeout=dict(directory="public-02", status="outer_tool_timeout", seconds=120,
                                        result="not a pass; no result.json published; raw partial logs retained"),
                  limits=["captured dirty development bytes, not historical producer authentication",
                          "sampled timing; electrical compliance not assessed; no EDA qualification",
                          "initial A/B implementation capture; independent review may require a new capture",
                          "C did not independently repeat every named/finalization/workflow lineage branch in A's focused suite"],
                  recorder_sha256=g.sha(Path(__file__)))
    g.write_new(args.receipt.resolve(), output)
    print(json.dumps(dict(receipt=str(args.receipt.resolve()), status=output["status"], results=results,
                          moving_source_matches_capture=output["moving_source_matches_capture"]), indent=2))


if __name__ == "__main__":
    main()
