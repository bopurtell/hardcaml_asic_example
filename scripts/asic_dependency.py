#!/usr/bin/env python3
"""Explicit local hardcaml_asic selection; no provisioning or shared switch writes."""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "https://github.com/LeEmperor/hardcaml_asic.git"
OWNER = "hardcaml_asic_example dependency store v1\n"
EXCLUDED = {".git", "_build", ".toolchain", ".dev", "__pycache__"}
PROBE = """open Hardcaml_asic
let project (r : Resolved_flow.t) : Elaborated_project.t = r.elaborated_project
let render = Bundle.render ?simulation_project:None
let create = Project.create ?source_inputs:(Some ([] : string list))
let source_inputs : Project.t -> string list = Project.source_inputs
let describe : Project.t -> Core.Sexp.t = Project.describe
let emit_bundle : ?inputs:Target.Inputs.t -> ?methodology:Flow.Catalog.resolved -> ?include_simulation:bool -> Project.t
  -> source_root:string -> output_dir:string -> Bundle.t Core.Or_error.t = Project.emit_bundle
let emit_store : ?inputs:Target.Inputs.t -> ?methodology:Flow.Catalog.resolved -> ?include_simulation:bool -> Project.t
  -> source_root:string -> store_dir:string -> (Bundle.t * Bundle.Publication.t) Core.Or_error.t = Project.emit_bundle_to_store
let publish : Bundle.t -> store_dir:string -> Bundle.Publication.t Core.Or_error.t = Bundle.publish
let publication (p : Bundle.Publication.t) = p.directory, p.reused
let catalog = Flow.Catalog.create
let profiles = Flow.Profile.create
let methodology = Flow.Methodology.create
let selection = Flow.Selection.create
let parameter = Flow.Parameter.of_scalar
let list : Flow.Catalog.t -> Yojson.Safe.t = Flow_spec.list_to_yojson
let describe_flow : Flow.Catalog.Entry.t -> Yojson.Safe.t = Flow_spec.describe_to_yojson
let prepare : ?inputs:Target.Inputs.t -> ?selection:Flow.Selection.t
  -> ?request:Flow.Parameter.assignment list -> ?include_simulation:bool
  -> ?catalog_inputs:string list -> ?expected_plan_identity:string
  -> catalog:Flow.Catalog.t -> endpoint:Flow.Stage.t -> Project.t -> source_root:string
  -> Methodology_plan.Prepared.t Core.Or_error.t = Methodology_plan.prepare
let prepared (p : Methodology_plan.Prepared.t) =
  Methodology_plan.Prepared.bundle p, Methodology_plan.Prepared.plan p
let plan (p : Methodology_plan.t) = Methodology_plan.to_yojson p,
  Methodology_plan.to_string p, Methodology_plan.plan_identity p
let () = ignore project; ignore render; ignore create; ignore source_inputs;
  ignore describe; ignore emit_bundle; ignore emit_store; ignore publish; ignore publication
  ; ignore catalog; ignore profiles; ignore methodology; ignore selection; ignore parameter
  ; ignore list; ignore describe_flow; ignore prepare; ignore prepared; ignore plan
"""


class Error(Exception):
    pass


