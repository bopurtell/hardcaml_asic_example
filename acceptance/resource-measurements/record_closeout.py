#!/usr/bin/env python3
"""Verify retained PT5b C receipts/logs and write a NEW closeout; no tests/builds."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_resource_measurements as acceptance
import asic_dependency


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", type=Path)
    parser.add_argument("--final", action="store_true", help="corrected capture, final logs and 15-test suite")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    focused_path = (args.focused or ROOT / "acceptance/resource-measurements" /
                    ("installed-final" if args.final else "installed-02") / "receipt.json").resolve(strict=True)
    focused = acceptance.load(focused_path)
    directory = ROOT / "acceptance/resource-measurements"
    capture = acceptance.load(directory / "accepted-live-01/capture.json")
    current = acceptance.protected_state()
    assertions = []

    def check(name, actual, expected):
        assertions.append(dict(assertion=name, actual=actual, expected=expected, passed=actual == expected))

    check("focused acceptance", focused["public_acceptance"], "passed")
    check("focused tests/failures/errors/skips",
          [focused["tests_run"], focused["failures"], focused["errors"], focused["skipped"]], [15 if args.final else 11, 0, 0, []])
    check("all public exits", all(c["exit"] == c["expected_exit"] for c in focused["commands"]), True)
    check("tested script identity", acceptance.sha(focused_path.parent / "tested-script.py"), focused["script_sha256"])
    check("protected state equals original capture", current, capture["protected_before"])
    check("protected state equals focused completion", current, focused["protected_after"])
    check("augmented bytes equal focused completion", acceptance.inventory(directory / "accepted-live-01/run"), focused["raw_after"])
    if args.final:
        earlier = focused["earlier_acceptance_after"]
        check("earlier acceptance unchanged during final acceptance", earlier, focused["earlier_acceptance_before"])
        check("earlier acceptance unchanged at closeout", {p: acceptance.sha(ROOT/p) for p in earlier}, earlier)
    for field, entry in focused["executable_ids"].items():
        check(field + " executable", acceptance.sha(Path(entry["path"])), entry["sha256"])
    check("isolated selected generation", str((ROOT / ".dev/asic-pt5b/current").resolve()),
          focused["provider_receipt"]["generation"])
    suffix = "final" if args.final else "01"
    suite = (directory / f"suite-{suffix}.stderr").read_text()
    fifo = (directory / f"fifo-{suffix}.stderr").read_text()
    for count in (11, 24, 21):
        check(f"full suite unittest group {count}", f"Ran {count} tests" in suite, True)
    check("full suite unittest groups passed", suite.count("\nOK\n"), 3)
    for marker in ("PASS directed:", "PASS wrapper seed=", "PASS memory Exact Simulation:",
                   "PASS bundle:", "simulation: PASS negative oracle", "synthesis: PASS negative oracle"):
        check(marker, marker in suite, True)
    check("standalone FIFO compatibility", "Ran 5 tests" in fifo and fifo.rstrip().endswith("OK"), True)
    closures = []
    for closure in focused["archive_closures"]:
        archive = focused_path.parent / (closure["label"] + "-archive/reports.tar.gz")
        check(closure["label"] + " archive hash", acceptance.sha(archive), closure["reports_sha256"])
        closures.append(dict(schema=closure["label"], advertised_refs=len(closure["refs"]),
                             all_advertised_bytes_verified=closure["all_advertised_bytes_verified"],
                             reports_sha256=closure["reports_sha256"]))
    # Read-only freshness observation using the same inventory algorithm as
    # capture. This neither refreshes the provider nor changes the ASIC checkout.
    source = Path(focused["provider_receipt"]["source"])
    source_now = asic_dependency.checksum(asic_dependency.development(source, ROOT / ".dev/asic-pt5b"))
    receipt = dict(scope="PT.5b C retained installed acceptance closeout; no new EDA",
        command=sys.orig_argv, provider_receipt=focused["provider_receipt"],
        executable_ids={**focused["executable_ids"], **{
            label: dict(path=str(ROOT / path), sha256=acceptance.sha(ROOT / path)) for label, path in
            (("fifo", "_build_pt5b/default/bin/project.exe"), ("memory", "_build_pt5b/default/memory/memory_cli.exe"))}},
        assertions=assertions, archive_closures=closures,
        focused_receipt=dict(path=str(focused_path.relative_to(ROOT)), sha256=acceptance.sha(focused_path)),
        raw_capture=dict(files=capture["file_count"], bytes=capture["total_bytes"],
                         receipt_sha256=acceptance.sha(directory / "accepted-live-01/capture.json")),
        retained_logs={str(p.relative_to(ROOT)): acceptance.sha(p) for p in sorted(directory.iterdir())
                       if p.is_file() and p.suffix in (".stdout", ".stderr")},
        executed_commands=[
            dict(command="opam exec --switch=5.2.0+ox -- python3 -B scripts/asic_dependency.py --store .dev/asic-pt5b refresh --source /home/wayne/devel/jane/hardcaml_asic --mode development --jobs 6", exit=0, logs="provider-"+suffix),
            dict(command="source .dev/asic-pt5b/current/activate.sh && opam exec --switch=5.2.0+ox -- dune build --build-dir _build_pt5b -j6 @all acceptance/resource-realization/installed_api.exe", exit=0, logs="build-"+suffix),
            dict(command='source .dev/asic-pt5b/current/activate.sh && opam exec --switch=5.2.0+ox -- env HARDCAML_ASIC_TEST_PROVIDER="$HARDCAML_ASIC_GENERATION/bin/hardcaml-asic-flow" dune runtest --build-dir _build_pt5b -j6 --force .', exit=0, logs="suite-"+suffix),
            dict(command='source .dev/asic-pt5b/current/activate.sh && opam exec --switch=5.2.0+ox -- python3 -B scripts/test_flow_emit.py "$PWD/_build_pt5b/default/bin/project.exe" "$PWD"', exit=0, logs="fifo-"+suffix)],
        command_exit_scope="successful exits observed during C session; this recorder checks existing logs/bytes, does not rerun commands",
        source_freshness=dict(current_snapshot_sha256=source_now,
            matches_tested_capture=source_now == focused["provider_receipt"]["snapshot_sha256"],
            scope="moving checkout observation only; tested identity remains the frozen capture"),
        failed_attempts=[dict(path="installed-01/receipt.json", tests=10, failures=5, errors=1,
            reason="harness expected CLI 0 for provenance contradictions, schema1 report rendering instead of fresh schema2, and retained MET on negative-slack fixture")],
        limitations=focused["limitations"],
        passed=all(a["passed"] for a in assertions))
    acceptance.new_json(args.receipt.resolve(), receipt)
    print(json.dumps(dict(passed=receipt["passed"], focused_tests=focused["tests_run"],
                          archive_closures=closures, source_freshness=receipt["source_freshness"]), indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
