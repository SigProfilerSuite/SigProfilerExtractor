import os
import subprocess
import sys
import time

import pytest

from SigProfilerExtractor.web import launcher


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(launcher, "_state_dir", lambda: state_dir)


# --------------------------------------------------------------- fingerprint


def test_fingerprint_changes_when_packaging_files_change(tmp_path):
    (tmp_path / "setup.py").write_text("v1")
    first = launcher.compute_fingerprint(tmp_path)
    (tmp_path / "setup.py").write_text("v2")
    second = launcher.compute_fingerprint(tmp_path)
    assert first != second


def test_fingerprint_is_stable_for_unchanged_files(tmp_path):
    (tmp_path / "setup.py").write_text("v1")
    assert launcher.compute_fingerprint(tmp_path) == launcher.compute_fingerprint(tmp_path)


def test_needs_install_when_fingerprint_file_absent(tmp_path):
    assert launcher.needs_install(tmp_path, tmp_path / "missing", force=False) is True


def test_needs_install_when_forced(tmp_path):
    fingerprint_path = tmp_path / ".fingerprint"
    fingerprint_path.write_text(launcher.compute_fingerprint(tmp_path))
    assert launcher.needs_install(tmp_path, fingerprint_path, force=True) is True


def test_no_install_needed_when_fingerprint_matches(tmp_path):
    fingerprint_path = tmp_path / ".fingerprint"
    fingerprint_path.write_text(launcher.compute_fingerprint(tmp_path))
    assert launcher.needs_install(tmp_path, fingerprint_path, force=False) is False


def test_needs_install_when_fingerprint_is_stale(tmp_path):
    fingerprint_path = tmp_path / ".fingerprint"
    fingerprint_path.write_text("stale-value")
    assert launcher.needs_install(tmp_path, fingerprint_path, force=False) is True


# ---------------------------------------------------------------- pidfile


def test_pidfile_round_trips(tmp_path):
    pidfile = tmp_path / "dashboard.pid"
    launcher._write_pidfile_atomic(pidfile, 1234, 8787, "tok")
    assert launcher._read_pidfile(pidfile) == (1234, 8787, "tok")


def test_read_pidfile_missing_file_returns_none(tmp_path):
    assert launcher._read_pidfile(tmp_path / "nope") is None


def test_read_pidfile_malformed_returns_none(tmp_path):
    pidfile = tmp_path / "dashboard.pid"
    pidfile.write_text("not-the-right-format")
    assert launcher._read_pidfile(pidfile) is None


def test_is_process_alive_for_self():
    assert launcher._is_process_alive(os.getpid()) is True


def test_is_process_alive_false_for_a_pid_that_does_not_exist():
    # A pid this large is exceedingly unlikely to be in use.
    assert launcher._is_process_alive(2**30) is False


# ---------------------------------------------------------- startup lock


def test_acquire_and_release_startup_lock(tmp_path):
    lock_path = launcher._acquire_startup_lock()
    assert lock_path is not None
    assert lock_path.is_file()
    lock_path.unlink()


def test_second_lock_acquire_waits_then_times_out():
    first = launcher._acquire_startup_lock()
    assert first is not None
    started = time.monotonic()
    second = launcher._acquire_startup_lock(timeout=0.3)
    elapsed = time.monotonic() - started
    assert second is None
    assert elapsed >= 0.25
    first.unlink()


def test_lock_held_by_a_dead_pid_is_reclaimed(tmp_path):
    lock_path = launcher._lockfile()
    lock_path.write_text(str(2**30))
    reclaimed = launcher._acquire_startup_lock(timeout=1.0)
    assert reclaimed is not None
    reclaimed.unlink()


# --------------------------------------------------------- server lifecycle


def _subprocess_env(cache_base):
    env = dict(os.environ)
    if sys.platform == "win32":
        env["LOCALAPPDATA"] = str(cache_base)
    else:
        env["XDG_CACHE_HOME"] = str(cache_base)
    return env


def _state_dir_under(cache_base):
    # Mirrors launcher._state_dir()'s own per-platform subdirectory naming.
    name = "SigProfilerExtractor" if sys.platform == "win32" else "sigprofilerextractor"
    return cache_base / name


