"""Cheap actual CLI checks: no Git, emission, or EDA needed."""
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    executable = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="project-cli-") as directory:
        root = Path(directory)
        output = root / "must-not-exist"
        env = dict(os.environ, PATH="", GIT_DIR=str(root / "no-git"))

        def check(args, status):
            result = subprocess.run([str(executable), *args], cwd=root, env=env,
                                    capture_output=True, text=True)
            assert result.returncode == status, (args, result)
            assert list(root.iterdir()) == [], (args, "unexpected filesystem output")
            return result

        description = check(["describe"], 0).stdout
        for fact in ("controlled_fifo", "tt_um_controlled_fifo", "clk",
                     "timing", "pinout", "policy", "source_inputs"):
            assert fact in description, (fact, description)
        assert json.loads(check(["describe", "--json", "--verbose"], 0).stdout)["project_name"] == "controlled_fifo"
        for args, mode in ((["resources", "--json"], "implementation"),
                           (["resources", "--simulation", "--json"], "simulation")):
            inventory = json.loads(check(args, 0).stdout)
            assert inventory['mode'] == mode and inventory['resources'] == []
        catalog = json.loads(check(["flow", "list", "--json"], 0).stdout)
        assert catalog["contract"] == "hardcaml-asic.flow-list" and catalog["schema_version"] == 1
        entry = json.loads(check(["flow", "describe", "--flow", "standard", "--json"], 0).stdout)
        assert entry["contract"] == "hardcaml-asic.flow-describe" and entry["schema_version"] == 1
        for args in (["flow"], ["flow", "unknown"], ["flow", "describe"],
                     ["flow", "describe", "--flow", "missing"],
                     ["flow", "plan"], ["flow", "emit"],
                     ["flow", "plan", "--endpoint", "synthesis", "--profile", "balanced"],
                     ["flow", "run", "--endpoint", "synthesis"],
                     ["flow", "run", "--endpoint", "synthesis", "--bundle", "anything"],
                     ["flow", "run", "--endpoint", "synthesis", "--checkpoint", "anything"]):
            check(args, 2)
        for args in ([], ["unknown"], ["describe", "extra"],
                      ["prepare", "--simulation"], ["preview", "--results-root", str(output)],
                     ["run"], ["run", "--stage", "bad"],
                     ["describe", "--output-dir", str(output)],
                     ["emit", "--source-root", str(root), "--output-dir", str(output), "--bogus"],
                     ["--source-root", str(root), "--output-dir", str(output)]):
            result = check(args, 2)
            assert "Usage: chip" in result.stderr and "Bundle emission failed" not in result.stderr
        for args in (["--help"], ["prepare", "--help"], ["preview", "--help"], ["resources", "--help"],
                     ["emit", "--help"], ["preflight", "--help"], ["run", "--help"],
                     *(["flow", command, "--help"] for command in ("list", "describe", "plan", "emit", "run"))):
            assert "Usage: chip" in check(args, 0).stdout
    print("PASS CLI: declaration-only description without Git/PATH; help and invalid commands; no output created")


if __name__ == "__main__":
    main()
