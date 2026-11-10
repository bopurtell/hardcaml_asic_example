#!/usr/bin/env python3
"""Independent assertions over public inspection and retained native reports."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from real_tools import EVIDENCE, dump
from record_command import sha


def inspect(provider, directory, output):
    output.mkdir()
    argv = [str(provider), "timing-intent-inspect", str(directory), "--json"]
    result = subprocess.run(argv, capture_output=True, timeout=30)
    (output / "stdout.log").write_bytes(result.stdout)
    (output / "stderr.log").write_bytes(result.stderr)
    dump(output / "command.json", {"argv": argv, "exit_code": result.returncode,
         "provider_sha256": sha(provider), "stdout_sha256": sha(output / "stdout.log"),
         "stderr_sha256": sha(output / "stderr.log")})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generation", type=Path, required=True)
    p.add_argument("--audit", type=Path, default=EVIDENCE / "sta-scalar-01")
    p.add_argument("--synthesis", type=Path, default=EVIDENCE / "synth-scalar-01")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir()
    provider = a.generation.resolve() / "bin/hardcaml-asic-flow"
    audit = json.loads((a.audit / "audit.json").read_text())
    for source in audit["sources"]:
        assert sha(a.audit / source["path"]) == source["sha256"]
    result = inspect(provider, a.audit.resolve(), a.output / "positive")
    assert result.returncode == 1, result.stderr
    view = json.loads(result.stdout)
    assert view["verdict"] == "unavailable"
    assert view["native_coverage"]["status"] == "unavailable"
    assert view["resolved"]["status"] == "producer_reported"
    assert view["applied"]["status"] == "command_completed"
    assert len(view["resolved"]["stages"]) == 5
    assert len(view["applied"]["exceptions"]) == 2
    assert view["downstream"]["coverage"] == view["unconstrained"]["coverage"] == "unavailable"
    assert view["requested"] == json.loads((a.audit / "manifest.json").read_text())["timing_intent"]
    stages = json.loads((a.synthesis / "inventory.json").read_text())["stages"]
    path_results = []
    for mode, native_check in (("min", "library hold time"), ("max", "library setup time")):
        text = (a.audit / f"downstream_{mode}.rpt").read_text()
        assert text.count("Startpoint:") == 3, text
        assert text.count(f"Path Type: {mode}") == 3
        assert text.count(native_check) == 3
        for stage in stages:
            if not stage["index"]:
                continue
            previous = next(s for s in stages if s["chain"] == stage["chain"] and s["index"] == stage["index"] - 1)
            pattern = rf'Startpoint: {re.escape(previous["cell"])} .*?Endpoint: {re.escape(stage["cell"])} .*?([+-]?[0-9.]+)\s+slack \((MET|VIOLATED)\)'
            match = re.search(pattern, text, re.S)
            assert match, (mode, previous, stage)
            path_results.append({"mode": mode, "from": previous["cell"] + "/Q", "to": stage["cell"] + "/D",
                                 "slack_ns": float(match[1]), "native_verdict": match[2]})
        assert "No paths found" in (a.audit / f"capture_{mode}.rpt").read_text()
    negatives = []
    for case in ("missing-resolution", "changed-sdc-hash", "wrong-producer", "truncated-stream",
                 "coherent-wrong-scope", "nonzero-process", "wrong-native-version"):
        fixture = a.output / case
        shutil.copytree(a.audit, fixture)
        metadata = json.loads((fixture / "audit.json").read_text())
        if case == "missing-resolution":
            (fixture / "resolution.log").unlink()
        elif case == "changed-sdc-hash":
            with (fixture / "top.sdc").open("a") as stream:
                stream.write("\n# diagnostic mutation\n")
        elif case == "wrong-producer":
            metadata["producer"]["version"] = "wrong-producer-version"
        elif case == "truncated-stream":
            for name in ("resolution.log", "tool.log"):
                (fixture / name).write_text("".join(line for line in (fixture / name).read_text().splitlines(keepends=True)
                                                   if '"event":"complete"' not in line))
        elif case == "coherent-wrong-scope":
            target = next(s for s in stages if s["id"] == "capture_first")["cell"]
            downstream = next(s for s in stages if s["id"] == "capture_second")["cell"]
            for name in ("resolution.log", "tool.log"):
                text = (fixture / name).read_text()
                assert f'"targets":["{target}/D"]' in text
                (fixture / name).write_text(text.replace(f'"targets":["{target}/D"]', f'"targets":["{downstream}/D"]'))
        elif case == "nonzero-process":
            process = json.loads((fixture / "process-result.json").read_text())
            process["exit_code"] = 1
            dump(fixture / "process-result.json", process)
        elif case == "wrong-native-version":
            (fixture / "producer-version.txt").write_text("unexpected-version\n")
        if case not in ("missing-resolution", "changed-sdc-hash"):
            for source in metadata["sources"]:
                source["sha256"] = sha(fixture / source["path"])
        dump(fixture / "audit.json", metadata)
        result = inspect(provider, fixture.resolve(), a.output / (case + "-inspection"))
        assert result.returncode == 2, (case, result.returncode, result.stdout, result.stderr)
        negatives.append({"case": case, "exit_code": result.returncode,
                          "diagnostic": result.stderr.decode().strip()})
    summary = {"status": "pass_with_coverage_unavailable", "build_identity": audit["build_identity"],
               "audit_id": audit["audit_id"], "provider_generation": str(a.generation.resolve()),
               "public_inspector_exit": 1, "native_coverage": "unavailable",
               "downstream_sampled_paths": path_results, "evidence_negatives": negatives,
               "timing_closure": "not claimed; retain native hold violations",
               "assertions": ["all retained audit source hashes match", "public requested/resolved/applied separation",
                              "five distinct stage observations", "two command-completed exceptions",
                              "three downstream setup and three downstream hold paths remain",
                              "sampled first-stage input capture has no min/max paths after exception",
                              "seven malformed/coherent-negative audits rejected with exit 2"]}
    dump(a.output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
