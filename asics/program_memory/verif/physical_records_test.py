"""Synthetic receipt fixtures: no simulator, TT tool, checker process or EDA."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "physical"))
from physical_records import inside, installed_runtime, sha, verify_hashes, verify_postcheck, zero


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sram-receipts-", dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "run/checks/check-1"
        self.flow = self.root / "run/project/runs/asic"
        self.generation = self.root / "generation"
        self.run = {"run_id": "fixture-run", "build_identity": "fixture-bundle"}
        self.directory.mkdir(parents=True)
        self.write(self.flow / "final/gds/tt_um_program_memory.gds", "fixture GDS, not geometry evidence")
        self.write(self.flow / "final/nl/tt_um_program_memory.nl.v", "sg13cmos5l_buf_1 buffer (.A(a), .X(x));")
        source = self.root / "source/vendor.v"
        vendor = "module sg13cmos5l_buf_1(A, X); input A; output X; assign X=A; endmodule"
        self.write(source, vendor)
        self.write(self.directory / "stdcell-vendor.v", vendor)
        functional = "\n`timescale 1ns/1ps\n// Reviewed zero-delay functional view; not SDF/timing evidence.\n\n" + vendor.replace("endmodule", "\nendmodule")
        self.write(self.directory / "stdcell-functional.v", functional)
        helper = "# synthetic fixture helper; never executed\n"
        self.write(self.directory / "physical-runtime.py", helper)
        self.write(self.generation / "lib/hardcaml_asic/flow/hardcaml_asic_flow/physical_runtime.py", helper)
        models = {"scope": "zero_delay_gate_functional", "models": [str(self.directory / "stdcell-functional.v")],
                  "source_hashes": {str(source): sha(source)}, "adaptations": {"sg13cmos5l_buf_1": []},
                  "vendor_sha256": sha(source), "functional_sha256": sha(self.directory / "stdcell-functional.v"),
                  "retained_hashes": {name: sha(self.directory / name) for name in ("stdcell-vendor.v", "stdcell-functional.v")}}
        self.json(self.directory / "replay-models.json", models)
        self.json(self.root / "run/preflight.json", {"references": [{"path": str(source), "sha256": sha(source)}]})
        for name in ("testbench.v", "postcheck.log", "tt/precheck/reports/result.xml"):
            self.write(self.directory / name, "synthetic postcheck fixture\n")
        self.record = {"schema_version": 1, **self.run, "status": "completed",
                       "checks": {"precheck": "pass", "gate_level": "pass"},
                       "tools": {"replay_scope": "zero_delay_gate_functional_not_timing_conformance"},
                       "resource_limits": {"host_cpu_affinity_max": 6, "tool_threads": 6, "container_cpus": 6},
                       "inputs": {"gds_sha256": sha(self.flow / "final/gds/tt_um_program_memory.gds"),
                                  "netlist_sha256": sha(self.flow / "final/nl/tt_um_program_memory.nl.v"),
                                  "testbench_sha256": sha(self.directory / "testbench.v"),
                                  "physical_runtime_sha256": sha(self.directory / "physical-runtime.py")},
                       "artifacts": {name: sha(self.directory / name) for name in
                                     ("stdcell-vendor.v", "stdcell-functional.v", "replay-models.json", "physical-runtime.py")},
                       "processes": [{"stdout": "postcheck.log", "stderr": "postcheck.log"}],
                       "process_results": [{"outcome": "exited", "code_or_ocaml_signal": 0, "succeeded": True}],
                       "commands": [["iverilog", "fixture"], ["vvp", "fixture"], ["precheck.py", "fixture"]],
                       "reports": ["tt/precheck/reports/result.xml"], "logs": ["postcheck.log"]}

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def json(self, path, value):
        self.write(path, json.dumps(value))

    def verify(self, record=None):
        self.json(self.directory / "postcheck.json", self.record if record is None else record)
        return verify_postcheck(self.directory, self.run, self.flow, self.generation, {})

    def test_complete_scoped_receipt(self):
        self.assertEqual(self.verify()["checks"]["gate_level"], "pass")

    def test_wrong_run_or_missing_external_gate(self):
        for key, value in (("run_id", "different"), ("status", "failed"),
                           ("checks", {"precheck": "pass", "gate_level": "pending"})):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.verify({**self.record, key: value})

    def test_changed_final_netlist(self):
        self.write(self.flow / "final/nl/tt_um_program_memory.nl.v", "changed connectivity")
        with self.assertRaisesRegex(RuntimeError, "postcheck input hash"):
            self.verify()

    def test_resealed_noncanonical_model(self):
        path = self.directory / "stdcell-functional.v"
        self.write(path, path.read_text().replace("assign X=A", "assign X=~A"))
        models = json.loads((self.directory / "replay-models.json").read_text())
        models["functional_sha256"] = models["retained_hashes"][path.name] = sha(path)
        self.json(self.directory / "replay-models.json", models)
        for name in (path.name, "replay-models.json"):
            self.record["artifacts"][name] = sha(self.directory / name)
        with self.assertRaisesRegex(RuntimeError, "noncanonical zero-delay"):
            self.verify()

    def test_timeout_or_overbudget(self):
        record = copy.deepcopy(self.record)
        record["process_results"][0]["outcome"] = "timed_out"
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.verify(record)
        record = copy.deepcopy(self.record)
        record["resource_limits"]["container_cpus"] = 20
        with self.assertRaisesRegex(RuntimeError, "worker limits"):
            self.verify(record)

    def test_hash_inventory_and_escape(self):
        path = self.directory / "postcheck.log"
        digest = sha(path)
        self.write(path, "changed")
        with self.assertRaises(RuntimeError):
            verify_hashes(self.directory, {path.name: digest}, {}, "")
        for name in ("../outside", "/etc/passwd"):
            with self.assertRaises(RuntimeError):
                inside(self.directory, name)

    def test_metrics_reject_missing_nan_bool_and_violation(self):
        for metrics in ({}, {"count": float("nan")}, {"count": False}, {"count": 1}):
            with self.assertRaises(RuntimeError):
                zero(metrics, "count")


class MagicPolicyFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generation = Path(__file__).resolve().parents[3] / ".dev/asic-sram/current"
        if not generation.is_dir():
            raise unittest.SkipTest("installed SRAM provider required for pure policy fixtures")
        cls.policy = installed_runtime(generation)

    def setUp(self):
        p = self.policy
        self.plan = {"macros": [{"location_um": [40., 81.], "halo_um": 2., "instance": "hc_resource_7_program"}]}
        self.m2 = (p.M2_OBS_RULE, tuple(map(Decimal, ("39.400", "81.520", "39.460", "202.295"))))
        self.m3 = (p.M3_OBS_RULE, tuple(map(Decimal, ("137.860", "80.540", "157.690", "80.740"))))
        self.findings = [self.m2, self.m3]
        self.controls = {"stock": self.findings[:], "without-Metal2": [self.m3],
                         "without-Metal3": [self.m2], "without-combined": []}

    def test_exact_four_controls(self):
        result = self.policy.validate_obstruction_controls(self.findings, self.controls, self.plan)
        self.assertEqual((result["raw_count"], result["accepted_count"], result["unclassified_count"]), (2, 2, 0))

    def test_missing_shifted_or_unrelated_disappearing_markers(self):
        variants = [dict(self.controls), dict(self.controls), dict(self.controls)]
        del variants[0]["stock"]
        variants[1]["stock"] = [(self.m2[0], tuple(v + Decimal("0.005") for v in self.m2[1])), self.m3]
        variants[2]["without-Metal2"] = []
        for controls in variants:
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                self.policy.validate_obstruction_controls(self.findings, controls, self.plan)

    def test_unknown_rule_and_retained_target(self):
        with self.assertRaises(ValueError):
            self.policy.validate_obstruction_controls([("unknown rule", self.m2[1])], self.controls, self.plan)
        self.controls["without-combined"] = [self.m2]
        with self.assertRaises(ValueError):
            self.policy.validate_obstruction_controls(self.findings, self.controls, self.plan)


if __name__ == "__main__":
    unittest.main()
