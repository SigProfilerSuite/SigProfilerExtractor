"""The clickable uninstaller (uninstall_web.sh, which uninstall_web.command runs),
on a throwaway copy: never on the real environment."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the POSIX uninstaller (Windows uses uninstall_web.ps1)")

SCRIPT = Path(__file__).resolve().parents[2] / "uninstall_web.sh"


@pytest.fixture
def install(tmp_path):
    """A folder laid out as after a launch: the script, an environment with a genome, run records."""
    here = tmp_path / "SigProfilerExtractor"
    here.mkdir()
    shutil.copy(SCRIPT, here / "uninstall_web.sh")
    venv = here / ".venv-dashboard"
    (venv / "lib" / "python3.13" / "site-packages" / "SigProfilerMatrixGenerator" / "references"
     / "chromosomes" / "tsb" / "GRCh37").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    cache = tmp_path / "cache"
    state = cache / "sigprofilerextractor"
    (state / "jobs" / "0123456789ab").mkdir(parents=True)
    (state / "dashboard.lock").write_text("")
    (state / "unrelated.txt").write_text("not the Workbench's")
    results = tmp_path / "home" / "SigProfilerExtractor_results" / "run"
    results.mkdir(parents=True)
    (here / "README.md").write_text("kept")
    return {"here": here, "venv": venv, "state": state, "cache": cache, "home": tmp_path / "home", "results": results}


def _run(install, answer=None, args=()):
    env = dict(os.environ, XDG_CACHE_HOME=str(install["cache"]), HOME=str(install["home"]))
    return subprocess.run(["bash", str(install["here"] / "uninstall_web.sh"), *args], input=answer,
                          capture_output=True, text=True, env=env, timeout=60)


def test_it_says_what_it_removes_and_removes_nothing_without_a_yes(install):
    done = _run(install, answer="n\n")
    assert done.returncode == 0
    assert str(install["venv"]) in done.stdout
    assert "GRCh37" in done.stdout
    assert "1 run(s)" in done.stdout
    assert "Nothing was removed." in done.stdout
    assert install["venv"].is_dir() and (install["state"] / "jobs").is_dir()


def test_yes_removes_the_environment_and_run_records_only(install):
    done = _run(install, answer="y\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not install["venv"].exists()
    assert not (install["state"] / "jobs").exists() and not (install["state"] / "dashboard.lock").exists()
    assert (install["state"] / "unrelated.txt").is_file()
    assert (install["here"] / "README.md").is_file() and install["results"].is_dir()


def test_yes_flag_needs_no_answer(install):
    done = _run(install, args=("--yes",))
    assert done.returncode == 0
    assert not install["venv"].exists()


def test_it_refuses_while_the_workbench_runs(install):
    # A process whose command line is the environment's python running the Workbench.
    name = f"{install['venv']}/bin/python -m SigProfilerExtractor.web.launcher"
    proc = subprocess.Popen(["bash", "-c", f'exec -a "{name}" sleep 30'])
    try:
        time.sleep(0.3)
        done = _run(install, args=("--yes",))
        assert done.returncode == 1
        assert "still running" in done.stdout
        assert install["venv"].is_dir()
    finally:
        proc.kill()


def test_a_live_pidfile_counts_as_running(install):
    (install["state"] / "dashboard.pid").write_text(f"{os.getpid()}:1234:token")
    done = _run(install, args=("--yes",))
    assert done.returncode == 1 and install["venv"].is_dir()


def test_nothing_to_remove(tmp_path):
    here = tmp_path / "x"
    here.mkdir()
    shutil.copy(SCRIPT, here / "uninstall_web.sh")
    env = dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "cache"))
    done = subprocess.run(["bash", str(here / "uninstall_web.sh")], capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0 and "Nothing to remove" in done.stdout


def test_a_folder_that_is_not_an_environment_is_left_alone(install):
    (install["venv"] / "pyvenv.cfg").unlink()
    _run(install, args=("--yes",))
    assert install["venv"].is_dir()