def _spawn_dashboard(cache_base):
    # launcher.main() (the installed sigprofilerextractor-web console
    # script's entry point) is used here rather than `python -m
    # ...launcher` (managed_main()), which first ensures/installs
    # dependencies into whatever environment it runs in -- a real pip
    # install is not something a test should trigger against the shared
    # dev environment.
    repo_root = launcher._repo_root()
    code = (
        "from SigProfilerExtractor.web import launcher; "
        "import sys; sys.exit(launcher.main(sys.argv[1:]))"
    )
    return subprocess.Popen(
        [sys.executable, "-u", "-c", code, "--no-launch"],
        cwd=str(repo_root),
        env=_subprocess_env(cache_base),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_for_pidfile(cache_base, timeout=15.0):
    # _run_server() can only be exercised as a real subprocess's main thread
    # (it installs a SIGTERM handler, which Python refuses off the main
    # thread), so these lifecycle tests spawn the launcher for real rather
    # than running _run_server() in-process on a background thread.
    pidfile = _state_dir_under(cache_base) / "dashboard.pid"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        existing = launcher._read_pidfile(pidfile)
        if existing is not None:
            return existing
        time.sleep(0.05)
    raise AssertionError(f"pidfile never appeared at {pidfile}")


def test_run_server_then_stop_server_end_to_end(tmp_path, monkeypatch):
    cache_base = tmp_path / "subproc_state"
    cache_base.mkdir()
    process = _spawn_dashboard(cache_base)
    try:
        pid, port, token = _wait_for_pidfile(cache_base)
        assert launcher._verify_identity(pid, port, token) is True

        monkeypatch.setattr(launcher, "_state_dir", lambda: _state_dir_under(cache_base))
        assert launcher.stop_server() is True
        assert launcher._read_pidfile(_state_dir_under(cache_base) / "dashboard.pid") is None
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_stop_server_with_no_running_dashboard_is_a_clean_noop():
    assert launcher.stop_server() is True


def test_second_launch_refuses_to_start_a_duplicate(tmp_path):
    cache_base = tmp_path / "subproc_state"
    cache_base.mkdir()
    first = _spawn_dashboard(cache_base)
    try:
        pid, port, token = _wait_for_pidfile(cache_base)

        second = _spawn_dashboard(cache_base)
        output, _ = second.communicate(timeout=10)
        assert second.returncode == 0
        assert "already running" in output
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)


# ------------------------------------------------------- installing with uv


class _Runs:
    """Records install commands instead of running them; fails the ones asked."""

    def __init__(self, fail=()):
        self.commands, self.fail = [], fail

    def __call__(self, command, check=False):
        self.commands.append(command)
        failed = any(word in command for word in self.fail)
        if failed and check:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 1 if failed else 0)


@pytest.fixture
def install_env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "setup.py").write_text("x")
    fingerprint = tmp_path / ".fingerprint"
    monkeypatch.setattr(launcher, "_fingerprint_path", lambda: fingerprint)
    monkeypatch.delenv("SPE_WEB_INSTALLER", raising=False)
    return repo, fingerprint


def _install(monkeypatch, repo, runs, uv_on_path=None):
    monkeypatch.setattr(launcher.subprocess, "run", runs)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: uv_on_path if name == "uv" else None)
    launcher.ensure_dependencies(repo, force=True)


def test_installs_with_the_uv_already_on_path(install_env, monkeypatch):
    repo, fingerprint = install_env
    runs = _Runs()
    _install(monkeypatch, repo, runs, uv_on_path="/opt/bin/uv")
    assert runs.commands == [["/opt/bin/uv", "pip", "install", "--python", sys.executable, "-e", str(repo)]]
    assert fingerprint.read_text() == launcher.compute_fingerprint(repo)


def test_adds_uv_to_the_environment_when_it_is_not_on_path(install_env, monkeypatch):
    repo, _ = install_env
    runs = _Runs()
    _install(monkeypatch, repo, runs)
    add_uv, install = runs.commands
    assert add_uv[:4] == [sys.executable, "-m", "pip", "install"] and add_uv[-1] == "uv"
    assert install == [sys.executable, "-m", "uv", "pip", "install", "--python", sys.executable, "-e", str(repo)]


def test_falls_back_to_pip_when_uv_cannot_be_added(install_env, monkeypatch):
    repo, fingerprint = install_env
    runs = _Runs(fail=("uv",))
    _install(monkeypatch, repo, runs)
    assert runs.commands[-1] == [sys.executable, "-m", "pip", "install", "--quiet", "-e", str(repo)]
    assert fingerprint.is_file()


def test_falls_back_to_pip_when_uv_cannot_install(install_env, monkeypatch, capsys):
    repo, fingerprint = install_env
    runs = _Runs(fail=("--python",))
    _install(monkeypatch, repo, runs, uv_on_path="/opt/bin/uv")
    assert [c[0] for c in runs.commands] == ["/opt/bin/uv", sys.executable]
    assert runs.commands[-1][1:4] == ["-m", "pip", "install"]
    assert "trying pip instead" in capsys.readouterr().out
    assert fingerprint.is_file()


def test_spe_web_installer_pip_skips_uv(install_env, monkeypatch):
    repo, _ = install_env
    monkeypatch.setenv("SPE_WEB_INSTALLER", "pip")
    runs = _Runs()
    _install(monkeypatch, repo, runs, uv_on_path="/opt/bin/uv")
    assert runs.commands == [[sys.executable, "-m", "pip", "install", "--quiet", "-e", str(repo)]]


def test_a_failed_install_leaves_no_fingerprint(install_env, monkeypatch):
    repo, fingerprint = install_env
    runs = _Runs(fail=("-e",))
    with pytest.raises(subprocess.CalledProcessError):
        _install(monkeypatch, repo, runs, uv_on_path="/opt/bin/uv")
    assert not fingerprint.exists()


def test_no_install_when_the_fingerprint_matches(install_env, monkeypatch, capsys):
    repo, fingerprint = install_env
    fingerprint.write_text(launcher.compute_fingerprint(repo))
    runs = _Runs()
    monkeypatch.setattr(launcher.subprocess, "run", runs)
    launcher.ensure_dependencies(repo)
    assert runs.commands == []
    assert "skipping install" in capsys.readouterr().out
