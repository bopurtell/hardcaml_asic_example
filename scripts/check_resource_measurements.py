#!/usr/bin/env python3
"""PT.5b C: immutable raw capture and independent capture acceptance.

This is not a resource-evidence parser. Installed acceptance consumes ASIC-owned
schema-2 APIs, with independent raw evidence oracles and disposable negatives.
No provider discovery, build, EDA, external model reads, or original resealing.
"""
import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import sys
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integration/workbench"))
from config_location import existing_configs

HISTORIES = (ROOT / "acceptance/sram/8b48d7d0-functional",
             ROOT / "acceptance/sram/physical-p4")
BASE = HISTORIES[1]
LIVE = ROOT / "_flow_results/sram-physical/runs/20261025T034710180883Z_be961b2c"
FLOW = LIVE / "project/runs/asic"
ACCEPTANCE = ROOT / "acceptance/resource-measurements"
RUN_ID = "be961b2c95f74c81ad6af81ca4d2b269"
BUILD = "fa38d9064dffdf2ec1578c79c2e8890eba81bf704af460e85fcc6031b707d53c"
TOP = "tt_um_program_memory"
INSTANCE = "hc_resource_7_program"
MACRO = "RM_IHPSG13_1P_256x16_c2_bm_bist"
CORNERS = ("nom_fast_1p32V_m40C", "nom_slow_1p08V_125C", "nom_typ_1p20V_25C")


def load(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def files(root):
    return sorted(p for p in root.rglob("*") if p.is_file())


def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in files(root)}


def protected_state():
    """Hash histories/config bytes and record all existing development pointers."""
    result = {str(p.relative_to(ROOT)): sha(p) for root in HISTORIES for p in files(root)}
    for p in [ROOT / "asic-dependency.json", *existing_configs(ROOT)]:
        result[str(p.relative_to(ROOT))] = sha(p)
    for p in sorted((ROOT / ".dev").glob("*/current")):
        if p.is_symlink() and p.parent.name != "asic-pt5b":
            result[str(p.relative_to(ROOT))] = {
                "symlink": os.readlink(p), "mtime_ns": p.lstat().st_mtime_ns}
    return result


def new_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def identity(path):
    run = load(path)
    actual = tuple(run[k] for k in ("run_id", "build_identity", "status", "completed_stage"))
    expected = (RUN_ID, BUILD, "completed", "full")
    if actual != expected:
        raise ValueError(f"not the accepted execution: {path}: {actual!r}")


