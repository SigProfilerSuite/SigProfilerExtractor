"""launch_web.sh picks a Python 3.10 or newer, or says what to install.

Each test runs the real script with a PATH holding only stand-in Pythons
(small scripts that report a chosen version) and the few tools the script
uses, so no real environment is created and nothing is installed.
"""

import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="launch_web.sh is for macOS and Linux")

SCRIPT = Path(__file__).resolve().parents[2] / "launch_web.sh"
TOOLS = ("dirname", "rm", "uname", "mkdir", "cp")

STAND_IN = """#!/bin/bash
# A stand-in for Python {version}.
case "$1 $2" in
    "-c "*version_info*) exit {status} ;;
    "-c "*version.split*) echo {version}; exit 0 ;;
    "-m venv") mkdir -p "$3/bin" && cp "$0" "$3/bin/python" && exit 0 ;;
esac
echo "Python {version} ran: $*" >> "{calls}"
exit 0
"""


@pytest.fixture
def setup(tmp_path):
    """A folder holding a copy of launch_web.sh, a bin folder for the stand-ins
    and the tools, and the file the stand-ins write their calls to."""
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copy(SCRIPT, repo / "launch_web.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        (bin_dir / tool).symlink_to(shutil.which(tool))
    return repo, bin_dir, tmp_path / "calls.txt"


def _python(where: Path, name: str, version: str, calls: Path) -> Path:
    ok = tuple(int(part) for part in version.split(".")[:2]) >= (3, 10)
    path = where / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STAND_IN.format(version=version, status=0 if ok else 1, calls=calls))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _launch(repo: Path, bin_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": str(bin_dir), "HOME": str(repo)}
    return subprocess.run(["/bin/bash", str(repo / "launch_web.sh"), *args], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=30)


def _calls(calls: Path) -> str:
    return calls.read_text() if calls.exists() else ""


def test_only_an_old_python_says_what_to_install(setup):
    repo, bin_dir, calls = setup
    _python(bin_dir, "python3", "3.9.6", calls)
    done = _launch(repo, bin_dir, "--no-launch")
    assert done.returncode == 1
    assert "needs Python 3.10 or newer" in done.stderr
    assert f"version 3.9.6 ({bin_dir / 'python3'}), which is too old" in done.stderr
    assert "https://www.python.org/downloads/" in done.stderr
    assert not (repo / ".venv-dashboard").exists()
    assert _calls(calls) == ""


def test_no_python_at_all_says_what_to_install(setup):
    repo, bin_dir, calls = setup
    done = _launch(repo, bin_dir, "--no-launch")
    assert done.returncode == 1
    assert "No Python was found on this computer." in done.stderr
    assert not (repo / ".venv-dashboard").exists()


def test_a_newer_python_beside_an_old_default_is_used(setup):
    # As on a Mac with the Python that comes with macOS first on PATH and a
    # Python from python.org beside it.
    repo, bin_dir, calls = setup
    _python(bin_dir, "python3", "3.9.6", calls)
    _python(bin_dir, "python3.12", "3.12.4", calls)
    done = _launch(repo, bin_dir, "--no-launch")
    assert done.returncode == 0, done.stderr
    ran = _calls(calls)
    assert "Python 3.12.4 ran: " in ran and "--ensure-deps-only" in ran
    assert "-m SigProfilerExtractor.web.launcher --no-launch" in ran
    assert "Python 3.9.6" not in ran


def test_the_default_python_is_used_when_it_is_new_enough(setup):
    repo, bin_dir, calls = setup
    _python(bin_dir, "python3", "3.13.1", calls)
    _python(bin_dir, "python3.12", "3.12.4", calls)
    done = _launch(repo, bin_dir, "--no-launch")
    assert done.returncode == 0, done.stderr
    assert "Python 3.13.1 ran: " in _calls(calls)
    assert "Python 3.12.4" not in _calls(calls)


def test_an_environment_made_with_an_old_python_is_made_again(setup):
    repo, bin_dir, calls = setup
    _python(bin_dir, "python3", "3.12.4", calls)
    old = repo / ".venv-dashboard"
    _python(old / "bin", "python", "3.9.6", calls)
    (old / "left-from-before").write_text("x")
    done = _launch(repo, bin_dir, "--no-launch")
    assert done.returncode == 0, done.stderr
    assert ("The Workbench's environment was made with Python 3.9.6; "
            "setting it up again with Python 3.12.4.") in done.stdout
    assert not (old / "left-from-before").exists()
    ran = _calls(calls).splitlines()
    # A Workbench still running from the old environment is stopped first.
    assert ran[0].startswith("Python 3.12.4 ran: ") and ran[0].endswith("--stop")
    assert any(line.endswith("--ensure-deps-only") for line in ran[1:])
    assert "Python 3.9.6" not in _calls(calls)


def test_an_environment_whose_python_is_gone_is_made_again(setup):
    repo, bin_dir, calls = setup
    _python(bin_dir, "python3", "3.12.4", calls)
    (repo / ".venv-dashboard" / "bin").mkdir(parents=True)
    done = _launch(repo, bin_dir, "--no-launch")
    assert done.returncode == 0, done.stderr
    assert "The Workbench's environment no longer runs; setting it up again" in done.stdout
    assert (repo / ".venv-dashboard" / "bin" / "python").exists()


def test_a_good_environment_is_kept(setup):
    repo, bin_dir, calls = setup
    _python(bin_dir, "python3", "3.12.4", calls)
    venv = repo / ".venv-dashboard"
    _python(venv / "bin", "python", "3.12.4", calls)
    (venv / "kept").write_text("x")
    done = _launch(repo, bin_dir, "--no-launch")
    assert done.returncode == 0, done.stderr
    assert "setting it up again" not in done.stdout
    assert (venv / "kept").exists()


def test_stop_works_with_only_an_old_python(setup):
    repo, bin_dir, calls = setup
    _python(bin_dir, "python3", "3.9.6", calls)
    done = _launch(repo, bin_dir, "--stop")
    assert done.returncode == 0, done.stderr
    assert _calls(calls).strip().endswith("--stop")
