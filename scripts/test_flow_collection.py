"""Build the real FIFO in a fresh source-only fixture. No Git setup, Silver or EDA."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    source = Path(__file__).resolve().parents[1]
    # Bundle provenance requires a HEAD. Borrow the enclosing checkout for
    # read-only status queries; never initialize or change a repository.
    scratch = source / "_build"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fifo-flow-collection-", dir=scratch) as tmp:
        root = Path(tmp)
        for name in ("asics", "ip"):
            shutil.copytree(source / name, root / name)
        for name in ("dune-project", "asic-dependency.json", "README.md"):
            shutil.copy(source / name, root)
        owner = "asics/fifo_demo"
        flows = root / owner / "flows"
        chip = f"./{owner}/cli/chip.exe"

        def command(*argv, error=None):
            if argv[0] == "dune":
                argv = (*argv[:2], "--root", ".", *argv[2:])
            proc = subprocess.run(argv, cwd=root, capture_output=True, text=True,
                                  env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
            if error is not None:
                assert proc.returncode and error in proc.stderr, proc
            else:
                assert not proc.returncode, proc.stderr
                return proc.stdout

        def listing(*selection):
            return json.loads(command("dune", "exec", chip, "--", "flow", "list", "--json", *selection))

        def entries(declaration):
            return {e["methodology"]["id"]: e for e in declaration["entries"]}

        def plan(*selection, endpoint="synthesis"):
            return json.loads(command("dune", "exec", chip, "--", "flow", "plan",
                                      "--endpoint", endpoint, "--source-root", str(root),
                                      "--json", *selection))

        def render(op, error=None, **fields):
            result = command("hardcaml-asic-starter", "render-" + op, json.dumps({
                "owner": owner, "registered": True, "catalog": listing(), **fields
            }), error=error)
            return json.loads(result) if result else None

        def apply(preview):
            f, = preview["files"]
            dest = root / f["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("x") as out:
                out.write(f["contents"])
            return dest

        initial = listing()["declaration"]
        fifo = ("--chip", "fifo_demo", "--variant", "default")
        assert initial == listing(*fifo)["declaration"]
        assert initial["default"] == {"flow": "standard", "profile": "balanced"}
        other_flows = {id: entry for id, entry in entries(initial).items() if id != "standard"}
        memory = ("dune", "exec", "./asics/program_memory/cli/chip.exe", "--", "flow", "list")
        memory_catalog = json.loads(command(*memory, "--json"))
        assert json.loads(command(*memory, "--chip", "program_memory", "--json")) == memory_catalog
        command(*memory, "--chip", "fifo_demo", "--json", error="Usage:")
        memory_target = ("--chip", "program_memory", "--variant", "default")
        assert listing(*memory_target) == memory_catalog
        assert memory_catalog["declaration"]["default"] == {
            "flow": "stock256-r0", "profile": "qualification"}
        memory_plan = plan(*memory_target, endpoint="timing")
        opts = dict(flow_id="standard", source_profile="balanced", profile_id="timing_trial", edits={})
        manual = render("profile", **opts, registered=False)
        assert not manual["files"] and "Flow.Profile.create" in manual["snippet"]
        render("profile", **{**opts, "profile_id": "balanced"}, error="Duplicate profile ID")
        render("profile", **{**opts, "edits": {"SYNTH_ABC_BUFFERING": "false"}}, error="boolean")
        render("profile", **{**opts, "edits": {"UNSUPPORTED": True}}, error="Unsupported parameter")
        copy = apply(render("profile", **opts))
        assert copy == flows / "standard/profiles/timing_trial.ml"
        render("profile", **opts, error="Duplicate profile ID")
        edited = render("profile", **{**opts, "profile_id": "edited", "edits": {
            "SYNTH_STRATEGY": "DELAY 3", "SYNTH_ABC_BUFFERING": None}})
        assert "Delay_3" in edited["files"][0]["contents"]
        assert "synth_abc_buffering" not in edited["files"][0]["contents"]
        helper = flows / "standard_profiles.ml"
        helper.write_text(helper.read_text().replace("Area_0", "Area_2"))
        e = entries(listing()["declaration"])["standard"]
        assignments = {p["id"]: {a["key"]: a["value"] for a in p["assignments"]} for p in e["profiles"]}
        assert e["default_profile"] == "balanced"
        assert assignments["balanced"]["SYNTH_STRATEGY"] == "AREA 2"
        assert assignments["timing_trial"] == {"SYNTH_STRATEGY": "AREA 0", "SYNTH_ABC_BUFFERING": False}
        assert assignments["synth_delay"]["SYNTH_STRATEGY"] == "DELAY 1"
        new = apply(render("flow", flow_id="quick", profile_id="initial", endpoints=["synthesis"],
                           recipe="librelane_classic_v1"))
        assert new == flows / "flow_quick.ml"
        (flows / "ordinary.ml").write_text("let helper = 1\n")
        catalog = listing()["declaration"]
        assert catalog["default"] == initial["default"]
        added = entries(catalog)
        assert set(added) == set(entries(initial)) | {"quick"}
        assert all(added[id] == entry for id, entry in other_flows.items())
        assert added["quick"]["default_profile"] == "initial"
        assert listing(*memory_target) == memory_catalog
        assert plan(*memory_target, endpoint="timing") == memory_plan
        command("dune", "exec", chip, "--", "flow", "describe", *memory_target,
                "--flow", "quick", "--json", error="Unknown flow ID")
        paths = command("dune", "exec", f"./{owner}/verif/bundle/export_trace.exe", "--", "--inputs").splitlines()
        assert {str(p.relative_to(root)) for p in [copy, new, helper]} <= set(paths)
        # Exercise real plan + run dispatch without starting physical tools.
        recorder = root / "record-attempt"
        recorder.write_text("""#!/usr/bin/env python3