def capture(destination):
    destination = destination.resolve()
    if not destination.is_relative_to(ACCEPTANCE.resolve()) or destination == ACCEPTANCE.resolve():
        raise ValueError("new capture must be beneath acceptance/resource-measurements")
    if destination.exists():
        raise FileExistsError(destination)
    before = protected_state()
    identity(BASE / "run.json")
    identity(LIVE / "run.json")
    if load(LIVE / "project/manifest.json")["identity"] != BUILD:
        raise ValueError("live project manifest is not the accepted build")
    mapping = {}

    def select(source, relative, role):
        source = source.absolute()
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"missing or symlink source: {source}")
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(relative)
        prior = mapping.get(str(relative))
        if prior and prior[0] != source:
            if sha(prior[0]) != sha(source):
                raise ValueError(f"conflicting original bytes: {relative}")
        # Keep both origins when the curated artifact and live artifact agree.
        mapping.setdefault(str(relative), (source, role, []))[2].append(str(source))

    for p in files(BASE):
        select(p, Path("run") / p.relative_to(BASE), "unchanged_curated_base")
    for p in files(FLOW / "56-openroad-stapostpnr"):
        select(p, Path("run/flow") / p.relative_to(FLOW), "postroute_sta_raw")
    # Retain actual inputs referenced by STA state, without following PDK refs.
    # Input-state metrics/SDFs are explicitly not post-route completion evidence.
    state = load(FLOW / "56-openroad-stapostpnr/state_in.json")

    def state_paths(value):
        if isinstance(value, str):
            yield Path(value)
        elif isinstance(value, dict):
            for child in value.values():
                yield from state_paths(child)
        elif isinstance(value, list):
            for child in value:
                yield from state_paths(child)

    for key, value in state.items():
        if key != "metrics":
            for p in state_paths(value):
                if not p.is_absolute() or not p.resolve().is_relative_to(FLOW.resolve()):
                    raise ValueError(f"STA state input outside selected flow: {p}")
                select(p, Path("run/flow") / p.relative_to(FLOW), "sta_state_input_not_completion")
    for name in ("or_metrics_out.json", "config.json", "state_in.json", "state_out.json",
                 "COMMANDS", "_env.tcl", "openroad-floorplan.log"):
        p = FLOW / "13-openroad-floorplan" / name
        select(p, Path("run/flow") / p.relative_to(FLOW), "native_gross_rectangle_producer")
    # These are the paths actually read in sta.log, distinct from state aliases.
    for relative in ("constraints/top.sdc", f"macros/{MACRO}.blackbox.v"):
        select(LIVE / "project" / relative, Path("run/bundle") / relative, "sta_logged_input")
    for relative in ("run.json", "preflight.json", "results.json", "project/manifest.json"):
        select(LIVE / relative, Path("run/capture-origin") / relative, "original_live_identity")

    destination.mkdir(parents=True)
    entries = []
    try:
        for relative, (source, role, origins) in sorted(mapping.items()):
            target = destination / relative
            digest = sha(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if sha(target) != digest or any(sha(Path(p)) != digest for p in origins):
                raise ValueError(f"source changed during capture: {source}")
            entries.append(dict(source=str(source), additional_sources=origins[1:],
                                destination=relative, role=role, size_bytes=target.stat().st_size,
                                source_sha256=digest, destination_sha256=digest))
        after = protected_state()
        if before != after:
            raise ValueError("protected histories/configuration/pointers changed during capture")
        new_json(destination / "capture.json", dict(
            scope="PT.5b C unchanged raw capture; not public-provider acceptance or new EDA",
            captured_at=datetime.now(timezone.utc).isoformat(), script_sha256=sha(Path(__file__)),
            run_id=RUN_ID, build_identity=BUILD, original_live_run=str(LIVE), curated_base=str(BASE),
            source_policy="byte copies; absolute references preserved; no external PDK reads",
            producer_policy="historical coarse records, no fabricated modern checkpoint",
            protected_before=before, protected_after=after, entries=entries,
            file_count=len(entries), total_bytes=sum(e["size_bytes"] for e in entries),
            public_acceptance="blocked_pending_integrated_provider_and_handoffs"))
    except Exception:
        # Leave a partial capture visible; never overwrite/reseal it on retry.
        raise
    return destination


class CaptureAcceptance(unittest.TestCase):
    """Independent raw spot oracles, not an alternative public implementation."""
    def test_capture_closure_and_original_sources(self):
        receipt = load(self.capture / "capture.json")
        entries = receipt["entries"]
        self.assertEqual(receipt["protected_before"], receipt["protected_after"])
        self.assertEqual(receipt["protected_after"], protected_state())
        self.assertEqual(len(entries), len({e["destination"] for e in entries}))
        self.assertEqual(set(inventory(self.capture / "run")),
                         {str(Path(e["destination"]).relative_to("run")) for e in entries})
        for entry in entries:
            with self.subTest(path=entry["destination"]):
                target = (self.capture / entry["destination"]).resolve()
                self.assertTrue(target.is_relative_to(self.capture.resolve()))
                self.assertEqual(sha(target), entry["destination_sha256"])
                self.assertEqual(entry["source_sha256"], entry["destination_sha256"])
                for source in [entry["source"], *entry["additional_sources"]]:
                    self.assertEqual(sha(Path(source)), entry["source_sha256"])

    def test_accepted_identity_and_unmodified_base(self):
        identity(self.capture / "run/run.json")
        identity(self.capture / "run/capture-origin/run.json")
        for relative, digest in inventory(BASE).items():
            self.assertEqual(sha(self.capture / "run" / relative), digest, relative)
        self.assertEqual(load(self.capture / "run/bundle/manifest.json")["identity"], BUILD)

    def test_raw_geometry_and_gross_rectangle_oracles(self):
        root = self.capture / "run"
        geometry = load(root / "flow/21-openroad-generatepdn/macro-power-geometry.json")
        macro, = geometry["macros"]
        self.assertEqual((macro["instance"], macro["module"], macro["orientation"]),
                         (INSTANCE, MACRO, "R0"))
        self.assertEqual(geometry["dbu_per_um"], 1000)
        self.assertEqual(macro["footprint_dbu"], [40000, 81000, 276800, 199780])
        lef = (root / f"baseline-inputs/0-{MACRO}.lef").read_text()
        self.assertIn("SIZE 236.8 BY 118.78 ;", lef)
        placed = (root / f"flow/54-odb-cellfrequencytables/{TOP}.def").read_text()
        self.assertIn(f"- {INSTANCE} {MACRO} + FIXED ( 40000 81000 ) N ;", placed)
        native = load(root / "flow/13-openroad-floorplan/or_metrics_out.json")
        core = [Decimal(v) for v in native["design__core__bbox"].split()]
        die = [Decimal(v) for v in native["design__die__bbox"].split()]
        self.assertEqual((core[2]-core[0])*(core[3]-core[1]), Decimal("902417.2416"))
        self.assertEqual((die[2]-die[0])*(die[3]-die[1]), Decimal("916213.9392"))

    def test_sampled_path_raw_oracles_and_units(self):
        flow = self.capture / "run/flow/56-openroad-stapostpnr"
        slow = (flow / CORNERS[1] / "max.rpt").read_text().split("Startpoint:")[1]
        fast = (flow / CORNERS[0] / "min.rpt").read_text().split("Startpoint:")[1]
        for snippet in (f"{INSTANCE}/A_DOUT[11] ({MACRO})", "Endpoint: uo_out[3]",
                        "11.246561   slack (MET)", "7.336773   data arrival time",
                        "18.583334   data required time", "0.004815    0.067838"):
            self.assertIn(snippet, slow)
        for snippet in ("_203_ (rising edge-triggered flip-flop", f"{INSTANCE}/A_ADDR[6] ({MACRO})",
                        "0.223533   slack (MET)", "0.949038   data arrival time",
                        "0.725504   data required time", "0.167545"):
            self.assertIn(snippet, fast)
        # Unit files are copied unchanged, including gzip compression without .gz.
        for corner in CORNERS:
            raw = (flow / corner / f"{TOP}__{corner}.lib").read_bytes()
            if raw.startswith(b"\x1f\x8b"):
                raw = gzip.decompress(raw)
            self.assertIn(b'time_unit', raw)
            self.assertIn(b'capacitive_load_unit', raw)
        fast_log = (flow / CORNERS[0] / "sta.log").read_text()
        self.assertIn("fast_1p32V_m55C.lib", fast_log)
        self.assertIn("define_corners nom_fast_1p32V_m40C", fast_log)
        self.assertFalse((BASE / "flow/56-openroad-stapostpnr").exists())


def verify(capture_dir, receipt_path):
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    before = protected_state()
    CaptureAcceptance.capture = capture_dir.resolve()
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CaptureAcceptance))
    after = protected_state()
    receipt = dict(scope="PT.5b raw capture verification only; no public measurement acceptance",
                   command=sys.argv, script_sha256=sha(Path(__file__)),
                   capture=str(capture_dir), capture_receipt_sha256=sha(capture_dir / "capture.json"),
                   tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   skipped=result.skipped, unittest_output=output.getvalue(),
                   protected_unchanged=before == after,
                   public_acceptance="blocked_pending_integrated_provider_and_handoffs")
    new_json(receipt_path, receipt)
    print(output.getvalue(), end="")
    return 0 if result.wasSuccessful() and before == after else 1


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False) + "\n")


