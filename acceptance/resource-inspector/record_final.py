#!/usr/bin/env python3
"""C final r3/B acceptance closure; no build, provider query or pointer publication."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
EXAMPLE = ROOT.parents[1]
WB = EXAMPLE.parent / "hardcaml_workbench"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    g = module("final_groundwork", WB / "scripts/test-resource-inspector.py")
    dep = module("final_dependency", EXAMPLE / "scripts/asic_dependency.py")
    codec = module("final_native_codec", WB / "demo/synthetic_flow/http_client.py")
    g.verify(EXAMPLE, g.FIXTURES)
    capture = g.load(ROOT / "capture-final/receipt.json")
    protected = g.protected(EXAMPLE)
    g.require(capture["status"] == "captured" and capture["preserve_current"], "nonpublishing final capture")
    g.require(capture["existing_pointers_unchanged"] and capture["protected_bytes_unchanged"], "capture protection")
    g.require(protected == g.load(ROOT / "capture-final/protected-before.json"), "all pointers/app/history unchanged since final capture")
    generation = Path(capture["provider"]["generation"])
    for name, digest in capture["binaries"].items():
        g.require(g.sha(generation / name) == digest, "immutable final binary: " + name)
    initial = g.load(ROOT / "capture-01/receipt.json")
    for name, digest in initial["binaries"].items():
        g.require(g.sha(Path(initial["provider"]["generation"]) / name) == digest, "initial generation preserved: " + name)
    old = g.load(ROOT / "closeout-02.json")
    immutable_prefixes = ("capture-01/", "public-", "http-", "pty-")
    preserved = 0
    for relative, digest in old["receipt_files"].items():
        if relative.startswith(immutable_prefixes):
            g.require(g.sha(ROOT / relative) == digest, "historical receipt unchanged: " + relative)
            preserved += 1
    broad = g.load(ROOT / "wb-broad-final/receipt.json")
    for relative, digest in broad["sources_after"].items():
        g.require(g.sha(WB / relative) == digest, "final WB product source unchanged: " + relative)
    for binary in broad["binaries_after"].values():
        g.require(g.sha(Path(binary["path"])) == binary["sha256"], "matching final WB binary")
    routes = {
        "public_bridge": (ROOT / "public-final-01", "result.json", "public_bridge_passed_ui_pending", 533),
        "actual_http_pty": (ROOT / "actual-final-03", "result.json", "retained_http_and_initial_pty_passed", 52),
        "synthetic_http_pty": (args.synthetic.resolve(), "result.json", "http_and_synthetic_pty_passed", 70),
        "wb_broad": (ROOT / "wb-broad-final", "receipt.json", "passed", None),
        "unified": (ROOT / "wb-unified-final", "receipt.json", "passed", 99),
        "saved_custom_resources": (ROOT / "wb-saved-layout-final", "receipt.json", "passed", 17),
        "asic_full_default": (ROOT / "asic-full-final-01", "receipt.json", "passed", None),
    }
    results = {}
    for name, (directory, filename, status, count) in routes.items():
        receipt = g.load(directory / filename)
        g.require(receipt["status"] == status and receipt["protected_unchanged"], name + " successful/protected")
        if count is not None:
            checks = receipt.get("native_result", receipt)["checks"]
            g.require(len(checks) == count and all(c["passed"] for c in checks), name + " checks")
        if filename == "receipt.json":
            g.require(receipt["exit"] == 0 and not receipt.get("timed_out") and receipt["sources_unchanged_during_run"], name + " completed command")
        results[name] = dict(directory=str(directory), status=status, checks=count, receipt_sha256=g.sha(directory / filename),
                             seconds=receipt.get("seconds"))
    live_result = g.load(ROOT / "actual-final-03/result.json")
    g.require(live_result["companions"] == {Path(k).name:v for k,v in capture["binaries"].items()}, "actual HTTP used all final installed companions")
    g.require(live_result["daemon_sha256"] == broad["binaries_after"]["daemon"]["sha256"]
              and live_result["client_sha256"] == broad["binaries_after"]["client"]["sha256"], "actual UI uses matching final binaries")
    synthetic = g.load(args.synthetic / "result.json")
    g.require(synthetic["binaries"] == {broad["binaries_after"][k]["path"]:broad["binaries_after"][k]["sha256"]
              for k in ("daemon", "client")}, "synthetic UI uses same final binaries")
    frozen = {
        "backend/asic_process.ml":"4074b3c87f7b1f18d6c55b868759eed7faefc785e1b6d43ac6e75e94f7c99045",
        "backend/asic_service.ml":"746b00f47a7decbee363bfe3e9ed87d7eb08ea09264a5fbc2fee6abc06c9d4a0",
        "backend/asic_resources_service.ml":"382dd101adc3cebafdb27775c3e76f3a9795a46db8fd15170b57cc60623cf169",
        "protocol/asic_resources.ml":"8a81631c16da47d0f86e454d69d24eef04913e66460c325a1a11c5decf092d7b"}
    for relative, digest in frozen.items():
        g.require(g.sha(WB / relative) == digest, "r3 source freeze: " + relative)
    current = dep.development(EXAMPLE.parent / "hardcaml_asic", EXAMPLE / ".dev/asic-pt6")
    g.require(dep.checksum(current) == capture["provider"]["snapshot_sha256"], "ASIC source still matches final capture after full suite")
    last = None
    for line in (ROOT / "actual-final-03/native-http.jsonl").open():
        event = json.loads(line)
        if event["path"] == "/api/v1/asic":
            last = event["response"]
    snapshot = dict(codec.parse(last)[1])
    resource_state = dict(snapshot["resources"][0])
    sources = []
    for source in resource_state["sources"]:
        source = dict(source)
        index = next((dict(i) for i in resource_state["indexes"] if dict(i)["source_id"] == source["id"]), None)
        sources.append(dict(source_id=source["id"], kind=source["kind"], path=source["path"], target=source["target"],
                            provider_identity=source["provider_identity"], freshness=source["freshness"],
                            digest=index["digest"] if index else None,
                            inventory_status=index.get("inventory_status", "Unknown") if index else None))
    screens = sorted((ROOT / "actual-final-03").glob("*timing-native*.txt"))
    screen_checks = []
    for token in ('"reported_load": 0.004815', '"reported_load": null', '"analysis_corner": "nom_fast_1p32V_m40C"',
                  "fast_1p32V_m55C.lib", "recorded_external_model_not_read"):
        matches = [p for p in screens if token in p.read_text()]
        g.require(matches, "actual retained timing screen: " + token)
        screen_checks.append(dict(token=token, path=str(matches[0].relative_to(ROOT)), sha256=g.sha(matches[0])))
    files = {str(p.relative_to(ROOT)):g.sha(p) for p in sorted(ROOT.rglob("*"))
             if p.is_file() and not p.is_symlink() and p.resolve() != args.receipt.resolve()}
    synthetic_files = {str(p.relative_to(args.synthetic)):g.sha(p) for p in sorted(args.synthetic.rglob("*")) if p.is_file() and not p.is_symlink()}
    output = dict(status="final_acceptance_passed", contract="PT6-A-contract-r3 + B final", results=results,
                  provider=capture["provider"], companions=capture["binaries"], wb_binaries=broad["binaries_after"],
                  wb_source_inventory_sha256=hashlib.sha256(json.dumps(broad["sources_after"],sort_keys=True).encode()).hexdigest(),
                  frozen_source_hashes=frozen, exact_actual_sources=sources, screen_replay=screen_checks,
                  protected=protected, historical_receipt_files_verified=preserved,
                  all276_and333_unchanged=True, all_current_pointers_unchanged=True, initial_generation_preserved=True,
                  files=files, synthetic_files=synthetic_files, recorder_sha256=g.sha(Path(__file__)),
                  documentation_hashes={str(p):g.sha(p) for p in (ROOT / "README.md", WB / "docs/resource_inspector_acceptance.md")},
                  current_harness_hashes={str(p):g.sha(p) for p in (WB / "scripts/test-resource-inspector.py",
                      WB / "scripts/test-resource-inspector-retained.py", WB / "scripts/fixtures/resource-inspector/provider.py",
                      WB / "scripts/test-resource-inspector-saved-layout.py", WB / "scripts/run-resource-inspector-regressions.py")},
                  limitations=["sampled reported paths, electrical compliance not_assessed; no new EDA qualification",
                               "no new named SRAM execution or preparation-to-historical-bundle linkage",
                               "C covers live same-key retry and guarded navigation; exhaustive poll/receipt interleavings remain B's focused suite",
                               "captured dirty development bytes, not historical producer authentication or clean-source stamp"],
                  coordinator_action="ready for explicit app-provider approval; application and every current pointer remain unchanged")
    g.write_new(args.receipt.resolve(), output)
    print(json.dumps(dict(receipt=str(args.receipt.resolve()), status=output["status"], generation=str(generation), results=results,
                         source_count=len(sources), historical_receipt_files_verified=preserved,
                         protected_unchanged=True, coordinator_action=output["coordinator_action"]), indent=2))


if __name__ == "__main__":
    main()