import json, sys
from pathlib import Path
if sys.argv[1] == "--version":
    print(json.dumps({"cli_contract":{"version":4,"capabilities":{"namedflow1":True}}}))
else:
    assert sys.argv[1] == "stages"
    home = Path(sys.argv[sys.argv.index("--workspace")+1])
    home.mkdir()
    print(json.dumps({"attempt":str(home)}))
""")
        recorder.chmod(0o755)
        before = {p: (root / p).read_bytes() for p in paths}
        for profile, strategy in [("timing_trial", "AREA 0"), ("balanced", "AREA 2"),
                                  ("synth_delay", "DELAY 1")]:
            args = ("--flow", "standard", "--profile", profile, "--endpoint", "synthesis",
                    "--source-root", str(root), "--json")
            prepared = plan(*fifo, "--flow", "standard", "--profile", profile)
            assert json.loads(prepared["configuration_bytes"])["SYNTH_STRATEGY"] == strategy
            if profile == "balanced":
                assert plan() == prepared
            receipt = json.loads(command("dune", "exec", chip, "--", "flow", "run", *args,
                "--provider", str(recorder), "--expected-plan-identity", prepared["plan_identity"]))
            assert Path(receipt["attempt"]).is_dir()
        assert all((root / p).read_bytes() == data for p, data in before.items())
        duplicate = flows / "flow_other.ml"
        duplicate.write_bytes(new.read_bytes())
        command("dune", "exec", chip, "--", "flow", "list", "--json", error="Duplicate flow ID quick")
        duplicate.unlink()
        new.unlink()
        standard = flows / "flow_standard.ml"
        opted_in = standard.read_text()
        standard.write_text(opted_in.replace("(* hardcaml-asic profile directory v1 *)\n", ""))
        catalog = listing()["declaration"]
        assert catalog["default"] == initial["default"]
        assert set(entries(catalog)) == set(entries(initial))
        e = entries(catalog)["standard"]
        assert [p["id"] for p in e["profiles"]] == ["balanced", "synth_delay"]
        copy.unlink()
        standard.write_text(opted_in)
        e = entries(listing()["declaration"])["standard"]
        assert [p["id"] for p in e["profiles"]] == ["balanced", "synth_delay"]
        print("PASS FIFO flow/profile additions and removals, per-chip isolation and defaults, "
              "copy isolation, collisions, source inventory")


if __name__ == "__main__":
    main()
