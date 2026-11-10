"""Consumer acceptance; all Git mutations are confined to disposable fixtures."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def require(condition, context):
    if not condition:
        raise AssertionError(context)


def run(argv, env, ok=True):
    result = subprocess.run([str(x) for x in argv], env=env, text=True, capture_output=True)
    require((result.returncode == 0) if ok else (result.returncode != 0),
            f"status={result.returncode}: {argv}\n{result.stdout}\n{result.stderr}")
    return result


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(output, response, source, inputs):
    require("asic-dependency.json" in inputs, "consumer dependency expectation is an input")
    files = tree(output)
    m = json.loads(files["manifest.json"])
    require(response == {"identity": m["identity"], "output_dir": str(output)}, "identity response")
    inventory = {x["path"]: x["sha256"] for x in m["files"]}
    expected = {"src/config.json", "constraints/top.sdc", "info.yaml",
                "src/tt_um_controlled_fifo.v", "simulation/tt_um_controlled_fifo.v"}
    expected.update("inputs/" + p for p in inputs)
    require(set(inventory) == expected and len(inventory) == len(m["files"]), "exact inventory")
    require(set(files) == expected | {"manifest.json"}, "no uninventoried files")
    for path, sha in inventory.items():
        require(digest(files[path]) == sha, f"file hash {path}")
    require([x["path"] for x in m["source_inputs"]] == sorted(inputs), "declared inputs")
    for x in m["source_inputs"]:
        require(x["copy"] == "inputs/" + x["path"], "copy path")
        data = (source / x["path"]).read_bytes()
        require(data == files[x["copy"]] and digest(data) == x["sha256"], f"source bytes/hash {x}")
    require(m["top_module"] == "tt_um_controlled_fifo" and m["project"] == "controlled_fifo_specimen", "top/project")
    require(m["adapter"] == "LibreLane" and m["operation"] == "Hardening", "operation")
    require(m["target"]["technology"] == "ihp-sg13cmos5l" and m["target"]["tiles"] == "6x4", "target")
    require(m["target"]["harness"] == "(Tiny_tapeout (tiles T6x4))", "harness")
    require(m["resources"] == [] and m["simulation_resources"] == [], "intentionally empty resources")
    require(m["synthesis_sources"] == ["src/tt_um_controlled_fifo.v"] and
            m["simulation_sources"] == ["simulation/tt_um_controlled_fifo.v"], "separate source sets")
    config = json.loads(files["src/config.json"])
    require(config == m["flow_configuration"], "manifest/config agreement")
    for s in m["resolved_settings"]:
        value = "dir::../tt/" + s["value"] if s["key"] == "FP_DEF_TEMPLATE" else s["value"]
        require(config[s["key"]] == value, f"resolved config {s['key']}")
    generated = {"VERILOG_FILES": ["dir::tt_um_controlled_fifo.v"],
                 "PNR_SDC_FILE": "dir::../constraints/top.sdc",
                 "SIGNOFF_SDC_FILE": "dir::../constraints/top.sdc"}
    require(m["generated_settings"] == generated, "generated settings")
    for key, value in generated.items():
        require(config[key] == value, key)
    for key, value in {"DESIGN_NAME": "tt_um_controlled_fifo", "CLOCK_PORT": "clk",
                       "PDK": "ihp-sg13cmos5l", "FP_SIZING": "absolute"}.items():
        require(config[key] == value, key)
    require(math.isclose(config["CLOCK_PERIOD"], 1e9 / 48e6, abs_tol=1e-9), "48MHz")
    sdc = files["constraints/top.sdc"].decode()
    clocks = re.findall(r"^create_clock -name clk -period (\S+) \[get_ports \{clk\}\]$", sdc, re.M)
    require(len(clocks) == 1 and float(clocks[0]) == config["CLOCK_PERIOD"], "SDC clock")
    delays = re.findall(r"^set_(input|output)_delay -(max|min) (\S+) -clock clk \[get_ports \{(\w+)\}\]$", sdc, re.M)
    expected_delays = {(direction, bound, port): maximum if bound == "max" else 0
                       for direction, ports, maximum in [("input", ["ena", "rst_n", "ui_in", "uio_in"], 1),
                                                          ("output", ["uo_out", "uio_out", "uio_oe"], 2)]
                       for port in ports for bound in ["min", "max"]}
    require(len(delays) == 14 and {(d, b, p): float(v) for d, b, v, p in delays} == expected_delays, "SDC delays")
    info = files["info.yaml"].decode()
    for line in ['  top_module: "tt_um_controlled_fifo"', '  tiles: "6x4"',
                 '  clock_hz: 48000000', '    - "tt_um_controlled_fifo.v"']:
        require(line in info.splitlines(), "TT metadata: " + line)
    require(len(re.findall(r"^  (?:ui|uo|uio)\[[0-7]\]:", info, re.M)) == 24, "24 pin descriptions")
    return m


def replay(first, exporter, bench, tmp, env, require_rtl):
    tools = [shutil.which(tool, path=env.get("PATH")) for tool in ("iverilog", "vvp")]
    if not all(tools):
        require(not require_rtl, "strict acceptance requires both iverilog and vvp")
        print("SKIP RTL: requires both iverilog and vvp; use @acceptance-strict to require them")
        return
    trace = run([exporter], env).stdout
    rows = trace.splitlines()
    trace_file = tmp / "trace.txt"
    trace_file.write_text(trace)
    corrupted = rows.copy()
    fields = corrupted[0].split()
    fields[7] = str(int(fields[7]) ^ 1)
    corrupted[0] = " ".join(fields)
    bad = tmp / "bad.txt"
    bad.write_text("\n".join(corrupted) + "\n")
    manifest = json.loads((first / "manifest.json").read_text())
    for mode in ("synthesis", "simulation"):
        exe = tmp / (mode + ".vvp")
        run([tools[0], "-g2012", "-s", "replay", "-o", exe, bench,
             *[first / p for p in manifest[mode + "_sources"]]], env)
        result = run([tools[1], exe, "+trace=" + str(trace_file)], env)
        require(f"PASS RTL edges={len(rows)} " in result.stdout, "all trace rows replayed")
        print(mode + ": " + result.stdout.strip())
        rejected = run([tools[1], exe, "+trace=" + str(bad)], env, ok=False)
        require("trace=0" in rejected.stdout and "expected=" in rejected.stdout and "actual=" in rejected.stdout, "negative oracle context")
        print(mode + ": PASS negative oracle rejected corrupted response at trace=0")


def real_checkout(emitter, exporter, source, bench, work, require_rtl):
    # Read-only repository inspection; preserve actual dirty/untracked input status.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
    work.mkdir(parents=True, exist_ok=False)
    def git(*args):
        return run(["git", "-C", source, *args], env).stdout
    inputs = run([exporter, "--inputs"], env).stdout.splitlines()
    require(inputs and len(inputs) == len(set(inputs)), "unique declared inputs")
    revision = git("rev-parse", "HEAD").strip()
    statuses = {p: git("status", "--porcelain", "--", p).rstrip("\n") for p in inputs}
    checkout_status = git("status", "--porcelain", "--untracked-files=all")
    manifests = []
    for name in ("first", "second"):
        output = work / name
        response = json.loads(run([emitter, "emit", "--json", "--source-root", source, "--output-dir", output], env).stdout)
        m = inspect(output, response, source, inputs)
        require(m["source_revision"] == revision, "actual checkout revision")
        require({x["path"]: x["git_status"] for x in m["source_inputs"]} == statuses,
                "actual input statuses")
        manifests.append(m)
    require(tree(work / "first") == tree(work / "second"), "real-checkout complete tree byte equality")
    require(git("rev-parse", "HEAD").strip() == revision
            and git("status", "--porcelain", "--untracked-files=all") == checkout_status,
            "checkout provenance stable during emission")
    evidence = {"source_root": str(source), "source_revision": revision,
                "checkout_status": checkout_status, "input_statuses": statuses,
                "identity": manifests[0]["identity"], "files": len(tree(work / "first"))}
    (work / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("PASS real-checkout repeat bytes, inventory/hashes/copied inputs and provenance: "
          + json.dumps(evidence))
    replay(work / "first", exporter, bench, work, env, require_rtl)


def main():
    parser = argparse.ArgumentParser()
    for name in ["emitter", "exporter", "source-root", "bench"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--require-rtl", action="store_true")
    parser.add_argument("--real-checkout", action="store_true",
                        help="Emit from the actual source root; only read-only Git inspection")
    parser.add_argument("--work-dir", type=Path,
                        help="Fresh preserved output directory required with --real-checkout")
    parser.add_argument("--baseline-emitter", type=Path,
                        help="Saved old CLI executable (without emit subcommand)")
    parser.add_argument("--baseline-cli", choices=("standalone", "project-v1"), default="standalone",
                        help="Saved baseline CLI syntax (never adds --json)")
    parser.add_argument("--baseline-source-root", type=Path,
                        help="Saved source snapshot supplying only old-only inventory paths")
    parser.add_argument("--baseline-inputs", type=Path,
                        help="Saved baseline --inputs output, one relative path per line")
    args = parser.parse_args()
    if bool(args.baseline_source_root) != bool(args.baseline_inputs):
        parser.error("--baseline-source-root and --baseline-inputs must be supplied together")
    if args.baseline_inputs and not args.baseline_emitter:
        parser.error("baseline source/inventory requires --baseline-emitter")
    emitter, exporter, source_root, bench = [p.resolve() for p in (args.emitter, args.exporter, args.source_root, args.bench)]
    baseline_emitter = args.baseline_emitter.resolve() if args.baseline_emitter else None
    if args.real_checkout:
        if args.work_dir is None or baseline_emitter is not None:
            parser.error("--real-checkout requires --work-dir and excludes --baseline-emitter")
        real_checkout(emitter, exporter, source_root, bench, args.work_dir.resolve(), args.require_rtl)
        return
    if args.work_dir is not None:
        parser.error("--work-dir requires --real-checkout")
    with tempfile.TemporaryDirectory(prefix="fifo-acceptance-") as tmp:
        tmp = Path(tmp)
        # Remove inherited repository/config/identity selectors. No shared config is read
        # or mutated; emitter subprocesses inherit these same identity/config bounds.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(tmp / "gitconfig"),
                   GIT_AUTHOR_NAME="Bundle test", GIT_AUTHOR_EMAIL="bundle@test.invalid",
                   GIT_COMMITTER_NAME="Bundle test", GIT_COMMITTER_EMAIL="bundle@test.invalid",
                   GIT_AUTHOR_DATE="2026-01-01T00:00:00+0000", GIT_COMMITTER_DATE="2026-01-01T00:00:00+0000",
                   GIT_TERMINAL_PROMPT="0")
        (tmp / "gitconfig").write_text("[commit]\n\tgpgSign = false\n[core]\n\thooksPath = " + str(tmp / "hooks") + "\n")
        (tmp / "hooks").mkdir()
        (tmp / "template").mkdir()
        inputs = run([exporter, "--inputs"], env).stdout.splitlines()
        require(inputs and len(inputs) == len(set(inputs)), "unique declared inputs")
        baseline_inputs = args.baseline_inputs.read_text().splitlines() if args.baseline_inputs else inputs
        require(baseline_inputs and len(baseline_inputs) == len(set(baseline_inputs)), "unique baseline inputs")
        union_inputs = sorted(set(inputs) | set(baseline_inputs))
        source = tmp / "source"
        source.mkdir()
        for p in union_inputs:
            require(not Path(p).is_absolute() and not {"..", ".git", "_build"}.intersection(Path(p).parts), "safe input")
            dest = source / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            origin = source_root if p in inputs else args.baseline_source_root
            shutil.copyfile(origin / p, dest)

        def git(*argv):
            return run(["git", "-C", source, "-c", "user.name=Bundle test", "-c", "user.email=bundle@test.invalid",
                        "-c", "commit.gpgSign=false", "-c", "core.hooksPath=" + str(tmp / "hooks"), *argv], env).stdout.strip()

        def emit(name, ok=True, executable=emitter):
            output = tmp / name
            command = [executable] + (["emit", "--json"] if executable == emitter else
                                      (["emit"] if args.baseline_cli == "project-v1" else []))
            result = run([*command, "--source-root", source, "--output-dir", output], env, ok=ok)
            return output, json.loads(result.stdout) if ok else result

        git("init", "--template=" + str(tmp / "template"))
        output, failure = emit("unborn", ok=False)
        require(not output.exists() and "git failed" in failure.stderr, "unborn failure leaves no output")
        protected = tmp / "unborn-existing"
        protected.mkdir()
        (protected / "sentinel").write_bytes(b"preserve existing content\x00\xff")
        protected_bytes = tree(protected)
        _, failure = emit("unborn-existing", ok=False)
        require("git failed" in failure.stderr and tree(protected) == protected_bytes,
                "unborn failure preserves existing bytes")
        git("add", "--", *union_inputs)
        git("commit", "-m", "baseline")
        proof = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%s", "HEAD")
        require(proof == "Bundle test <bundle@test.invalid>\nBundle test <bundle@test.invalid>\nbaseline", "synthetic identities")
        require(git("remote") == "", "fixture has no remotes")
        print("PASS synthetic author=committer=Bundle test <bundle@test.invalid>; message=baseline; no remotes")
        first, response = emit("first")
        m = inspect(first, response, source, inputs)
        require(m["source_revision"] == git("rev-parse", "HEAD"), "fixture revision")
        require(all(x["git_status"] == "" for x in m["source_inputs"]), "clean baseline")
        second, response2 = emit("second")
        inspect(second, response2, source, inputs)
        require(tree(first) == tree(second), "repeat emission byte equality")
        saved = tree(first)
        if baseline_emitter is not None:
            baseline, baseline_response = emit("baseline", executable=baseline_emitter)
            baseline_m = inspect(baseline, baseline_response, source, baseline_inputs)
            require(baseline_m["source_revision"] == m["source_revision"], "same synthetic revision")
            require(all(x["git_status"] == "" for x in baseline_m["source_inputs"]), "clean old inventory")
            baseline_files = tree(baseline)
            artifacts = ["src/tt_um_controlled_fifo.v", "simulation/tt_um_controlled_fifo.v",
                         "src/config.json", "constraints/top.sdc", "info.yaml"]
            for path in artifacts:
                require(baseline_files[path] == saved[path], "baseline artifact byte equality: " + path)
                print(f"PASS baseline artifact {path}: bytes={len(saved[path])} sha256={digest(saved[path])}")
            provenance = {"identity", "files", "source_inputs"}
            require({k: v for k, v in baseline_m.items() if k not in provenance} ==
                    {k: v for k, v in m.items() if k not in provenance}, "baseline nonprovenance manifest facts")
            if set(baseline_inputs) == set(inputs):
                require(baseline_files == saved, "same-inventory baseline whole-bundle equality")
                require(baseline_m == m, "same-inventory baseline manifest equality")
            print(f"PASS baseline artifacts and nonprovenance facts; old inputs={len(baseline_inputs)}, "
                  f"new inputs={len(inputs)}, revision={m['source_revision']}, clean status")
            print(f"PASS baseline emitter sha256={digest(baseline_emitter.read_bytes())}; "
                  f"current emitter sha256={digest(emitter.read_bytes())}")
        _, failure = emit("first", ok=False)
        require("not empty" in failure.stderr and tree(first) == saved, "nonempty refusal preserves bundle")
        for index, (path, comment) in enumerate([("README.md", b"\n<!-- fixture comment -->\n"),
                                                ("ip/controlled_fifo/rtl/controlled_fifo.ml", b"\n(* fixture source comment *)\n")]):
            file = source / path
            file.write_bytes(file.read_bytes() + comment)
            changed, answer = emit(f"changed-{index}")
            changed_m = inspect(changed, answer, source, inputs)
            require(changed_m["identity"] != m["identity"], "tracked edit changes identity")
            require(next(x["git_status"] for x in changed_m["source_inputs"] if x["path"] == path) == " M " + path, "tracked dirty status")
            m = changed_m
        (source / "ip/controlled_fifo/rtl/controlled_fifo.mli").unlink()
        output, failure = emit("missing", ok=False)
        require(not output.exists() and "source input is missing" in failure.stderr, "missing source leaves no output")
        _, failure = emit("first", ok=False)
        require("source input is missing" in failure.stderr and tree(first) == saved, "render failure preserves existing bytes")
        print("PASS bundle: repeat bytes, inventory/hashes, identity, target/config/SDC, 2 tracked edits, 5 failure cases")

        replay(first, exporter, bench, tmp, env, args.require_rtl)


if __name__ == "__main__":
    main()