class PublicAcceptance(unittest.TestCase):
    """Only installed ASIC APIs supply measurement parsing and verdicts."""
    commands = []
    mutations = []
    archive_closures = []

    def invoke(self, executable, *args, code=0):
        command = [str(executable), *map(str, args)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                env=dict(os.environ, PATH="/nonexistent/pt5b-no-tools",
                                         TOOLCHAIN="/nonexistent/pt5b"), timeout=120)
        stem = f"{len(self.commands):03d}"
        (self.output / (stem + ".stdout")).write_text(result.stdout)
        (self.output / (stem + ".stderr")).write_text(result.stderr)
        self.commands.append(dict(command=command, exit=result.returncode, expected_exit=code,
                                  stdout=stem + ".stdout", stderr=stem + ".stderr", test=self.id()))
        self.assertEqual(result.returncode, code, (command, result.stdout[:2000], result.stderr))
        return json.loads(result.stdout) if result.returncode == 0 or result.stdout.strip() else None

    def inspect(self, root, code=0, provider=None):
        return self.invoke(provider or self.provider, "resources-inspect", root, "--json", code=code)

    def api(self, operation, path, *args, code=0):
        return self.invoke(self.consumer, operation, path, *args, code=code)

    @staticmethod
    def final(evidence):
        return next(o for o in evidence["observations"] if o["stage"] == "final_physical")

    def fixture(self, source=None):
        temporary = tempfile.TemporaryDirectory(prefix="pt5b-c-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "run"
        shutil.copytree(source or self.raw, root)
        return root

    def record(self, root, label, paths):
        self.mutations.append(dict(label=label, fixture=str(root),
                                   scope="disposable diagnostic; not requalified geometry or STA",
                                   changes=[dict(path=p,
                                       original_sha256=sha(self.raw/p) if (self.raw/p).is_file() else None,
                                       changed_sha256=sha(root/p) if (root/p).is_file() else None)
                                            for p in paths]))

    def rebind(self, root, paths):
        checks = load(root / "physical-checks.json")
        for relative in paths:
            key = relative.removeprefix("flow/")
            if key in checks["artifacts"]:
                checks["artifacts"][key] = sha(root / relative)
            if key.endswith("macro-power-geometry.json"):
                checks["power_geometry_sha256"] = sha(root / relative)
        write_json(root / "physical-checks.json", checks)
        run = load(root / "run.json")
        run["physical_checks_sha256"] = sha(root / "physical-checks.json")
        write_json(root / "run.json", run)

    def refs(self, evidence, root):
        refs = {r["path"]: r["sha256"] for r in evidence["evidence_refs"]}
        self.assertEqual(len(refs), len(evidence["evidence_refs"]))
        for relative, digest in refs.items():
            path = (root / relative).resolve()
            self.assertTrue(path.is_relative_to(root.resolve()))
            self.assertEqual(sha(path), digest)
        def walk(value):
            if isinstance(value, dict):
                if {"path", "sha256", "format", "scope"} <= value.keys():
                    self.assertEqual(refs[value["path"]], value["sha256"])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(evidence)
        return refs

    def checked(self, root):
        evidence = self.inspect(root)
        self.assertEqual(evidence, self.api("inspect", root))
        self.assertEqual(evidence["schema_version"], 2)
        self.assertEqual(evidence["contract"], "hardcaml-asic.resource-evidence")
        self.assertEqual(evidence["provenance"]["run_id"], RUN_ID)
        self.assertEqual(evidence["provenance"]["build_identity"], BUILD)
        self.assertEqual(evidence["provenance"]["run"]["sha256"], sha(root / "run.json"))
        self.assertTrue(all(c["status"] == "pass" for c in evidence["check_outcomes"]))
        self.refs(evidence, root)
        path = self.output / f"evidence-{len(self.commands)}.json"
        new_json(path, evidence)
        self.assertTrue(self.api("validate", path)["valid"])
        self.assertTrue(self.api("verify-sources", path, root)["valid"])
        return evidence

    def test_public_physical_geometry_class_sums_gross_ratios(self):
        for root in (BASE, self.raw):
            with self.subTest(source=str(root)):
                evidence = self.checked(root)
                observation = self.final(evidence)
                row, = observation["resources"]
                geometry = row["geometry"]
                self.assertEqual(geometry["status"], "available")
                instance, = geometry["instances"]
                self.assertEqual(instance, dict(instance=INSTANCE, module=MACRO, orientation="R0",
                    dbu_per_um=1000, origin_dbu=[40000, 81000], bounds_dbu=[40000, 81000, 276800, 199780],
                    width_um=236.8, height_um=118.78, area_um2=28127.104, halo_dbu=2000))
                self.assertAlmostEqual(row["area"]["value"], 28127.104, places=7)
                physical = observation["physical"]
                self.assertEqual(physical["status"], "available")
                expected = dict(macro_footprint_area=28127.104, macro_component_area=28127.104,
                    macro_component_count=1, nonspacer_component_area=4793.6448,
                    nonspacer_component_count=389, spacer_component_area=866655.4176,
                    spacer_component_count=68539, nonspacer_plus_macro_area=32920.7488,
                    all_component_area=899576.1664, native_all_component_area=899576,
                    native_nonspacer_area=4793.64, native_spacer_area=866655, native_macro_area=28127.1)
                for key, value in expected.items():
                    metric = physical["measurements"][key]
                    self.assertAlmostEqual(metric["value"], value, places=7, msg=key)
                    self.assertEqual(metric["unit"], "count" if key.endswith("count") else "um^2")
                    self.assertTrue(metric["evidence_refs"])
                    self.assertIsNone(metric["unavailable_reason"])
                self.assertEqual(physical["floorplan"]["core"]["bounds_um"], [2.88, 3.78, 1286.4, 706.86])
                self.assertEqual(physical["floorplan"]["die"]["bounds_um"], [0, 0, 1289.28, 710.64])
                ratios = physical["ratios"]
                self.assertEqual(len(ratios), 6)
                for ratio in ratios:
                    denominator = 902417.2416 if ratio["name"].endswith("core") else 916213.9392
                    numerator = (899576.1664 if ratio["name"].startswith("all_component") else
                                 32920.7488 if ratio["name"].startswith("nonspacer") else 28127.104)
                    self.assertAlmostEqual(ratio["numerator"]["value"], numerator, places=7)
                    self.assertAlmostEqual(ratio["denominator"]["value"], denominator, places=7)
                    self.assertAlmostEqual(ratio["value"], numerator/denominator, places=12)
                    self.assertEqual(ratio["denominator"]["unit"], "um^2")
                    self.assertIn("gross", ratio["denominator"]["scope"])

    def test_public_sampled_timing_electrical_provenance(self):
        observation = self.final(self.checked(self.raw))
        self.assertEqual(observation["timing_diagnostics"], [])
        row, = observation["resources"]
        timing, electrical = row["timing_links"], row["electrical_links"]
        self.assertEqual(timing["status"], "observed")
        self.assertEqual(timing["coverage"], "sampled_reported_paths_not_exhaustive")
        self.assertEqual(electrical["compliance"], "not_assessed")
        self.assertEqual((len(timing["paths"]), len(electrical["points"])), (186, 372))
        slow, = [p for p in timing["paths"] if p["corner"] == CORNERS[1] and
                 p["path_type"] == "max" and p["provenance"]["first_line"] == 7]
        fast, = [p for p in timing["paths"] if p["corner"] == CORNERS[0] and
                 p["path_type"] == "min" and p["provenance"]["first_line"] == 7]
        for path, values in ((slow, (7.336773, 18.583334, 11.246561)),
                             (fast, (0.949038, 0.725504, 0.223533))):
            self.assertEqual(tuple(path[k] for k in ("arrival", "required", "slack")), values)
            self.assertEqual((path["time_unit"], path["status"]), ("ns", "met"))
        self.assertEqual(slow["data_start"]["name"], INSTANCE + "/A_DOUT[11]")
        self.assertEqual(slow["data_end"]["name"], "uo_out[3]")
        self.assertEqual(slow["data_start"]["slew"], 0.067838)
        self.assertEqual(slow["data_start"]["reported_load"], 0.004815)
        self.assertEqual(fast["data_start"]["name"], "_203_/Q")
        self.assertEqual(fast["data_end"]["name"], INSTANCE + "/A_ADDR[6]")
        self.assertEqual(fast["data_end"]["slew"], 0.167545)
        self.assertIsNone(fast["data_end"]["reported_load"])
        self.assertIsNone(fast["data_end"]["fanout"])
        for path in timing["paths"]:
            provenance = path["provenance"]
            self.assertEqual((provenance["run_id"], provenance["build_identity"], provenance["stage"]),
                             (RUN_ID, BUILD, "final_physical"))
            self.assertEqual(provenance["origin"], "coarse_run_retained_post_pnr_sta")
            self.assertLessEqual(provenance["first_line"], provenance["last_line"])
            lines = (self.raw / provenance["report"]["path"]).read_text().splitlines()
            self.assertTrue(lines[provenance["first_line"]-1].startswith("Startpoint:"))
            self.assertIn("slack (", lines[provenance["last_line"]-1])
            self.assertTrue(any(p["instance"] == INSTANCE and p["role"] == "data"
                                for p in (path["data_start"], path["data_end"])))
            for model in provenance["external_models"]:
                self.assertEqual(model["verification"], "recorded_external_model_not_read")
                if path["corner"] == CORNERS[0]:
                    self.assertIn("fast_1p32V_m55C.lib", model["reference"])
                    self.assertEqual(model["analysis_corner"], CORNERS[0])
        self.assertTrue({"launch_clock", "capture_clock", "data"} <=
                        {p["point"]["role"] for p in electrical["points"]})
        for entry in electrical["points"]:
            self.assertEqual(entry["point"]["instance"], INSTANCE)
            self.assertEqual(entry["point"]["master"], MACRO)
            self.assertEqual((entry["point"]["time_unit"], entry["point"]["capacitance_unit"]), ("ns", "pF"))

    def test_original_snapshot_timing_and_missing_optional_lef(self):
        row, = self.final(self.inspect(BASE))["resources"]
        self.assertEqual(row["timing_links"]["status"], "unavailable")
        self.assertEqual(row["electrical_links"]["status"], "unavailable")
        root = self.fixture()
        relative = "baseline-inputs/1-sg13cmos5l_stdcell.lef"
        (root / relative).unlink()
        self.record(root, "missing_optional_stdcell_lef", [relative])
        final = self.final(self.inspect(root))
        self.assertEqual(final["resources"][0]["geometry"]["status"], "available")
        metric = final["physical"]["measurements"]["nonspacer_component_area"]
        self.assertIsNone(metric["value"])
        self.assertTrue(metric["unavailable_reason"])

    def test_physical_semantic_negatives_after_checker_rebinding(self):
        geo = "flow/21-openroad-generatepdn/macro-power-geometry.json"
        deffile = f"flow/54-odb-cellfrequencytables/{TOP}.def"
        mutations = [
            ("wrong_instance", geo, lambda j: j["macros"][0].update(instance=INSTANCE+"_near")),
            ("wrong_master", geo, lambda j: j["macros"][0].update(module="wrong")),
            ("duplicate_instance", geo, lambda j: j["macros"].append(copy.deepcopy(j["macros"][0]))),
            ("missing_instance", geo, lambda j: j.update(macros=[])),
            ("wrong_scale", geo, lambda j: j.update(dbu_per_um=2000)),
            ("rotated", geo, lambda j: j["macros"][0].update(orientation="R90")),
            ("moved_def", deffile, lambda t: t.replace("FIXED ( 40000 81000 ) N", "FIXED ( 41000 81000 ) N", 1)),
            ("malformed_def", deffile, lambda t: t.replace("END COMPONENTS", "END BROKEN", 1)),
            ("zero_core", "metrics.json", lambda j: j.update(design__core__bbox="2.88 3.78 2.88 706.86")),
            ("native_count_conflict", "metrics.json", lambda j: j.update(design__instance__count__stdcell=390)),
        ]
        for label, relative, mutate in mutations:
            with self.subTest(mutation=label):
                root = self.fixture()
                path = root / relative
                if relative.endswith(".json"):
                    value = load(path)
                    mutate(value)
                    write_json(path, value)
                else:
                    original = path.read_text()
                    changed = mutate(original)
                    self.assertNotEqual(original, changed)
                    path.write_text(changed)
                self.rebind(root, [relative])
                self.record(root, label, [relative, "physical-checks.json", "run.json"])
                evidence = self.inspect(root, 1)
                final = self.final(evidence)
                self.assertEqual(final["physical"]["status"], "invalid")
                self.assertTrue(final["measurement_error"])
                self.assertNotIn("hash mismatch", final["measurement_error"])
                self.assertFalse(self.api("report", root)["accepted"])

    def test_bound_lef_semantic_conflict_and_stale_hash_distinct(self):
        relative = f"baseline-inputs/0-{MACRO}.lef"
        for label, old, new in (("lef_class_conflict", "CLASS BLOCK", "CLASS CORE SPACER"),
                                ("lef_size_conflict", "SIZE 236.8 BY", "SIZE 236.9 BY"),
                                ("lef_nonzero_origin", "ORIGIN 0 0", "ORIGIN 1 0")):
            with self.subTest(mutation=label):
                root = self.fixture()
                path = root / relative
                original_sha = sha(path)
                text = path.read_text()
                self.assertIn(old, text)
                path.write_text(text.replace(old, new, 1))
                preflight = load(root / "preflight.json")
                matches = [r for r in preflight["references"] if r.get("sha256") == original_sha]
                self.assertTrue(matches)
                for r in matches:
                    r["sha256"] = sha(path)
                write_json(root / "preflight.json", preflight)
                self.record(root, label, [relative, "preflight.json"])
                final = self.final(self.inspect(root, 1))
                self.assertEqual(final["physical"]["status"], "invalid")
                self.assertNotIn("hash mismatch", final["measurement_error"])
        root = self.fixture()
        path = root / f"flow/54-odb-cellfrequencytables/{TOP}.def"
        path.write_bytes(path.read_bytes() + b"\n")
        self.record(root, "ordinary_unbound_def_tamper", [str(path.relative_to(root))])
        final = self.final(self.inspect(root, 1))
        self.assertIn("hash mismatch", final["reason"])

    def sampled_fixture(self):
        root = self.fixture()
        producer = root / "flow/56-openroad-stapostpnr"
        config = load(producer / "config.json")
        config["STA_CORNERS"] = [CORNERS[1]]
        write_json(producer / "config.json", config)
        report = producer / CORNERS[1] / "max.rpt"
        original = report.read_text()
        second = original.index("Startpoint:", original.index("Startpoint:")+1)
        report.write_text(original[:second])
        (producer / CORNERS[1] / "min.rpt").unlink()
        self.record(root, "diagnostic_single_original_path", [str(p.relative_to(root)) for p in
                    (producer/"config.json", report, producer/CORNERS[1]/"min.rpt")])
        return root, report

    def test_varied_report_values_and_valid_negative_slack(self):
        root, report = self.sampled_fixture()
        text = report.read_text().replace("18.583334", "6.000000").replace("11.246561", "-1.336773")
        text = text.replace("slack (MET)", "slack (VIOLATED)")
        text = text.replace("0.004815    0.067838", "0.006321    0.081234")
        report.write_text(text)
        self.record(root, "varied_load_slew_negative_slack", [str(report.relative_to(root))])
        evidence = self.inspect(root)
        row = self.final(evidence)["resources"][0]
        path, = row["timing_links"]["paths"]
        self.assertEqual((path["arrival"], path["required"], path["slack"], path["status"]),
                         (7.336773, 6, -1.336773, "violated"))
        self.assertEqual((path["data_start"]["slew"], path["data_start"]["reported_load"]), (0.081234, 0.006321))
        destination = self.output / "negative-slack-observation.json"
        new_json(destination, evidence)
        self.assertTrue(self.api("validate", destination)["valid"])
        self.assertTrue(self.api("verify-sources", destination, root)["valid"])
        # Resource retention still passes. This is measured negative timing, not
        # a fabricated retention failure or new global timing qualification.
        self.assertEqual(self.final(evidence)["status"], "pass")

    def test_timing_semantics_no_clock_or_prefix_attribution(self):
        for label, mutate in (
            ("near_prefix", lambda t: t.replace(INSTANCE, INSTANCE+"_near")),
            ("wrong_master", lambda t: t.replace(MACRO, "WRONG_MASTER")),
            ("wrong_data_pin", lambda t: t.replace("A_DOUT[11]", "A_CLK")),
            ("truncated", lambda t: t[:t.index("data required time")]),
            ("nonfinite_slew", lambda t: t.replace("0.067838", "     nan")),
        ):
            with self.subTest(mutation=label):
                root, report = self.sampled_fixture()
                report.write_text(mutate(report.read_text()))
                self.record(root, label, [str(report.relative_to(root))])
                final = self.final(self.inspect(root))
                row = final["resources"][0]
                self.assertEqual(row["timing_links"]["status"], "unavailable")
                self.assertEqual(row["electrical_links"]["status"], "unavailable")
        for label in ("missing_units", "conflicting_units", "wrong_log_corner", "wrong_input_netlist", "wrong_producer", "wrong_run"):
            with self.subTest(mutation=label):
                root, report = self.sampled_fixture()
                producer = root / "flow/56-openroad-stapostpnr"
                corner = producer / CORNERS[1]
                if label.endswith("units"):
                    path = corner / f"{TOP}__{CORNERS[1]}.lib"
                    path.write_text('library(diagnostic) { time_unit : "1ns"; ' +
                                    ('time_unit : "1ps"; capacitive_load_unit (1,pF);' if label == "conflicting_units" else '') + ' }\n')
                elif label == "wrong_log_corner":
                    path = corner / "sta.log"
                    path.write_text(path.read_text().replace("define_corners " + CORNERS[1], "define_corners unrelated"))
                elif label == "wrong_input_netlist":
                    path = root / f"flow/53-openroad-fillinsertion/{TOP}.nl.v"
                    path.write_bytes(path.read_bytes() + b"\n")
                elif label == "wrong_run":
                    path = root / "run.json"
                    value = load(path)
                    value["run_id"] = "different_run"
                    write_json(path, value)
                else:
                    path = producer / "config.json"
                    value = load(path)
                    value["meta"]["step"] = "OpenROAD.STAPrePNR"
                    write_json(path, value)
                self.record(root, label, [str(path.relative_to(root))])
                # Optional unsupported STA must not turn into fabricated links.
                final = self.final(self.inspect(root, 0 if label.endswith("units") else 1))
                self.assertEqual(final["resources"][0]["timing_links"]["status"], "unavailable")
                self.assertTrue(final["timing_diagnostics"])
                if not label.endswith("units"):
                    self.assertEqual(final["status"], "fail")
                    self.assertTrue(final["measurement_error"])

    def test_review_primary_arrival_cannot_promote_capture_clock_to_data(self):
        for remove_endpoint in (False, True):
            with self.subTest(remove_endpoint=remove_endpoint):
                root, _ = self.sampled_fixture()
                relative = f"flow/56-openroad-stapostpnr/{CORNERS[1]}/min.rpt"
                original = (self.raw / relative).read_text()
                second = original.index("Startpoint:", original.index("Startpoint:")+1)
                lines = original[:second].splitlines(keepends=True)
                primary = next(i for i, line in enumerate(lines) if "data arrival time" in line)
                if remove_endpoint:
                    endpoint = max(i for i, line in enumerate(lines[:primary]) if INSTANCE+"/" in line)
                    self.assertNotIn("/A_CLK ", lines[endpoint])
                    lines[endpoint] = ""
                lines[primary] = ""
                (root / relative).write_text("".join(lines))
                self.record(root, "review_missing_primary_arrival_endpoint_"+str(remove_endpoint), [relative])
                evidence = self.inspect(root)
                final = self.final(evidence)
                row, = final["resources"]
                paths = row["timing_links"]["paths"]
                self.assertEqual(len(paths), 1)
                self.assertEqual(paths[0]["path_type"], "max")
                self.assertTrue(any("min.rpt" in d for d in final["timing_diagnostics"]))
                points = row["electrical_links"]["points"]
                self.assertEqual(len(points), 2)
                self.assertFalse(any(p["point"]["pin"] == "A_CLK" and p["point"]["role"] == "data" for p in points))
                destination = self.output / ("primary-arrival-"+str(remove_endpoint)+".json")
                new_json(destination, evidence)
                self.assertTrue(self.api("verify-sources", destination, root)["valid"])

    def test_review_nested_unit_spoof_and_partial_report_diagnostics(self):
        root, _ = self.sampled_fixture()
        relative = f"flow/56-openroad-stapostpnr/{CORNERS[1]}/{TOP}__{CORNERS[1]}.lib"
        (root / relative).write_text('library(nested_spoof) { cell(inner) { time_unit : "1ns"; capacitive_load_unit (1,pF); } }\n')
        self.record(root, "review_nested_only_unit_spoof", [relative])
        final = self.final(self.inspect(root))
        self.assertEqual(final["resources"][0]["timing_links"]["status"], "unavailable")
        self.assertEqual(final["resources"][0]["electrical_links"]["status"], "unavailable")
        self.assertTrue(final["timing_diagnostics"])
        for label, content in (("empty", b""), ("garbage", b"not an STA report\n"),
                               ("gzip", gzip.compress(b"not a supported text report\n", mtime=0))):
            with self.subTest(report=label):
                root, _ = self.sampled_fixture()
                relative = f"flow/56-openroad-stapostpnr/{CORNERS[1]}/min.rpt"
                (root / relative).write_bytes(content)
                self.record(root, "review_partial_"+label+"_min_report", [relative])
                evidence = self.inspect(root)
                final = self.final(evidence)
                row = final["resources"][0]
                path, = row["timing_links"]["paths"]
                self.assertEqual(path["path_type"], "max")
                self.assertEqual(len(row["electrical_links"]["points"]), 2)
                self.assertTrue(any("min.rpt" in d for d in final["timing_diagnostics"]))
                destination = self.output / ("partial-"+label+".json")
                new_json(destination, evidence)
                self.assertTrue(self.api("verify-sources", destination, root)["valid"])

    def test_review_partial_lef_native_contradictions(self):
        for label in ("no_macro_lef_wrong_stdcell_area", "no_stdcell_lef_wrong_macro_area"):
            with self.subTest(mutation=label):
                root = self.fixture()
                if label.startswith("no_macro"):
                    relative = f"baseline-inputs/0-{MACRO}.lef"
                    metric, value = "design__instance__area__stdcell", 4000
                else:
                    relative = "baseline-inputs/1-sg13cmos5l_stdcell.lef"
                    metric, value = "design__instance__area__macros", 20000
                (root / relative).unlink()
                native = load(root / "metrics.json")
                native[metric] = value
                write_json(root / "metrics.json", native)
                self.rebind(root, [])
                self.record(root, label, [relative, "metrics.json", "physical-checks.json", "run.json"])
                evidence = self.inspect(root, 1)
                final = self.final(evidence)
                self.assertEqual(final["physical"]["status"], "invalid")
                self.assertTrue(final["measurement_error"])
                self.assertNotIn("hash mismatch", final["measurement_error"])
                destination = self.output / (label+".json")
                new_json(destination, evidence)
                # A truthful failed observation remains source-replayable.
                self.assertTrue(self.api("verify-sources", destination, root)["valid"])

    def test_review_lef_scope_and_def_terminator_semantics(self):
        relative = f"baseline-inputs/0-{MACRO}.lef"
        for label, body in (
            ("post_pin_duplicate_size", "PIN C_DIAGNOSTIC\n DIRECTION INPUT ;\nEND C_DIAGNOSTIC\n SIZE 236.8 BY 118.78 ;\n"),
            ("unclosed_pin", "PIN C_DIAGNOSTIC\n DIRECTION INPUT ;\n"),
            ("mismatched_port", "PIN C_DIAGNOSTIC\n PORT\n LAYER Metal1 ;\n END C_DIAGNOSTIC\n"),
        ):
            with self.subTest(mutation=label):
                root = self.fixture()
                path = root / relative
                old_digest = sha(path)
                text = path.read_text()
                self.assertIn("  SYMMETRY X Y R90 ;", text)
                # Insert immediately after direct attributes, before real pins.
                path.write_text(text.replace("  SYMMETRY X Y R90 ;", "  SYMMETRY X Y R90 ;\n"+body, 1))
                preflight = load(root / "preflight.json")
                matches = [r for r in preflight["references"] if r.get("sha256") == old_digest]
                self.assertTrue(matches)
                for r in matches:
                    r["sha256"] = sha(path)
                write_json(root / "preflight.json", preflight)
                self.rebind(root, [])
                self.record(root, "review_"+label, [relative, "preflight.json", "physical-checks.json", "run.json"])
                final = self.final(self.inspect(root, 1))
                self.assertEqual(final["physical"]["status"], "invalid")
                self.assertNotIn("hash mismatch", final["measurement_error"])
        root = self.fixture()
        relative = f"flow/54-odb-cellfrequencytables/{TOP}.def"
        path = root / relative
        raw = path.read_text()
        self.assertIn("END COMPONENTS", raw)
        path.write_text(raw.replace("END COMPONENTS", "END COMPONENTS_WRONG", 1))
        self.rebind(root, [relative])
        self.record(root, "review_def_terminator_prefix", [relative, "physical-checks.json", "run.json"])
        final = self.final(self.inspect(root, 1))
        self.assertEqual(final["physical"]["status"], "invalid")
        self.assertNotIn("hash mismatch", final["measurement_error"])

    def staged(self):
        root = self.fixture()
        shutil.copytree(root / "bundle", root / "project")
        shutil.copytree(root / "flow", root / "project/runs/asic")
        mapping = [("metrics.json", "project/runs/asic/final/metrics.json"),
                   ("metrics.csv", "project/runs/asic/final/metrics.csv"),
                   ("final.gds", f"project/runs/asic/final/gds/{TOP}.gds"),
                   ("runtime/physical-runtime.py", "project/physical-runtime.py"),
                   ("runtime/macro-flow.py", "project/macro-flow.py"),
                   ("mapped.json", f"project/runs/asic/06-yosys-synthesis/{TOP}.nl.v.json")]
        for source, destination in mapping:
            target = root / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / source, target)
        record = load(root / "run.json")
        record["bundle"] = str(root / "project")
        write_json(root / "run.json", record)
        self.mutations.append(dict(label="disposable_portable_archive_layout", fixture=str(root),
            copies=[["bundle/", "project/"], ["flow/", "project/runs/asic/"], *mapping],
            scope="relocation only; no fabricated producing run", run_sha256=sha(root/"run.json")))
        return root

    def archive(self, root, evidence, label):
        refs = self.refs(evidence, root)
        self.assertTrue(refs.keys() <= set(self.api("archive-sources", root)))
        destination = self.output / (label + "-archive")
        self.invoke(self.provider, "archive", root, "--output", destination, "--json")
        with tarfile.open(destination / "reports.tar.gz") as stream:
            self.assertTrue(refs.keys() <= set(stream.getnames()))
            for name, digest in refs.items():
                member = stream.extractfile(name)
                self.assertIsNotNone(member)
                self.assertEqual(hashlib.sha256(member.read()).hexdigest(), digest, name)
        self.archive_closures.append(dict(label=label, refs=refs,
            reports_sha256=sha(destination/"reports.tar.gz"), all_advertised_bytes_verified=True))

    def test_collection_report_archive_and_stale_source_closure(self):
        original_results = sha(self.raw / "results.json")
        direct = self.inspect(self.raw)
        report = self.api("report", self.raw)
        self.assertTrue(report["accepted"], report["problems"])
        self.assertEqual(report["results"]["resource_evidence"], direct)
        self.assertEqual(sha(self.raw / "results.json"), original_results)
        root = self.staged()
        evidence = self.inspect(root)
        collected = self.api("collect", root)
        self.assertEqual(collected["resource_evidence"], evidence)
        self.assertTrue({r["path"] for r in evidence["evidence_refs"]} <= set(collected["raw_artifacts"]))
        stored = load(root / "results.json")
        stored["resource_evidence"] = evidence
        write_json(root / "results.json", stored)
        stored_sha = sha(root / "results.json")
        refreshed = self.api("report", root)
        self.assertTrue(refreshed["accepted"], refreshed["problems"])
        self.assertEqual(refreshed["results"]["resource_evidence"], evidence)
        self.assertEqual(sha(root / "results.json"), stored_sha)
        self.archive(root, evidence, "schema2")
        path = self.output / "stale-source-evidence.json"
        new_json(path, evidence)
        source = root / f"project/runs/asic/56-openroad-stapostpnr/{CORNERS[1]}/max.rpt"
        source.write_bytes(source.read_bytes() + b"\n")
        self.assertFalse(self.api("verify-sources", path, root)["valid"])
        self.assertFalse(self.api("report", root)["accepted"])
        self.api("archive-sources", root, code=2)

    def test_genuine_schema1_compatibility_replay_report_archive(self):
        historical = ROOT / "acceptance/resource-realization/installed-final/037.stdout"
        self.assertEqual(load(historical)["schema_version"], 1)
        self.assertTrue(self.api("validate", historical)["valid"])
        self.assertTrue(self.api("verify-sources", historical, BASE)["valid"])
        root = self.staged()
        # The actual frozen PT.5 provider emits old semantics. No local downgrade
        # algorithm fabricates a schema-1 assertion from schema-2 fields.
        legacy = self.inspect(root, provider=self.schema1_provider)
        self.assertEqual(legacy["schema_version"], 1)
        path = self.output / "genuine-schema1.json"
        new_json(path, legacy)
        self.assertTrue(self.api("validate", path)["valid"])
        self.assertTrue(self.api("verify-sources", path, root)["valid"])
        stored = load(root / "results.json")
        stored["resource_evidence"] = legacy
        write_json(root / "results.json", stored)
        before = sha(root / "results.json")
        report = self.api("report", root)
        self.assertTrue(report["accepted"], report["problems"])
        self.assertEqual(report["results"]["resource_evidence"]["schema_version"], 2)
        self.assertEqual(self.final(legacy)["resources"][0]["timing_links"]["status"], "unavailable")
        self.assertEqual(self.final(report["results"]["resource_evidence"])["resources"][0]["timing_links"]["status"], "observed")
        self.assertEqual(sha(root / "results.json"), before)
        self.archive(root, legacy, "schema1")

    def test_strict_validation_and_coherent_forgery_source_replay(self):
        baseline = self.inspect(self.raw)
        for label, mutate in (
            ("false_geometry", lambda e: self.final(e)["resources"][0]["geometry"]["instances"][0].update(instance=INSTANCE+"_near")),
            ("wrong_gross_unit", lambda e: self.final(e)["physical"]["floorplan"]["core"]["area"].update(unit="ns")),
            ("false_compliance", lambda e: self.final(e)["resources"][0]["electrical_links"].update(compliance="pass")),
            ("wrong_timing_stage", lambda e: self.final(e)["resources"][0]["timing_links"]["paths"][0]["provenance"].update(stage="synthesis")),
        ):
            with self.subTest(mutation=label):
                evidence = copy.deepcopy(baseline)
                mutate(evidence)
                path = self.output / (label + ".json")
                new_json(path, evidence)
                self.assertFalse(self.api("validate", path)["valid"])
        root = self.staged()
        forged = self.inspect(root)
        path = self.final(forged)["resources"][0]["timing_links"]["paths"][0]
        path["required"] += 1
        path["slack"] += 1
        destination = self.output / "coherent-timing-forgery.json"
        new_json(destination, forged)
        self.assertTrue(self.api("validate", destination)["valid"])
        self.assertFalse(self.api("verify-sources", destination, root)["valid"])
        stored = load(root / "results.json")
        stored["resource_evidence"] = forged
        write_json(root / "results.json", stored)
        self.assertFalse(self.api("report", root)["accepted"])
        self.api("archive-sources", root, code=2)
        archive = self.output / "forgery-must-not-publish"
        self.invoke(self.provider, "archive", root, "--output", archive, "--json", code=2)
        self.assertFalse((archive / "reports.tar.gz").exists())

    def test_varied_gross_core_and_coherent_physical_forgery(self):
        # Change real retained metric bytes in a diagnostic copy. New arithmetic
        # must follow those bytes rather than the historical expected constants.
        root = self.fixture()
        native = load(root / "metrics.json")
        bounds = [3.84, 3.78, 1286.4, 706.86]
        area = float((Decimal("1286.4")-Decimal("3.84")) * (Decimal("706.86")-Decimal("3.78")))
        native["design__core__bbox"] = " ".join(map(str, bounds))
        native["design__core__area"] = float(f"{area:.6g}")
        write_json(root / "metrics.json", native)
        self.record(root, "varied_gross_core_rectangle", ["metrics.json"])
        evidence = self.inspect(root)
        physical = self.final(evidence)["physical"]
        self.assertEqual(physical["floorplan"]["core"]["bounds_um"], bounds)
        self.assertAlmostEqual(physical["floorplan"]["core"]["area"]["value"], area, places=7)
        for ratio in physical["ratios"]:
            if ratio["name"].endswith("core"):
                self.assertAlmostEqual(ratio["value"], ratio["numerator"]["value"]/area, places=12)
        # Same coherent change only to structured assertions, over unchanged
        # original sources: shape-valid is insufficient without source replay.
        root = self.fixture()
        forged = self.inspect(root)
        physical = self.final(forged)["physical"]
        physical["floorplan"]["core"]["bounds_um"] = bounds
        physical["floorplan"]["core"]["area"]["value"] = area
        for ratio in physical["ratios"]:
            if ratio["name"].endswith("core"):
                ratio["denominator"]["value"] = area
                ratio["value"] = ratio["numerator"]["value"]/area
        path = self.output / "coherent-physical-forgery.json"
        new_json(path, forged)
        self.assertTrue(self.api("validate", path)["valid"])
        self.assertFalse(self.api("verify-sources", path, root)["valid"])


