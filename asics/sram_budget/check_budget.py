"""Check the emitted RTL and the production resource inspector on fresh bundles."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


MACRO = "RM_IHPSG13_1P_256x16_c2_bm_bist"


def check_bundle(emit, inspect, source, output, budget, expected_macros, bench, env):
    subprocess.run([emit, str(budget), source, output], check=True, env=env)
    index = json.loads(subprocess.check_output(
        [inspect, "resource-inspect", output, "--kind", "bundle", "--json"], env=env
    ))
    rows = {r["id"]: r for r in index["rows"]}
    assert len(index["rows"]) == len(rows) == 3
    assert set(rows) == {"bank0", "bank1", "bank2"}
    assert len({r["contract"] for r in rows.values()}) == 1
    manifest = json.loads((output / "manifest.json").read_text())
    revision = subprocess.check_output(
        ["git", "-C", source, "rev-parse", "HEAD"], env=env, text=True).strip()
    assert manifest["source_revision"] == revision
    assert all(entry["git_status"] == "" for entry in manifest["source_inputs"])
    snapshot = {r["id"]["display"]: r for r in manifest["resource_snapshot"]["resources"]}

    instances = []
    for bank, row in rows.items():
        assert row["requirement"] == "exact_or_flop_fallback", row
        assert row["policy"] == "default", row
        assert row["synthesis"] == row["final"] == "unavailable", row
        if bank in expected_macros:
            assert row["implementation"] == MACRO, row
            assert row["reason"].startswith("exact_mapping"), row
            [instance] = row["instances"]
            instances.append(instance)
        else:
            assert snapshot[bank]["selection"]["reason"] == {
                "kind": "budget_exhausted", "macro": MACRO, "limit": budget
            }, snapshot[bank]
            assert row["implementation"] == "flops", row
            assert row["reason"] == f"budget_exhausted (macro={MACRO}, limit={budget})", row
            assert not row["instances"], row

    rtl = (output / "src/tt_um_sram_budget.v").read_text()
    rtl_instances = re.findall(rf"\b{re.escape(MACRO)}\s+(\w+)\s*\(", rtl)
    assert len(set(instances)) == len(expected_macros)
    assert sorted(rtl_instances) == sorted(instances), (rtl_instances, instances)
    if bench is not None:
        replay = output.parent / f"replay-{budget}"
        subprocess.run(["iverilog", "-g2012", "-s", "bank_replay", "-o", replay,
                        bench, output / "simulation/tt_um_sram_budget.v"], check=True)
        subprocess.run(["vvp", replay], check=True)


if __name__ == "__main__":
    emit, library_meta, root, bench = map(Path, sys.argv[1:])
    # Use the CLI installed in the same prefix as the library Dune actually
    # linked. PATH may still contain an older switch executable in local builds.
    # Don't resolve META: a Dune install tree intentionally uses symlinks.
    inspect = library_meta.absolute().parents[2] / "bin/hardcaml-asic-flow"
    emit, root, bench = (p.resolve() for p in (emit, root, bench))
    sys.path.insert(0, str(root / "scripts"))
    from git_fixture import fixture
    if not all(shutil.which(tool) for tool in ("iverilog", "vvp")):
        print("SKIP behavioral bank-isolation replay: requires iverilog and vvp", file=sys.stderr)
        bench = None
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        env = fixture(root, source, [
            "dune-project", "asic-dependency.json", "asics/sram_budget/dune",
            "asics/sram_budget/sram_budget.ml", "asics/sram_budget/emit.ml",
        ])
        check_bundle(emit, inspect, source, Path(tmp) / "two", 2, {"bank0", "bank1"}, bench, env)
        check_bundle(emit, inspect, source, Path(tmp) / "three", 3, {"bank0", "bank1", "bank2"}, bench, env)