def run(argv, *, cwd=None, env=None):
    result = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if result.returncode:
        raise Error(f"{shlex.join(map(str, argv))}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def git(source, *args):
    # Ignore inherited Git selectors/config; all operations here are read-only.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
    return run(["git", "-C", str(source), *args], env=env)


def record_read(path):
    record = json.loads(path.read_text())
    if (set(record) != {"schema", "package", "repository", "revision"}
            or record["schema"] != 1 or record["package"] != "hardcaml_asic"
            or record["repository"] != REPOSITORY
            or not re.fullmatch(r"[0-9a-f]{40}", record["revision"])):
        raise Error("invalid dependency record (expected schema 1, hardcaml_asic, repository and full revision)")
    return record


def source_check(source):
    source = source.resolve(strict=True)
    top = Path(os.fsdecode(git(source, "rev-parse", "--show-toplevel")).strip()).resolve()
    if source != top:
        raise Error("--source must be the expected provider repository root")
    return source


def safe_name(name):
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise Error(f"unsafe source path: {name!r}")
    return p


def included(name, source, store):
    p = safe_name(name)
    # These existing private Dune roots are build products, including broken
    # install symlinks, not authored inputs. Never traverse or repair them.
    private_build = p.parts[0] in {'_build_pt8_workbench', '_build_pt8_workloads'}
    return not (private_build or set(p.parts) & EXCLUDED or (store and (source / name).is_relative_to(store)))


def committed(source, revision):
    actual = git(source, "rev-parse", "--verify", revision + "^{commit}").decode().strip()
    if actual != revision:
        raise Error("recorded revision must name the exact commit")
    entries = {}
    for entry in git(source, "ls-tree", "-rz", revision).split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        name = os.fsdecode(name)
        if not included(name, source, None):
            continue
        if kind != "blob" or mode not in {"100644", "100755", "120000"}:
            raise Error(f"unsupported committed entry: {name}")
        entries[name] = (mode, git(source, "cat-file", "blob", oid))
    return entries


def development(source, store):
    entries = {}
    names = git(source, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    for raw in sorted(set(names.split(b"\0")) - {b""}):
        name = os.fsdecode(raw)
        if not included(name, source, store):
            continue
        path = source / name
        # Never follow a replaced parent directory outside the source tree.
        if path.parent.resolve() != path.parent or not path.parent.resolve().is_relative_to(source):
            raise Error(f"symlinked source parent: {name}")
        try:
            info = path.lstat()
        except FileNotFoundError:  # tracked deletion
            continue
        if stat.S_ISLNK(info.st_mode):
            entries[name] = ("120000", os.fsencode(os.readlink(path)))
        elif stat.S_ISREG(info.st_mode):
            with path.open("rb") as stream:
                before = os.fstat(stream.fileno())
                data = stream.read()
                after = os.fstat(stream.fileno())
            def identity(s):
                return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(before) != identity(after) or identity(path.lstat()) != identity(info) or identity(before) != identity(info):
                raise Error("source changed during capture; retry refresh")
            entries[name] = ("100755" if info.st_mode & 0o111 else "100644", data)
        else:
            raise Error(f"unsupported source entry: {name}")
    return entries


# Type spellings inside project.mli for each provider layout (see SOURCE_LAYOUTS).
PROJECT_TYPE_NAMES = {
    "flat": {"inputs": r"Target\.Inputs\.t", "resolved": r"Flow\.Catalog\.resolved", "bundle": r"Bundle"},
    "grouped": {"inputs": r"Platform\.Target\.Inputs\.t",
                "resolved": r"Hardcaml_asic_flow_domain\.Catalog\.resolved", "bundle": r"Elaboration\.Bundle"},
}


def project_api_check(data, layout="flat"):
    text = re.sub(r"\s+", "", re.sub(r"\(\*.*?\*\)", "", data.decode(), flags=re.S))
    names = PROJECT_TYPE_NAMES[layout]
    common = r"\?inputs:{inputs}->\?methodology:{resolved}->\?include_simulation:bool->t->source_root:string->".format(**names)
    signatures = {
        "create": r"valcreate:(?:(?!val).)*?\?source_inputs:stringlist(?:(?!val).)*?->unit->tOr_error\.t",
        "source_inputs": r"valsource_inputs:t->stringlist",
        "describe": r"valdescribe:t->Sexp\.t",
        "emit_bundle": r"valemit_bundle:" + common + r"output_dir:string->{bundle}\.tOr_error\.t".format(**names),
        "emit_bundle_to_store": r"valemit_bundle_to_store:" + common
            + r"store_dir:string->\({bundle}\.t\*{bundle}\.Publication\.t\)Or_error\.t".format(**names),
    }
    for name, signature in signatures.items():
        if not re.search(signature, text):
            raise Error(f"incompatible Project.{name} API; use explicit development refresh "
                        "(--mode development) and re-activate current/activate.sh until the owner updates the pin")


# Provider interface locations: "flat" before the namespace reorganization (ad290d8),
# "grouped" after it. One layout is chosen per check and every file comes from it.
SOURCE_LAYOUTS = {
    "flat": {"elaborated_project": "lib/elaborated_project.mli", "resolved": "lib/resolved_flow.mli",
             "bundle": "lib/bundle.mli", "project": "lib/project.mli",
             "catalog": "lib/flow/catalog.mli", "profile": "lib/flow/profile.mli",
             "methodology": "lib/flow/methodology.mli", "selection": "lib/flow/selection.mli",
             "parameter": "lib/flow/parameter.mli", "flow_spec": "lib/flow_spec.mli",
             "methodology_plan": "lib/methodology_plan.mli"},
    "grouped": {"elaborated_project": "lib/elaboration/elaborated_project.mli",
                "resolved": "lib/elaboration/resolved.mli", "bundle": "lib/elaboration/bundle.mli",
                "project": "lib/project.mli",
                "catalog": "flow_domain/catalog.mli", "profile": "flow_domain/profile.mli",
                "methodology": "flow_domain/methodology.mli", "selection": "flow_domain/selection.mli",
                "parameter": "flow_domain/parameter.mli", "flow_spec": "lib/flow/spec.mli",
                "methodology_plan": "lib/methodology_plan.mli"},
}
INSTALL_LAYOUTS = {
    "flat": {"elaborated_project": "elaborated_project.mli", "resolved": "resolved_flow.mli",
             "bundle": "bundle.mli", "project": "project.mli",
             "catalog": "flow_domain/catalog.mli", "profile": "flow_domain/profile.mli",
             "methodology": "flow_domain/methodology.mli", "selection": "flow_domain/selection.mli",
             "parameter": "flow_domain/parameter.mli", "flow_spec": "flow_spec.mli",
             "methodology_plan": "methodology_plan.mli"},
    "grouped": {"elaborated_project": "elaboration/elaborated_project.mli",
                "resolved": "elaboration/resolved.mli", "bundle": "elaboration/bundle.mli",
                "project": "project.mli",
                "catalog": "flow_domain/catalog.mli", "profile": "flow_domain/profile.mli",
                "methodology": "flow_domain/methodology.mli", "selection": "flow_domain/selection.mli",
                "parameter": "flow_domain/parameter.mli", "flow_spec": "flow/spec.mli",
                "methodology_plan": "methodology_plan.mli"},
}


def select_layout(layouts, exists, message):
    # The elaborated_project interface marks the layout; both or neither present is refused.
    found = [name for name, paths in layouts.items() if exists(paths["elaborated_project"])]
    if len(found) != 1:
        candidates = " or ".join(paths["elaborated_project"] for paths in layouts.values())
        raise Error(f"{message}: {'mixed provider layouts' if found else 'missing/incompatible'} {candidates}")
    return found[0]


def api_check(entries):
    layout = select_layout(SOURCE_LAYOUTS, entries.__contains__,
                           "expected hardcaml_asic source with renamed public API")
    paths = SOURCE_LAYOUTS[layout]
    required = {"dune-project": b"hardcaml_asic", paths["elaborated_project"]: b"type t",
                paths["resolved"]: b"elaborated_project : Elaborated_project.t",
                paths["bundle"]: b"?simulation_project:",
                "bin/dune": b"(public_name hardcaml-asic-flow)"}
    for name, token in required.items():
        if name not in entries or token not in entries[name][1]:
            raise Error(f"expected hardcaml_asic source with renamed public API: missing/incompatible {name}")
    project_api_check(entries.get(paths["project"], (None, b""))[1], layout)
    native_dune = re.sub(r";[^\n]*", "", entries["bin/dune"][1].decode())
    if not re.search(r"\(executable\s+\(name flow_cli\)(?:(?!\(executable).)*?\(public_name hardcaml-asic-flow\)", native_dune, re.S):
        raise Error("expected native flow_cli executable owning hardcaml-asic-flow in bin/dune")
    bundle_api_check(entries[paths["bundle"]][1])
    catalog_api_check({name: data for name, (_, data) in entries.items()}, paths)


def catalog_api_check(files, paths):
    # Source-only gate; compilation of PROBE checks the precise installed types.
    required = {
        "catalog": ("val create", "val resolve", "val declaration"),
        "profile": ("val create", "val assignments"),
        "methodology": ("Librelane_classic_v1", "val create"),
        "selection": ("val create", "val default"),
        "parameter": ("val of_scalar", "val check_assignments"),
        "flow_spec": ("val list_to_yojson", "val describe_to_yojson"),
        "methodology_plan": ("module Prepared", "val prepare", "?catalog_inputs:string list",
                             "?expected_plan_identity:string", "val plan_identity", "val to_string"),
    }
    for role, tokens in required.items():
        name = paths[role]
        text = re.sub(r"\(\*.*?\*\)", "", files.get(name, b"").decode(), flags=re.S)
        text = re.sub(r"\s+", " ", text)
        if any(token not in text for token in tokens):
            raise Error(f"incompatible catalog/plan API: {name}; use explicit development refresh")


def namedflow_check(metadata):
    contract = metadata.get("cli_contract", {}) if isinstance(metadata, dict) else {}
    caps = contract.get("capabilities", {}) if isinstance(contract, dict) else {}
    if (not isinstance(contract, dict) or type(contract.get("version")) is not int or contract["version"] != 4
            or not isinstance(caps, dict) or caps.get("namedflow1") is not True):
        raise Error("installed named-flow provider requires exact CLI4 + namedflow1=true")


def provider_metadata(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Error(f"duplicate provider metadata field: {key}")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique)
    except ValueError as exc:
        raise Error("malformed provider metadata") from exc


def bundle_api_check(data):
    text = re.sub(r"\s+", "", re.sub(r"\(\*.*?\*\)", "", data.decode(), flags=re.S))
    if ("modulePublication:sigtypet=private{directory:string;reused:bool}" not in text
            or "valpublish:t->store_dir:string->Publication.tOr_error.t" not in text):
        raise Error("incompatible Bundle publication API")


def materialize(entries, destination):
    for name in entries:
        for parent in PurePosixPath(name).parents:
            if str(parent) in entries:
                raise Error(f"source file used as directory: {parent}")
    for name, (mode, data) in sorted(entries.items()):
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "120000":
            target = os.fsdecode(data)
            if os.path.isabs(target):
                raise Error(f"absolute source symlink: {name}")
            path.symlink_to(target)
        else:
            path.write_bytes(data)
            path.chmod(0o755 if mode == "100755" else 0o644)
    for name, (mode, _) in entries.items():
        if mode == "120000":
            try:
                target = (destination / name).resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise Error(f"broken/cyclic source symlink: {name}") from exc
            if not target.is_relative_to(destination) or not target.is_file():
                raise Error(f"source symlink escapes snapshot: {name}")


def checksum(entries):
    digest = hashlib.sha256()
    for name, (mode, data) in sorted(entries.items()):
        for value in (os.fsencode(name), mode.encode(), data):
            digest.update(str(len(value)).encode() + b":" + value)
    return digest.hexdigest()


def store_path(path):
    path = Path(os.path.abspath(path))
    if path != path.resolve() or path == Path(path.anchor) or any(c in str(path) for c in ":\n\r"):
        raise Error("store must be a non-symlink path without colons or newlines")
    return path


def owned(store):
    if store.is_symlink() or not store.is_dir():
        raise Error("store is not a managed directory")
    marker = store / ".owner"
    if marker.is_symlink() or not marker.is_file() or marker.read_text() != OWNER:
        raise Error("refusing existing destination without exact store ownership marker")
    for name in ("generations", "writer.lock"):
        if (store / name).is_symlink():
            raise Error(f"unsafe store entry: {name}")
    current = store / "current"
    if current.is_symlink():
        selected = current.resolve(strict=True)
        if selected.parent != store / "generations" or not (selected / "receipt.json").is_file():
            raise Error("selection is not a published managed generation")
    elif current.exists():
        raise Error("refusing non-symlink current destination")


@contextlib.contextmanager
def writer(store):
    if not store.exists():
        store.parent.mkdir(parents=True, exist_ok=True)
        try:
            store.mkdir()
        except FileExistsError:
            raise Error("store initialization contention; retry")
        (store / ".owner").write_text(OWNER)
    owned(store)
    with (store / "writer.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Error("refresh already in progress (store writer lock)")
        yield


def activation(generation, generations, removed_library_paths=()):
    # Exact known prefixes only, never glob-delete arbitrary OCAMLPATH entries.
    def clean(variable, suffix):
        paths = [str(p / suffix) for p in generations]
        if suffix == "lib":
            paths += list(removed_library_paths)
        patterns = "|".join(shlex.quote(p) for p in paths)
        return f"""_asic_rest=${{{variable}-}}
_asic_out=
_asic_sep=
if [ -n "$_asic_rest" ]; then
while :; do
  case $_asic_rest in *:*) _asic_part=${{_asic_rest%%:*}}; _asic_rest=${{_asic_rest#*:}}; _asic_more=1;;
    *) _asic_part=$_asic_rest; _asic_more=0;; esac
  case $_asic_part in {patterns}) ;; *)
    _asic_out=$_asic_out$_asic_sep$_asic_part; _asic_sep=:;; esac
  [ "$_asic_more" = 1 ] || break
done
fi
{variable}={shlex.quote(str(generation / suffix))}${{_asic_sep:+:}}$_asic_out
export {variable}
"""
    return ("# Generated; source again after refresh. Paths name an immutable generation.\n"
            + clean("OCAMLPATH", "lib") + clean("PATH", "bin")
            + "HARDCAML_ASIC_GENERATION="
            + shlex.quote(str(generation)) + "\nexport HARDCAML_ASIC_GENERATION\n"
            + "unset _asic_rest _asic_out _asic_sep _asic_part _asic_more\n")


def validate_install(generation, work, runner, jobs=20):
    package = generation / "lib/hardcaml_asic"
    layout = select_layout(INSTALL_LAYOUTS, lambda name: (package / name).is_file(), "incomplete installation")
    paths = INSTALL_LAYOUTS[layout]
    for relative in ("META", "dune-package", paths["elaborated_project"], paths["resolved"], paths["bundle"],
                     paths["project"],
                     "flow/hardcaml_asic_flow/__init__.py",
                     "flow/hardcaml_asic_flow/backend_protocol.py",
                     "flow/hardcaml_asic_flow/librelane_bridge.py",
                     "flow/hardcaml_asic_flow/stage_metadata_probe.py",
                     "flow/hardcaml_asic_flow/probe.py",
                     "flow/hardcaml_asic_flow/managed_python.py",
                     "flow/hardcaml_asic_flow/paths.py",
                     "flow/hardcaml_asic_flow/runtime_contract.py",
                     "flow/hardcaml_asic_flow/runtime_observation.py",
                     "flow/hardcaml_asic_flow/data/managed-python.json",
                     "flow/hardcaml_asic_flow/data/toolchain.lock",
                     "flow/hardcaml_asic_flow/data/toolchain.sh", "flow/hardcaml_asic_flow/data/version.txt"):
        if not (package / relative).is_file():
            raise Error(f"incomplete installation: {relative}")
    for name, token in ((paths["elaborated_project"], "type t"),
                        (paths["resolved"], "elaborated_project : Elaborated_project.t"),
                        (paths["bundle"], "?simulation_project:")):
        if token not in (package / name).read_text():
            raise Error(f"installed public API incompatible: {name}")
    project_api_check((package / paths["project"]).read_bytes(), layout)
    catalog_api_check({name: (package / name).read_bytes() for name in paths.values() if (package / name).is_file()},
                      paths)
    for name in ("hardcaml-asic-flow", *("hardcaml-asic-experimental-" + suffix for suffix in (
            "execute", "archive", "finalization", "finalization-inspect", "postcheck",
            "report", "collect", "run", "preflight", "observation-read", "stages",
            "plan-inspect", "segment-execute", "checkpoint-inspect"))):
        executable = generation / "bin" / name
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise Error(f"incomplete native installation: {name}")
        if executable.read_bytes()[:4] != b"\x7fELF":
            raise Error(f"expected native executable: {name}")
    bundle_api_check((package / paths["bundle"]).read_bytes())
    for path in generation.rglob("*"):
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(generation):
            raise Error(f"installed symlink escapes immutable generation: {path}")
    env = dict(os.environ)
    env["OCAMLPATH"] = str(generation / "lib") + (":" + env["OCAMLPATH"] if env.get("OCAMLPATH") else "")
    env["PATH"] = str(generation / "bin") + os.pathsep + env.get("PATH", "")
    found = runner(["ocamlfind", "query", "hardcaml_asic"], env=env).decode().strip()
    if Path(found).resolve() != package.resolve():
        raise Error("compiler resolves another hardcaml_asic package")
    probe = work / "probe.ml"
    probe.write_text(PROBE)
    runner(["ocamlfind", "ocamlc", "-package", "hardcaml_asic", "-c", str(probe)], cwd=work, env=env)
    if str(work / "source") in (package / "dune-package").read_text():
        raise Error("installed Dune metadata references temporary source capture")
    consumer = work / "consumer"
    consumer.mkdir()
    (consumer / "dune-project").write_text("(lang dune 3.17)\n")
    (consumer / "dune").write_text("(executable (name probe) (libraries hardcaml_asic))\n")
    (consumer / "probe.ml").write_text(PROBE)
    runner(["dune", "build", "-j", str(jobs), "--root", str(consumer), "probe.exe"], cwd=consumer, env=env)
    runner([str(generation / "bin/hardcaml-asic-flow"), "--help"], env=env)
    metadata = provider_metadata(runner([str(generation / "bin/hardcaml-asic-flow"), "--version", "--json"], env=env))
    namedflow_check(metadata)


def refresh(source, mode, store, record, runner=run, remove_source_build_override=False, jobs=20):
    if type(jobs) is not int or jobs <= 0:
        raise Error("jobs must be a positive integer")
    source = source_check(source)
    if source == store or source.is_relative_to(store):
        raise Error("source cannot be inside the store")
    with writer(store):
        baseline = committed(source, record["revision"])
        base = git(source, "rev-parse", "HEAD").decode().strip()
        observed_base = committed(source, base) if mode == "development" else baseline
        if mode == "development":
            entries = development(source, store)
            if entries != development(source, store) or base != git(source, "rev-parse", "HEAD").decode().strip():
                raise Error("source changed during capture; retry refresh")
        else:
            entries = baseline
        api_check(entries)
        generations = store / "generations"
        generations.mkdir(exist_ok=True)
        generation = generations / uuid.uuid4().hex
        generation.mkdir()
        # Retain failed private generations too; never delete user destinations.
        with tempfile.TemporaryDirectory(prefix="capture-", dir=store) as temporary:
            work = Path(temporary)
            snapshot = work / "source"
            snapshot.mkdir()
            materialize(entries, snapshot)
            # -p implies --root .; cwd is the captured source, not the checkout.
            runner(["dune", "build", "-j", str(jobs), "--build-dir", "_build",
                    "-p", "hardcaml_asic", "@install"], cwd=snapshot)
            runner(["dune", "install", "-j", str(jobs), "--root", str(snapshot), "--prefix", str(generation),
                    "--build-dir", "_build", "--libdir", str(generation / "lib"),
                    "hardcaml_asic"], cwd=snapshot)
            validate_install(generation, work, runner, jobs=jobs)
        removed_paths = []
        if (store / "current").is_symlink():
            removed_paths = json.loads((store / "current/receipt.json").read_text()).get("removed_library_paths", [])
        if remove_source_build_override:
            manual = str(source / "_build/install/default/lib")
            if any(c in manual for c in ":\n\r"):
                raise Error("manual override path contains a path separator/newline")
            removed_paths = sorted(set(removed_paths + [manual]))
        receipt = {"schema": 1, "mode": mode, "source": str(source), "record": record,
                   "observed_base_revision": base, "generation": str(generation),
                   "snapshot_sha256": checksum(entries),
                   "differs_from_recorded_snapshot": entries != baseline,
                   "captured_differs_from_observed_base": entries != observed_base if mode == "development" else None,
                   "removed_library_paths": removed_paths,
                   "source_state": ("committed bytes; working-tree state not inspected" if mode == "recorded"
                                    else "captured bytes; not an atomic checkout or a clean-tree claim"),
                   "identity_scope": "local refresh receipt, NOT P6.5 source stamp",
                   "refreshed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        (generation / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        known = [p for p in generations.iterdir() if p.is_dir() and not p.is_symlink()]
        (generation / "activate.sh").write_text(activation(generation, known, removed_paths))
        pointer = store / (".selection-" + uuid.uuid4().hex)
        pointer.symlink_to(generation.relative_to(store))
        current = store / "current"
        if current.exists() and not current.is_symlink():
            raise Error("refusing to overwrite non-symlink current destination")
        os.replace(pointer, current)
        return receipt


def status(store, record):
    result = {"record": record, "published_generation": None,
              "environment_active_generation": os.environ.get("HARDCAML_ASIC_GENERATION"),
              "environment_ocamlpath": os.environ.get("OCAMLPATH", ""),
              "receipt": None, "diagnostic": "Run refresh with --source and --mode, then source current/activate.sh"}
    if store.exists():
        owned(store)
        current = store / "current"
        if current.is_symlink():
            generation = current.resolve(strict=True)
            if generation.parent != store / "generations":
                raise Error("selection points outside managed generations")
            receipt = json.loads((generation / "receipt.json").read_text())
            result.update(published_generation=str(generation), receipt=receipt,
                          development_override=receipt["mode"] == "development",
                          development_snapshot_dirty=receipt["captured_differs_from_observed_base"],
                          development_base_mismatch=(receipt["mode"] == "development"
                                                     and receipt["observed_base_revision"] != record["revision"]),
                          baseline_mismatch=receipt["record"] != record or receipt["differs_from_recorded_snapshot"],
                          diagnostic="Source current/activate.sh after each refresh")
    active = result["environment_active_generation"]
    result["active_is_published"] = bool(active and active == result["published_generation"])
    result["active_is_older"] = bool(active and active != result["published_generation"])
    result["active_library_path_is_first"] = bool(active and os.environ.get("OCAMLPATH", "").split(":")[0] == active + "/lib")
    if result["published_generation"] and not (result["active_is_published"] and result["active_library_path_is_first"]):
        result["diagnostic"] = ("Published provider is not activated first in this shell; run: . "
                                + shlex.quote(str(store / "current/activate.sh"))
                                + "; then ocamlfind query hardcaml_asic. Refresh alone cannot activate the calling shell.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, default=ROOT / "asic-dependency.json")
    parser.add_argument("--store", type=Path, default=ROOT / ".dev/asic")
    commands = parser.add_subparsers(dest="command", required=True)
    refresh_parser = commands.add_parser("refresh")
    refresh_parser.add_argument("--source", type=Path, required=True)
    refresh_parser.add_argument("--mode", choices=("recorded", "development"), required=True)
    refresh_parser.add_argument("--jobs", type=int, default=20,
                                help="maximum Dune jobs for build, install and consumer probe (default: 20)")
    refresh_parser.add_argument("--remove-source-build-override", action="store_true",
                                help="record removal of this source's _build/install/default/lib during activation")
    commands.add_parser("status").add_argument("--json", action="store_true")
    validate = commands.add_parser("validate-source", help="read-only committed API check; no build")
    validate.add_argument("--source", type=Path, required=True)
    validate.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate-source":
            if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
                raise Error("expected full 40-character commit revision")
            entries = committed(source_check(args.source), args.revision)
            api_check(entries)
            print(json.dumps({"revision": args.revision, "renamed_api_present": True, "project_api_present": True,
                              "snapshot_sha256": checksum(entries), "compiled": False}))
            return
        record = record_read(args.record)
        store = store_path(args.store)
        result = (refresh(args.source, args.mode, store, record,
                          remove_source_build_override=args.remove_source_build_override,
                          jobs=args.jobs) if args.command == "refresh"
                  else status(store, record))
        print(json.dumps(result, indent=2))
    except (Error, OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"asic dependency: {exc}\n")


if __name__ == "__main__":
    main()