def public_acceptance(args):
    output = args.output_dir.resolve()
    if output.exists() or not output.is_relative_to(ACCEPTANCE):
        raise ValueError("public output must be a new directory beneath acceptance/resource-measurements")
    output.mkdir()
    shutil.copyfile(Path(__file__), output / "tested-script.py")
    before = protected_state()
    earlier_paths = [ACCEPTANCE/"installed-02", ACCEPTANCE/"closeout-01.json",
                     ACCEPTANCE/"accepted-live-01/capture.json"]
    def earlier_inventory():
        return {str(p.relative_to(ROOT)): sha(p) for root in earlier_paths
                for p in (files(root) if root.is_dir() else [root])}
    earlier_before = earlier_inventory()
    raw_before = inventory(args.run_dir)
    PublicAcceptance.output = output
    PublicAcceptance.raw = args.run_dir.resolve(strict=True)
    for field in ("provider", "consumer", "schema1_provider"):
        setattr(PublicAcceptance, field, getattr(args, field).resolve(strict=True))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(PublicAcceptance))
    after = protected_state()
    raw_after = inventory(args.run_dir)
    earlier_after = earlier_inventory()
    preserved = before == after and raw_before == raw_after and earlier_before == earlier_after
    receipt = dict(scope="PT.5b C independent installed public-provider acceptance", command=sys.orig_argv,
        script_sha256=sha(Path(__file__)), python_version=sys.version,
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=result.skipped,
        unittest_output=stream.getvalue(), protected_before=before, protected_after=after,
        raw_before=raw_before, raw_after=raw_after, preserved=preserved,
        earlier_acceptance_before=earlier_before, earlier_acceptance_after=earlier_after,
        commands=PublicAcceptance.commands, mutations=PublicAcceptance.mutations,
        archive_closures=PublicAcceptance.archive_closures,
        executable_ids={field: dict(path=str(getattr(PublicAcceptance, field)), sha256=sha(getattr(PublicAcceptance, field)))
                        for field in ("provider", "consumer", "schema1_provider")},
        provider_receipt=load(PublicAcceptance.provider.parent.parent/"receipt.json"),
        public_acceptance="passed" if result.wasSuccessful() and preserved else "failed",
        limitations=["sampled reported timing, not exhaustive resource coverage or electrical compliance",
                     "no new EDA, timed-model conformance, IR/EM, resource power or flop ownership",
                     "external model references are historical recorded bindings, not retained verified model bytes",
                     "disposable rebound semantic fixtures are not requalified geometry or STA",
                     "historical tool authentication and P6 source stamp unavailable"])
    new_json(output / "receipt.json", receipt)
    print(stream.getvalue(), end="")
    print("Protected evidence/configuration/pointers preserved:", preserved)
    return 0 if result.wasSuccessful() and preserved else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--capture", type=Path, help="new raw capture directory")
    modes.add_argument("--verify-capture", type=Path)
    modes.add_argument("--public", action="store_true")
    parser.add_argument("--receipt", type=Path, help="new raw verification receipt")
    parser.add_argument("--run-dir", type=Path, default=ACCEPTANCE/"accepted-live-01/run")
    parser.add_argument("--provider", type=Path)
    parser.add_argument("--consumer", type=Path)
    parser.add_argument("--schema1-provider", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.capture:
        print(capture(args.capture))
        return 0
    if args.public:
        if not all((args.provider, args.consumer, args.schema1_provider, args.output_dir)):
            parser.error("--public requires --provider --consumer --schema1-provider --output-dir")
        return public_acceptance(args)
    if args.receipt is None:
        parser.error("--verify-capture requires --receipt")
    return verify(args.verify_capture, args.receipt)


if __name__ == "__main__":
    raise SystemExit(main())
