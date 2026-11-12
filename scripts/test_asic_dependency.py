"""PDK-free setup contract tests. Only temporary fixtures create Git commits."""
import fcntl
import json
import os
import shlex
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import asic_dependency as dep

PROJECT_API = """type t
val create : name:string -> ?source_inputs:string list -> policy:Resource_policy.t -> unit -> t Or_error.t
val source_inputs : t -> string list
val describe : t -> Sexp.t
val emit_bundle : ?inputs:Target.Inputs.t -> ?methodology:Flow.Catalog.resolved -> ?include_simulation:bool -> t -> source_root:string -> output_dir:string -> Bundle.t Or_error.t
val emit_bundle_to_store : ?inputs:Target.Inputs.t -> ?methodology:Flow.Catalog.resolved -> ?include_simulation:bool -> t -> source_root:string -> store_dir:string -> (Bundle.t * Bundle.Publication.t) Or_error.t
"""
BUNDLE_API = """val render : ?simulation_project:Elaborated_project.t -> unit
module Publication : sig type t = private { directory : string; reused : bool } end
val publish : t -> store_dir:string -> Publication.t Or_error.t
"""
GROUPED_PROJECT_API = (PROJECT_API.replace("Target.Inputs.t", "Platform.Target.Inputs.t")
                       .replace("Flow.Catalog.resolved", "Hardcaml_asic_flow_domain.Catalog.resolved")
                       .replace("Bundle.", "Elaboration.Bundle."))
CATALOG_APIS = {
    "lib/flow/catalog.mli": "val create : unit val resolve : unit val declaration : unit",
    "lib/flow/profile.mli": "val create : unit val assignments : unit",
    "lib/flow/methodology.mli": "type t = Librelane_classic_v1 val create : unit",
    "lib/flow/selection.mli": "val create : unit val default : unit",
    "lib/flow/parameter.mli": "val of_scalar : unit val check_assignments : unit",
    "lib/flow_spec.mli": "val list_to_yojson : unit val describe_to_yojson : unit",
    "lib/methodology_plan.mli": "module Prepared : sig end val prepare : ?catalog_inputs:string list -> ?expected_plan_identity:string -> unit val plan_identity : unit val to_string : unit",
}


