"""Create isolated Git provenance from explicitly supplied Dune source inputs."""
import os
from pathlib import Path
import shutil
import subprocess


def fixture(source, destination, inputs):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME="Bundle test", GIT_AUTHOR_EMAIL="bundle@test.invalid",
               GIT_COMMITTER_NAME="Bundle test", GIT_COMMITTER_EMAIL="bundle@test.invalid",
               GIT_AUTHOR_DATE="2026-01-01T00:00:00Z",
               GIT_COMMITTER_DATE="2026-01-01T00:00:00Z", GIT_TERMINAL_PROMPT="0")
    destination.mkdir()
    for name in sorted(set(inputs)):
        relative = Path(name)
        assert not relative.is_absolute() and not {"..", ".git"}.intersection(relative.parts), name
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", destination, "-c", "core.hooksPath=/dev/null",
             "-c", "commit.gpgsign=false", "-c", "init.templateDir=", *args],
            env=env, text=True).strip()

    git("init", "--initial-branch=fixture")
    git("add", ".")
    git("commit", "-m", "baseline")
    assert not git("remote")
    assert not git("status", "--porcelain")
    return env
