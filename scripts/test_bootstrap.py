"""Exercise real checkout setup with disposable installed-provider and build tools."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


BOOTSTRAP = Path(__file__).resolve().parent.parent / "bootstrap.sh"
sys.path.insert(0, str(BOOTSTRAP.parent / "integration/workbench"))
from wire import parse

TARGET = "asics/fifo_demo/cli/project.exe"
ASIC = "hardcaml-workbench-asic.sexp"
PREP = "hardcaml-workbench-preparation.sexp"
RECORDER = r'''
import json
import os
from pathlib import Path
import signal
import sys

Path(os.environ["RECORD"]).write_text(json.dumps({
    "argv": sys.argv[1:], "cwd": os.getcwd(), "pid": os.getpid(),
    "env": {key: os.environ.get(key) for key in
            ("TOOLCHAIN", "TT", "FLOW_PY", "PATH", "SENTINEL")},
}))
if os.environ.get("WAIT_FOR_SIGNAL"):
    signal.pause()
sys.exit(int(os.environ.get("EXIT_CODE", "0")))
'''


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bootstrap's fixture ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "consumer's project"
        self.project.mkdir()
        self.wrapper = self.project / "bootstrap.sh"
        shutil.copy2(BOOTSTRAP, self.wrapper)
        for source in ("scripts/configure-synthesis.py", "integration/workbench/wire.py",
                       "integration/workbench/config_location.py"):
            dest = self.project / source
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BOOTSTRAP.parent / source, dest)
        self.caller = self.root / "caller's cwd"
        self.caller.mkdir()
        self.bin = self.root / "installed bin"
        self.bin.mkdir()
        # A short shebang path also works when the test interpreter lives in a
        # prefix containing spaces. No provider code or toolchain is invoked.
        self.python = self.root / "python"
        self.python.symlink_to(sys.executable)
        self.recorder = self.bin / "hardcaml-asic-flow"
        self.recorder.write_text("#!/bin/bash\nexec " + self.shell_quote(str(self.python))
                                 + " -c " + self.shell_quote(RECORDER) + ' "$@"\n')
        self.recorder.chmod(0o755)
        self.record = self.root / "record.json"
        (self.bin / "python3").symlink_to(sys.executable)
        opam = self.bin / "opam"
        opam.write_text('#!/bin/bash\n[[ $1 == exec && $2 == -- ]] || exit 64\n'
                        'shift 2\nexec "$@"\n')
        opam.chmod(0o755)
        dune = self.bin / "dune"
        dune.write_text("#!/bin/bash\nexec python3 -c " + self.shell_quote(r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if not os.environ.get("ALREADY_PROVISIONED"):
    assert Path(os.environ["RECORD"]).is_file(), "build before provision"
Path(os.environ["BUILD_RECORD"]).write_text(json.dumps(args))
if os.environ.get("BUILD_FAIL"):
    sys.exit(42)
target = Path(args[args.index("--root") + 1]) / "_build/default" / args[-1]
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("#!/bin/sh\nexit 0\n")
target.chmod(0o755)
''') + ' "$@"\n')
        dune.chmod(0o755)
        self.build_record = self.root / "build.json"
        self.env = {"PATH": str(self.bin), "RECORD": str(self.record),
                    "BUILD_RECORD": str(self.build_record),
                    "SENTINEL": "owner's environment", "TT": "unchanged tt",
                    "FLOW_PY": "unchanged python"}

    @staticmethod
    def shell_quote(text):
        return "'" + text.replace("'", "'\"'\"'") + "'"

    def invoke(self, *args, cwd=None, command=None):
        return subprocess.run([str(command or self.wrapper), *args],
                              cwd=cwd or self.caller, env=self.env,
                              capture_output=True, text=True, timeout=10)

    def recorded(self):
        return json.loads(self.record.read_text())

    def assert_forwarded(self, args, root=None):
        result = self.invoke(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.recorded()
        self.assertEqual(record["argv"], ["provision", "--toolchain",
                         str(root if root is not None else self.project / "_flow_tools"), *args])
        self.assertEqual(record["cwd"], str(self.caller))
        self.assertEqual(record["env"], {key: self.env.get(key) for key in record["env"]})
        self.assertFalse((self.project / "_flow_tools").exists())

    def test_no_arguments_provisions_then_configures_fifo_from_any_cwd(self):
        self.assertTrue(os.access(BOOTSTRAP, os.X_OK))
        self.assert_forwarded([])
        argv = json.loads(self.build_record.read_text())
        self.assertEqual(argv[0], "build")
        self.assertIn(TARGET, argv)
        configs = self.project / ".workbench"
        fields = dict(parse((configs / ASIC).read_text()))
        self.assertEqual(fields["project_executable"], str(self.project / "_build/default" / TARGET))
        self.assertEqual(fields["toolchain"], str(self.project / "_flow_tools"))
        self.assertEqual(dict(parse((configs / PREP).read_text()))["build_target"], TARGET)
        self.assertFalse((self.project / ASIC).exists())
        self.assertFalse((self.project / PREP).exists())
        result = self.invoke(cwd=self.project, command="./bootstrap.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded()["argv"],
                         ["provision", "--toolchain", str(self.project / "_flow_tools")])
        self.assertEqual(self.recorded()["cwd"], str(self.project))

    def test_setup_existing_tools_without_reprovisioning(self):
        tools = self.project / "_flow_tools"
        tools.mkdir()
        self.env["ALREADY_PROVISIONED"] = "1"
        result = self.invoke("-B", str(self.project / "scripts/configure-synthesis.py"),
                             command=self.bin / "python3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.build_record.is_file())
        self.assertFalse(self.record.exists())
        config = dict(parse((self.project / ".workbench" / ASIC).read_text()))
        self.assertEqual(config["toolchain"], str(tools))

    def test_relative_script_path_and_cdpath(self):
        self.env["CDPATH"] = str(self.root)
        self.assert_forwarded(["--check"])
        result = self.invoke("--help", command="../consumer's project/bootstrap.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded()["argv"],
                         ["provision", "--toolchain", str(self.project / "_flow_tools"), "--help"])
        self.assertEqual(self.recorded()["cwd"], str(self.caller))

    def test_environment_root_absolute_and_relative(self):
        for root in (str(self.root / "owner's tools"), "relative owner's tools"):
            with self.subTest(root=root):
                self.env["TOOLCHAIN"] = root
                self.assert_forwarded(["--check"], root=root)

    def test_empty_environment_uses_default(self):
        self.env["TOOLCHAIN"] = ""
        self.assert_forwarded([])

    def test_explicit_root_follows_environment_for_provider_precedence(self):
        self.env["TOOLCHAIN"] = "environment's tools"
        for root in (str(self.root / "explicit owner's tools"), "relative owner's tools"):
            with self.subTest(root=root):
                self.assert_forwarded(["--toolchain", root, "--check"],
                                      root=self.env["TOOLCHAIN"])
        self.assert_forwarded(["--toolchain=relative owner's tools"],
                              root=self.env["TOOLCHAIN"])

    def test_explicit_root_follows_default(self):
        self.assert_forwarded(["--toolchain", "caller's tools"])
        fields = dict(parse((self.project / ".workbench" / ASIC).read_text()))
        tools = self.caller / "caller's tools"
        self.assertEqual(fields["toolchain"], str(tools))
        for key, relative in (("pdk_root", "pdk"), ("support_tools", "tt"),
                              ("python", ".venv/bin/python")):
            self.assertEqual(fields[key], [str(tools / relative)])

    def test_mixed_existing_locations_preserved_without_duplicate_configs(self):
        root_config = self.project / ASIC
        root_config.write_bytes(b"owner's root selection\n")
        self.assert_forwarded([])
        local = self.project / ".workbench"
        self.assertFalse((local / ASIC).exists())
        self.assertTrue((local / PREP).is_file())
        (local / PREP).write_bytes(b"owner's preparation\n")
        self.assert_forwarded([])
        self.assertEqual(root_config.read_bytes(), b"owner's root selection\n")
        self.assertEqual((local / PREP).read_bytes(), b"owner's preparation\n")
        self.assertFalse((self.project / PREP).exists())
        self.assertFalse(self.build_record.exists())

    def test_conflicting_copies_refused_before_build_or_publication(self):
        local = self.project / ".workbench"
        local.mkdir()
        for directory in (local, self.project):
            (directory / PREP).write_text(str(directory))
        self.assertNotEqual(self.invoke().returncode, 0)
        for directory in (local, self.project):
            self.assertEqual((directory / PREP).read_text(), str(directory))
            self.assertFalse((directory / ASIC).exists())
        self.assertFalse(self.build_record.exists())

    def test_failed_provision_or_build_never_publishes_configs(self):
        self.env["EXIT_CODE"] = "37"
        self.assertEqual(self.invoke().returncode, 37)
        self.assertFalse(self.build_record.exists())
        self.assertFalse((self.project / ".workbench").exists())
        del self.env["EXIT_CODE"]
        self.env["BUILD_FAIL"] = "1"
        self.assertEqual(self.invoke().returncode, 42)
        self.assertFalse((self.project / ".workbench").exists())

    def test_provider_modes_and_base_python_forwarded_verbatim(self):
        self.assert_forwarded(["--check", "--offline", "--no-container",
                               "--python", "relative python's prefix/bin/python3.11"])

    def test_check_preserves_fresh_and_configured_checkout(self):
        def snapshot():
            return {p.relative_to(self.project): (p.stat().st_mode, p.stat().st_mtime_ns,
                                                  p.read_bytes() if p.is_file() else None)
                    for p in [self.project, *self.project.rglob("*")]}

        for configured in (False, True):
            with self.subTest(configured=configured):
                if configured:
                    config = self.project / ".workbench/hardcaml-workbench-asic.sexp"
                    config.parent.mkdir()
                    config.write_text("owner's ASIC selection\n")
                    (self.project / "dune-workspace").write_text("owner's workspace\n")
                for status in (0, 1):
                    before = snapshot()
                    self.env["EXIT_CODE"] = str(status)
                    result = self.invoke("--check")
                    self.assertEqual(result.returncode, status, result.stderr)
                    self.assertEqual(self.recorded()["argv"], ["provision", "--toolchain",
                                     str(self.project / "_flow_tools"), "--check"])
                    self.assertEqual(snapshot(), before)
                    self.assertFalse(self.build_record.exists())

    def test_help_is_delegated(self):
        self.assert_forwarded(["--help"])

    def test_absent_provider_is_actionable_and_writes_nothing(self):
        self.recorder.unlink()
        self.env["TOOLCHAIN"] = str(self.root / "must not create")
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        result = self.invoke("--toolchain", "also must not create")
        self.assertEqual(result.returncode, 127)
        self.assertEqual(result.stdout, "")
        for text in ("hardcaml-asic-flow", "PATH", "opam", "activate.sh", "README.md"):
            self.assertIn(text, result.stderr)
        self.assertEqual(before, sorted(str(p.relative_to(self.root))
                                        for p in self.root.rglob("*")))

    def test_exit_status_is_preserved(self):
        for status in (2, 37, 127):
            with self.subTest(status=status):
                self.env["EXIT_CODE"] = str(status)
                self.assertEqual(self.invoke("--check").returncode, status)

    def test_exec_preserves_pid_and_signal_status(self):
        self.env["WAIT_FOR_SIGNAL"] = "1"
        process = subprocess.Popen([str(self.wrapper), "--check"],
                                   cwd=self.caller, env=self.env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    record = self.recorded()
                    break
                except (FileNotFoundError, json.JSONDecodeError):
                    if process.poll() is not None:
                        self.fail("recorder exited before recording")
                    time.sleep(0.01)
            else:
                self.fail("recorder did not start")
            self.assertEqual(record["pid"], process.pid)
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=10), -signal.SIGTERM)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