class CaptureBuildRootsTests(unittest.TestCase):
    def test_private_dune_roots_do_not_enter_captured_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'execution').mkdir()
            (root / 'execution/source.ml').write_text('authored')
            names = ['execution/source.ml']
            for name in ('_build_pt8_workbench', '_build_pt8_workloads'):
                (root / name).mkdir()
                link = root / name / 'broken-install-link'
                link.symlink_to('missing')
                names.append(str(link.relative_to(root)))
            with patch.object(dep, 'git', return_value=('\0'.join(names) + '\0').encode()):
                entries = dep.development(root, root / 'store')
            self.assertEqual(set(entries), {'execution/source.ml'})
            self.assertTrue(all((root / n / 'broken-install-link').is_symlink()
                                for n in ('_build_pt8_workbench', '_build_pt8_workloads')))


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="asic setup's ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "provider's source"
        self.source.mkdir()
        self.store = self.root / "private store's prefix"
        self.calls = []
        files = {
            **CATALOG_APIS,
            "dune-project": "(lang dune 3.17)\n(name hardcaml_asic)\n",
            "lib/elaborated_project.mli": "type t\n",
            "lib/resolved_flow.mli": "type t = private { elaborated_project : Elaborated_project.t }\n",
            "lib/bundle.mli": BUNDLE_API,
            "lib/project.mli": PROJECT_API,
            "bin/dune": "(executable (name flow_cli) (public_name hardcaml-asic-flow) (package hardcaml_asic))\n",
            "toolchain.lock": "fixture data\n",
            ".gitignore": "_build/\n.toolchain/\nignored\n",
        }
        for name, text in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        data = self.source / "flow/hardcaml_asic_flow/data"
        data.mkdir(parents=True)
        (data / "toolchain.lock").symlink_to("../../../toolchain.lock")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME="Bundle test", GIT_AUTHOR_EMAIL="bundle@test.invalid",
                   GIT_COMMITTER_NAME="Bundle test", GIT_COMMITTER_EMAIL="bundle@test.invalid",
                   GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
        def fixture_git(*args):
            return dep.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                            "-c", "init.templateDir=", "-C", str(self.source), *args], env=env)
        self.fixture_git = fixture_git
        fixture_git("init")
        fixture_git("add", ".")
        fixture_git("commit", "-m", "baseline")
        self.assertEqual(fixture_git("remote"), b"")
        self.assertEqual(fixture_git("show", "-s", "--format=%an <%ae>|%cn <%ce>"),
                         b"Bundle test <bundle@test.invalid>|Bundle test <bundle@test.invalid>\n")
        self.record = dict(schema=1, package="hardcaml_asic", repository=dep.REPOSITORY,
                           revision=fixture_git("rev-parse", "HEAD").decode().strip())
        self.failure = None
        self.mutate = False
        self.contract = 4
        self.capability = True

    def runner(self, argv, *, cwd=None, env=None):
        self.calls.append(argv)
        stage = argv[1] if argv[0] in {"dune", "ocamlfind"} else "cli"
        if stage == self.failure:
            raise dep.Error("injected " + stage + " failure")
        if stage == "build" and "probe.exe" in argv:
            self.assertIn("hardcaml_asic", (Path(cwd) / "dune").read_text())
            self.assertEqual((Path(cwd) / "probe.ml").read_text(), dep.PROBE)
            if self.failure == "dune-probe":
                raise dep.Error("injected Dune link failure")
        elif stage == "build":
            self.snapshot = Path(cwd)
            self.captured = {str(p.relative_to(cwd)): p.read_bytes()
                             for p in Path(cwd).rglob("*") if p.is_file()}
            self.assertTrue((Path(cwd) / "flow/hardcaml_asic_flow/data/toolchain.lock").is_symlink())
            self.assertFalse((Path(cwd) / ".git").exists())
            if self.mutate:
                (self.source / "toolchain.lock").write_text("changed after capture")
                self.assertEqual((Path(cwd) / "toolchain.lock").read_bytes(), b"fixture data\n")
        elif stage == "install":
            generation = Path(argv[argv.index("--prefix") + 1])
            package = generation / "lib/hardcaml_asic"
            for name in ("META", "dune-package",
                         "flow/hardcaml_asic_flow/__init__.py", "flow/hardcaml_asic_flow/probe.py",
                         "flow/hardcaml_asic_flow/backend_protocol.py",
                         "flow/hardcaml_asic_flow/librelane_bridge.py",
                         "flow/hardcaml_asic_flow/stage_metadata_probe.py",
                         "flow/hardcaml_asic_flow/paths.py",
                         "flow/hardcaml_asic_flow/managed_python.py",
                         "flow/hardcaml_asic_flow/runtime_contract.py",
                         "flow/hardcaml_asic_flow/runtime_observation.py",
                         "flow/hardcaml_asic_flow/data/managed-python.json",
                         "flow/hardcaml_asic_flow/data/toolchain.lock",
                         "flow/hardcaml_asic_flow/data/toolchain.sh", "flow/hardcaml_asic_flow/data/version.txt"):
                target = package / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("stub installed bytes")
            # Mirror the real install: flat lib/flow/ became flow_domain/; grouped keeps lib/ subdirectories.
            grouped = (self.snapshot / "flow_domain").is_dir()
            installed = dep.INSTALL_LAYOUTS["grouped" if grouped else "flat"]
            for source in (self.snapshot / "lib").rglob("*.mli"):
                relative = str(source.relative_to(self.snapshot / "lib"))
                target = package / (relative if grouped else relative.replace('flow/', 'flow_domain/', 1))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            for source in (self.snapshot / "flow_domain").rglob("*.mli"):
                target = package / "flow_domain" / source.relative_to(self.snapshot / "flow_domain")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            if self.failure == "old-api":
                (package / installed["resolved"]).write_text("old API")
            if self.failure == "old-project-api":
                (package / "project.mli").write_text("type t")
            if self.failure == "old-bundle-api":
                (package / installed["bundle"]).write_text("?simulation_project:")
            if self.failure == "mixed-install":
                (package / "elaborated_project.mli").write_text("type t\n")
            if self.failure == "capture-metadata":
                (package / "dune-package").write_text(str(self.snapshot / "_build/install/default/lib"))
            if self.failure == "external-link":
                (package / "external").symlink_to(self.source / "toolchain.lock")
            (generation / "bin").mkdir()
            for name in ("hardcaml-asic-flow", *("hardcaml-asic-experimental-" + suffix for suffix in (
                    "execute", "archive", "finalization", "finalization-inspect", "postcheck",
                    "report", "collect", "run", "preflight", "observation-read", "stages",
                    "plan-inspect", "segment-execute", "checkpoint-inspect"))):
                executable = generation / "bin" / name
                executable.write_bytes(b"\x7fELFfixture native bytes")
                executable.chmod(0o755)
            if self.failure == "missing-native-helper":
                (generation / "bin/hardcaml-asic-experimental-stages").unlink()
            if self.failure == "shell-cli":
                (generation / "bin/hardcaml-asic-flow").write_text("#!/bin/sh\n")
            if self.failure == "missing-data":
                (package / "flow/hardcaml_asic_flow/data/toolchain.lock").unlink()
            if self.failure == "missing-probe":
                (package / "flow/hardcaml_asic_flow/probe.py").unlink()
            if self.failure == "missing-managed-module":
                (package / "flow/hardcaml_asic_flow/managed_python.py").unlink()
            if self.failure == "missing-managed-data":
                (package / "flow/hardcaml_asic_flow/data/managed-python.json").unlink()
            for module in ("__init__", "backend_protocol", "librelane_bridge", "stage_metadata_probe", "paths", "runtime_contract", "runtime_observation"):
                if self.failure == "missing-" + module:
                    (package / f"flow/hardcaml_asic_flow/{module}.py").unlink()
        elif stage == "query":
            if self.failure == "wrong-package":
                return b"/shared/opam/lib/hardcaml_asic\n"
            return (env["OCAMLPATH"].split(":")[0] + "/hardcaml_asic\n").encode()
        elif stage == "ocamlc":
            self.assertIn("Resolved_flow.t", Path(argv[-1]).read_text())
            self.assertIn("?simulation_project:None", Path(argv[-1]).read_text())
            self.assertEqual(Path(argv[-1]).read_text(), dep.PROBE)
            for token in ("Project.create ?source_inputs:", "Project.source_inputs", "Project.describe",
                          "?inputs:Target.Inputs.t", "?include_simulation:bool", "Project.emit_bundle",
                          "Project.emit_bundle_to_store", "Bundle.publish", "p.directory", "p.reused"):
                self.assertIn(token, dep.PROBE)
        if "--version" in argv:
            return json.dumps({"cli_contract": {"version": 1 if self.failure == "old-cli" else self.contract,
                                               "capabilities": {"namedflow1": self.capability}}}).encode()
        return b""

    def refresh(self, mode="recorded"):
        return dep.refresh(self.source, mode, self.store, self.record, self.runner)

    def regroup(self):
        # Move the fixture to the ad290d8 grouped layout and record that commit.
        flat, grouped = dep.SOURCE_LAYOUTS["flat"], dep.SOURCE_LAYOUTS["grouped"]
        for role in flat:
            if flat[role] != grouped[role]:
                target = self.source / grouped[role]
                target.parent.mkdir(parents=True, exist_ok=True)
                (self.source / flat[role]).rename(target)
        (self.source / "lib/project.mli").write_text(GROUPED_PROJECT_API)
        self.fixture_git("add", "-A", ".")
        self.fixture_git("commit", "-m", "grouped layout fixture")
        self.record["revision"] = self.fixture_git("rev-parse", "HEAD").decode().strip()

    def test_grouped_layout_validates_source_and_install(self):
        self.regroup()
        self.assertFalse((self.source / "lib/elaborated_project.mli").exists())
        dep.api_check(dep.development(self.source, self.store))
        report = json.loads(dep.run(["python3", str(Path(dep.__file__)), "validate-source",
                                     "--source", str(self.source), "--revision", self.record["revision"]]))
        self.assertIs(report["renamed_api_present"], True)
        for mode in ("recorded", "development"):
            with self.subTest(mode=mode):
                receipt = self.refresh(mode)
                package = Path(receipt["generation"]) / "lib/hardcaml_asic"
                self.assertTrue((package / "elaboration/resolved.mli").is_file())
                self.assertTrue((package / "flow/spec.mli").is_file())
                self.assertFalse((package / "elaborated_project.mli").exists())

    def test_grouped_layout_failures_and_mixed_layouts_refused(self):
        self.regroup()
        first = self.refresh()
        entries = dep.development(self.source, self.store)
        grouped = dep.SOURCE_LAYOUTS["grouped"]
        with self.assertRaisesRegex(dep.Error, "catalog/plan API: lib/flow/spec.mli"):
            dep.api_check({k: v for k, v in entries.items() if k != "lib/flow/spec.mli"})
        with self.assertRaisesRegex(dep.Error, "renamed public API.*lib/elaboration/resolved.mli"):
            dep.api_check({k: v for k, v in entries.items() if k != grouped["resolved"]})
        # A flat-layout spec does not satisfy a grouped provider.
        moved = {("lib/flow_spec.mli" if k == "lib/flow/spec.mli" else k): v for k, v in entries.items()}
        with self.assertRaisesRegex(dep.Error, "catalog/plan API"):
            dep.api_check(moved)
        with self.assertRaisesRegex(dep.Error, "mixed provider layouts"):
            dep.api_check(dict(entries, **{"lib/elaborated_project.mli": entries[grouped["elaborated_project"]]}))
        # Flat Project spellings do not satisfy a grouped provider, and vice versa.
        with self.assertRaisesRegex(dep.Error, "Project.emit_bundle"):
            dep.api_check(dict(entries, **{"lib/project.mli": ("100644", PROJECT_API.encode())}))
        with self.assertRaisesRegex(dep.Error, "Project.emit_bundle"):
            dep.project_api_check(GROUPED_PROJECT_API.encode())
        for stage, error in (("old-api", "installed public API incompatible: elaboration/resolved.mli"),
                             ("old-bundle-api", "Bundle publication API"), ("old-project-api", "Project"),
                             ("mixed-install", "mixed provider layouts")):
            with self.subTest(stage=stage):
                self.failure = stage
                with self.assertRaisesRegex(dep.Error, error):
                    self.refresh()
                self.assertEqual((self.store / "current").resolve(), Path(first["generation"]))

    def test_source_cli_owner_must_be_an_actual_native_stanza(self):
        entries = dep.development(self.source, self.store)
        for data in (b"; (executable (name flow_cli) (public_name hardcaml-asic-flow))\n",
                     b"(executable (name shell_adapter) (public_name hardcaml-asic-flow))\n"):
            with self.subTest(data=data), self.assertRaises(dep.Error):
                dep.api_check(dict(entries, **{"bin/dune": ("100644", data)}))

    def test_recorded_ignores_dirty_and_untracked_development_includes_them(self):
        (self.source / "toolchain.lock").write_text("dirty")
        (self.source / "new.ml").write_text("untracked")
        (self.source / "ignored").write_text("excluded")
        for directory in ("_build", ".toolchain"):
            (self.source / directory).mkdir()
            (self.source / directory / "secret").write_text("excluded")
        recorded = self.refresh()
        self.assertEqual(self.captured["toolchain.lock"], b"fixture data\n")
        self.assertNotIn("new.ml", self.captured)
        self.assertFalse(recorded["differs_from_recorded_snapshot"])
        dev = self.refresh("development")
        self.assertEqual(self.captured["toolchain.lock"], b"dirty")
        self.assertEqual(self.captured["new.ml"], b"untracked")
        self.assertNotIn("ignored", self.captured)
        self.assertFalse(any("secret" in p for p in self.captured))
        self.assertTrue(dev["differs_from_recorded_snapshot"])
        self.assertNotEqual(dev["snapshot_sha256"], recorded["snapshot_sha256"])
        self.assertTrue(Path(recorded["generation"]).is_dir())
        self.assertFalse((self.source / "_build/default").exists())
        self.assertEqual({c[0] for c in self.calls if "hardcaml-asic-flow" not in c[0]}, {"dune", "ocamlfind"})

    def test_failures_preserve_publication(self):
        first = self.refresh()
        for stage in ("build", "install", "query", "ocamlc", "dune-probe", "capture-metadata", "cli", "missing-data", "missing-probe", "missing-managed-module", "missing-managed-data", "missing-runtime_contract", "missing-runtime_observation", "missing-__init__", "missing-backend_protocol", "missing-librelane_bridge", "missing-stage_metadata_probe", "missing-paths", "missing-native-helper", "shell-cli", "old-bundle-api", "old-cli", "wrong-package", "old-api", "old-project-api", "external-link"):
            with self.subTest(stage=stage):
                self.failure = stage
                with self.assertRaises(dep.Error):
                    self.refresh()
                self.assertEqual((self.store / "current").resolve(), Path(first["generation"]))
                self.assertEqual(json.loads((self.store / "current/receipt.json").read_text()), first)

    def test_release_build_uses_capture_without_duplicate_root(self):
        self.refresh()
        build = next(c for c in self.calls if c[:2] == ["dune", "build"])
        self.assertIn("-p", build)
        self.assertNotIn("--root", build)  # -p already supplies --root .
        self.assertEqual(build[build.index("--build-dir") + 1], "_build")
        install = next(c for c in self.calls if c[:2] == ["dune", "install"])
        self.assertEqual(install[install.index("--build-dir") + 1], "_build")
        self.assertTrue(any("probe.exe" in c for c in self.calls))
        for command in self.calls:
            if command[0] == "dune":
                self.assertEqual(command[command.index("-j") + 1], "20")
        self.assertTrue(self.snapshot.is_relative_to(self.store))

    def test_supported_cli_contracts_only_and_refusal_preserves_selection(self):
        selected = self.refresh()
        for version in (1, 2, 3, 5, None, "4", True, 4.0):
            with self.subTest(version=version):
                self.contract = version
                with self.assertRaisesRegex(dep.Error, "CLI4.*namedflow1"):
                    self.refresh()
                self.assertEqual((self.store / "current").resolve(), Path(selected["generation"]))
                self.assertEqual(json.loads((self.store / "current/receipt.json").read_text()), selected)
        self.contract = 4
        for value in (False, None, 1, "true", {}, []):
            self.capability = value
            with self.subTest(capability=value), self.assertRaisesRegex(dep.Error, "namedflow1"):
                self.refresh()
            self.assertEqual((self.store / "current").resolve(), Path(selected["generation"]))

    def test_catalog_surface_required_before_build(self):
        entries = dep.development(self.source, self.store)
        dep.api_check(entries)
        for name in CATALOG_APIS:
            with self.subTest(name=name), self.assertRaisesRegex(dep.Error, "catalog/plan API"):
                dep.api_check({k: v for k, v in entries.items() if k != name})
        for metadata in ({}, [], {"cli_contract": []}, {"cli_contract": {"version": 4}},
                         {"cli_contract": {"version": 4, "capabilities": []}}):
            with self.subTest(metadata=metadata), self.assertRaises(dep.Error):
                dep.namedflow_check(metadata)
        for data in ('not JSON', '{"cli_contract":{},"cli_contract":{}}',
                     '{"cli_contract":{"version":4,"capabilities":{"namedflow1":true,"namedflow1":true}}}'):
            with self.subTest(data=data), self.assertRaises(dep.Error):
                dep.provider_metadata(data)

    def test_missing_revision_api_and_wrong_source(self):
        first = self.refresh()
        self.record = dict(self.record, revision="0" * 40)
        with self.assertRaises(dep.Error):
            self.refresh()
        self.record = first["record"].copy()
        self.record["revision"] = dep.git(self.source, "rev-parse", "HEAD").decode().strip()
        (self.source / "lib/resolved_flow.mli").unlink()
        with self.assertRaisesRegex(dep.Error, "renamed public API"):
            self.refresh("development")
        with self.assertRaises(dep.Error):
            dep.refresh(self.source / "lib", "recorded", self.store, self.record, self.runner)
        with self.assertRaisesRegex(dep.Error, "renamed public API"):
            dep.api_check({})
        self.fixture_git("add", "lib/resolved_flow.mli")
        self.fixture_git("commit", "-m", "missing interface fixture")
        self.record["revision"] = self.fixture_git("rev-parse", "HEAD").decode().strip()
        with self.assertRaisesRegex(dep.Error, "renamed public API"):
            self.refresh("recorded")
        self.assertEqual((self.store / "current").resolve(), Path(first["generation"]))

    def test_old_recorded_api_allows_new_development_and_refusal_preserves_selection(self):
        (self.source / "lib/project.mli").write_text("type t\n")
        self.fixture_git("add", "lib/project.mli")
        self.fixture_git("commit", "-m", "old project API fixture")
        self.record["revision"] = self.fixture_git("rev-parse", "HEAD").decode().strip()
        (self.source / "lib/project.mli").write_text(PROJECT_API)
        first = self.refresh("development")
        self.assertTrue(first["differs_from_recorded_snapshot"])
        calls = len(self.calls)
        with self.assertRaisesRegex(dep.Error, "explicit development refresh"):
            self.refresh("recorded")
        self.assertEqual(len(self.calls), calls)
        self.assertEqual((self.store / "current").resolve(), Path(first["generation"]))
        self.assertEqual(json.loads((self.store / "current/receipt.json").read_text()), first)

    def test_project_api_requires_all_new_signatures(self):
        dep.project_api_check(PROJECT_API.encode())
        for token in ("?source_inputs:string list", "val source_inputs", "val describe", "val emit_bundle",
                      "val emit_bundle_to_store", "store_dir:string", "Bundle.Publication.t",
                       "?inputs:Target.Inputs.t", "?methodology:Flow.Catalog.resolved", "?include_simulation:bool", "output_dir:string"):
            with self.subTest(token=token), self.assertRaises(dep.Error):
                dep.project_api_check(PROJECT_API.replace(token, "obsolete").encode())

    def test_bundle_publication_requires_signature_and_private_fields(self):
        dep.bundle_api_check(BUNDLE_API.encode())
        for token in ("val publish", "store_dir:string", "private", "directory : string", "reused : bool"):
            with self.subTest(token=token), self.assertRaises(dep.Error):
                dep.bundle_api_check(BUNDLE_API.replace(token, "obsolete").encode())

    def test_validate_source_reports_uncompiled_and_does_not_publish(self):
        result = dep.run(["python3", str(Path(dep.__file__)), "validate-source",
                          "--source", str(self.source), "--revision", self.record["revision"]])
        report = json.loads(result)
        self.assertIs(report["compiled"], False)
        self.assertIs(report["project_api_present"], True)
        self.assertFalse(self.store.exists())
        self.assertEqual(self.calls, [])

    def test_lock_contention(self):
        first = self.refresh()
        with (self.store / "writer.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(dep.Error, "writer lock"):
                self.refresh()
        self.assertEqual((self.store / "current").resolve(), Path(first["generation"]))

    def test_snapshot_does_not_follow_later_source_edits(self):
        self.mutate = True
        receipt = self.refresh("development")
        self.assertFalse(receipt["differs_from_recorded_snapshot"])
        self.assertEqual(self.captured["toolchain.lock"], b"fixture data\n")
        self.assertEqual(dep.status(self.store, self.record)["receipt"], receipt)

    def test_concurrent_capture_change_is_rejected(self):
        original = dep.development
        def moving(source, store):
            entries = original(source, store)
            (source / "toolchain.lock").write_text("moving")
            return entries
        with patch.object(dep, "development", moving):
            with self.assertRaisesRegex(dep.Error, "changed during capture"):
                self.refresh("development")
        self.assertFalse((self.store / "current").exists())

    def test_activation_repeated_and_status_stale_environment(self):
        first = self.refresh()
        second = self.refresh()
        env = dict(os.environ, OCAMLPATH="/unrelated path/lib:/manual/_build/install/default/lib",
                   PATH=os.environ["PATH"])
        command = '. "$1"; . "$2"; . "$2"; exec python3 -c "import os,json; print(json.dumps(dict(os.environ)))"'
        result = json.loads(dep.run(["sh", "-c", command, "sh",
                                    first["generation"] + "/activate.sh",
                                    second["generation"] + "/activate.sh"], env=env))
        self.assertEqual(result["OCAMLPATH"], second["generation"] + "/lib:" + env["OCAMLPATH"])
        self.assertEqual(result["PATH"], second["generation"] + "/bin:" + env["PATH"])
        with patch.dict(os.environ, HARDCAML_ASIC_GENERATION=first["generation"],
                        OCAMLPATH=first["generation"] + "/lib"):
            status = dep.status(self.store, self.record)
            self.assertTrue(status["active_is_older"])
            self.assertFalse(status["active_is_published"])
            self.assertTrue(status["active_library_path_is_first"])
            self.assertIn("not activated first in this shell", status["diagnostic"])
            self.assertIn(shlex.quote(str(self.store / "current/activate.sh")), status["diagnostic"])
        self.assertEqual(status["published_generation"], second["generation"])

    def test_explicit_manual_override_removal_is_recorded_and_carried_forward(self):
        manual = str(self.source / "_build/install/default/lib")
        first = dep.refresh(self.source, "recorded", self.store, self.record, self.runner,
                            remove_source_build_override=True)
        second = self.refresh()
        self.assertEqual(first["removed_library_paths"], [manual])
        self.assertEqual(second["removed_library_paths"], [manual])
        env = dict(os.environ, OCAMLPATH=manual + ":/unrelated/lib")
        result = dep.run(["sh", "-c", '. "$1"; python3 -c "import os; print(os.environ[\'OCAMLPATH\'])"',
                          "sh", second["generation"] + "/activate.sh"], env=env)
        self.assertEqual(result.decode().strip(), second["generation"] + "/lib:/unrelated/lib")

    def test_store_safety_and_read_only_status(self):
        self.assertIsNone(dep.status(self.store, self.record)["published_generation"])
        self.assertFalse(self.store.exists())
        self.store.mkdir()
        sentinel = self.store / "keep"
        sentinel.write_text("user work")
        with self.assertRaisesRegex(dep.Error, "ownership"):
            self.refresh()
        self.assertEqual(sentinel.read_text(), "user work")
        alias = self.root / "alias"
        alias.symlink_to(self.store)
        with self.assertRaises(dep.Error):
            dep.store_path(alias)
        with self.assertRaises(dep.Error):
            dep.store_path(self.root / "colon:path")

    def test_unsafe_symlink_rejected(self):
        (self.source / "escape").symlink_to("/etc/passwd")
        with self.assertRaisesRegex(dep.Error, "absolute source symlink"):
            self.refresh("development")
        self.assertFalse((self.store / "current").exists())

    def test_store_inside_source_is_excluded_and_foreign_pointer_preserved(self):
        self.store = self.source / "private-store"
        self.refresh("development")
        self.refresh("development")
        self.assertFalse(any(p.startswith("private-store/") for p in self.captured))
        current = self.store / "current"
        current.unlink()
        current.symlink_to(self.root)
        with self.assertRaisesRegex(dep.Error, "selection"):
            self.refresh()
        self.assertEqual(current.resolve(), self.root)

    def test_process_errors_and_cli_requires_explicit_mode(self):
        with self.assertRaisesRegex(dep.Error, "failure detail"):
            dep.run(["python3", "-c", "import sys; sys.stderr.write('failure detail'); sys.exit(3)"])
        result = subprocess.run(["python3", str(Path(dep.__file__)), "refresh", "--source", str(self.source)],
                                capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"--mode", result.stderr)


class RecordedSelectionTests(unittest.TestCase):
    """Record updates remain independent of installed selections; no Git writes."""

    def test_new_record_reports_old_selection_without_rewriting_it(self):
        record = dep.record_read(dep.ROOT / "asic-dependency.json")
        with tempfile.TemporaryDirectory(prefix="asic-record-selection-") as temporary:
            store = Path(temporary)
            (store / ".owner").write_text(dep.OWNER)
            generation = store / "generations/previous"
            generation.mkdir(parents=True)
            receipt = dict(mode="recorded", record=dict(record, revision="0" * 40),
                           observed_base_revision="0" * 40,
                           differs_from_recorded_snapshot=False,
                           captured_differs_from_observed_base=None)
            receipt_bytes = (json.dumps(receipt) + "\n").encode()
            (generation / "receipt.json").write_bytes(receipt_bytes)
            (generation / "activate.sh").write_bytes(b"# previous activation\n")
            (store / "current").symlink_to("generations/previous")
            before = {p.name: p.read_bytes() for p in generation.iterdir()}
            with patch.dict(os.environ, HARDCAML_ASIC_GENERATION=str(generation),
                            OCAMLPATH=str(generation / "lib")), \
                 patch.object(dep, "run", side_effect=AssertionError("unexpected process")):
                status = dep.status(store, record)
            self.assertTrue(status["baseline_mismatch"])
            self.assertTrue(status["active_is_published"])
            self.assertTrue(status["active_library_path_is_first"])
            self.assertEqual(status["receipt"], receipt)
            self.assertEqual(status["record"], record)
            self.assertEqual(os.readlink(store / "current"), "generations/previous")
            self.assertEqual({p.name: p.read_bytes() for p in generation.iterdir()}, before)

    def test_recorded_mode_validates_committed_bytes_before_build_or_publication(self):
        with tempfile.TemporaryDirectory(prefix="asic-record-gate-") as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            store = Path(temporary) / "store"
            record = dep.record_read(dep.ROOT / "asic-dependency.json")
            entries = {"dune-project": ("100644", b"incompatible committed provider")}
            with patch.object(dep, "source_check", return_value=source), \
                 patch.object(dep, "committed", return_value=entries) as committed, \
                 patch.object(dep, "git", return_value=record["revision"].encode()), \
                 patch.object(dep, "development", side_effect=AssertionError("unexpected worktree capture")), \
                 patch.object(dep, "run", side_effect=AssertionError("unexpected build")):
                with self.assertRaisesRegex(dep.Error, "renamed public API"):
                    dep.refresh(source, "recorded", store, record, jobs=2)
            committed.assert_called_once_with(source, record["revision"])
            self.assertFalse((store / "current").exists())
            self.assertFalse((store / "generations").exists())


class JobsTests(unittest.TestCase):
    """No Git repositories or compiler processes: exercise resource propagation."""

    def test_bounded_jobs_reach_build_install_and_validation(self):
        with tempfile.TemporaryDirectory(prefix="asic-jobs-") as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            store = Path(temporary) / "store"
            entries = {"dune-project": ("100644", b"(lang dune 3.17)\n")}
            calls = []
            with patch.object(dep, "source_check", return_value=source), \
                 patch.object(dep, "committed", return_value=entries), \
                 patch.object(dep, "git", return_value=b"a" * 40), \
                 patch.object(dep, "development", return_value=entries), \
                 patch.object(dep, "api_check"), patch.object(dep, "validate_install") as validate:
                receipt = dep.refresh(source, "development", store, {"revision": "a" * 40},
                                      runner=lambda argv, **kwargs: calls.append(argv), jobs=2)
            self.assertEqual([argv[argv.index("-j") + 1] for argv in calls], ["2", "2"])
            self.assertEqual(validate.call_args.kwargs["jobs"], 2)
            self.assertEqual(str((store / "current").resolve()), receipt["generation"])

    def test_invalid_jobs_fail_before_any_source_or_store_access(self):
        for jobs in (0, -1, True, 1.5, "2"):
            with patch.object(dep, "source_check") as source:
                with self.assertRaisesRegex(dep.Error, "positive integer"):
                    dep.refresh(None, None, None, None, jobs=jobs)
                source.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
