"""Checking whether a process is alive, on every platform (Windows in CI).

On Windows, os.kill(pid, 0) is not a probe: signal 0 is CTRL_C_EVENT, so the
call sends Ctrl+C to every process on the console. A check like that would
raise KeyboardInterrupt in this test process, which ends the pytest session.
"""

import os
import subprocess
import sys
import time

import pytest

from SigProfilerExtractor.web import jobs, launcher

REPO_ROOT = jobs.Path(__file__).resolve().parents[2]
SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


@pytest.fixture
def sleeper():
    # Same console and process group as this test: the case where a stray
    # Ctrl+C would reach the caller too.
    child = subprocess.Popen(SLEEPER)
    yield child
    child.kill()
    child.wait()


def _settle():
    # A console Ctrl+C arrives asynchronously; give it time to land.
    time.sleep(0.5)


def test_a_running_process_is_alive_and_checking_it_sends_no_ctrl_c(sleeper):
    for _ in range(10):
        assert launcher._is_process_alive(sleeper.pid) is True
        assert jobs._is_alive(sleeper.pid) is True
    _settle()


def test_this_process_is_alive():
    assert launcher._is_process_alive(os.getpid()) is True
    _settle()


def test_a_process_that_exited_is_not_alive():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert launcher._is_process_alive(child.pid) is False
    assert jobs._is_alive(child.pid) is False


@pytest.mark.parametrize("pid", [0, -1, 2**30])
def test_impossible_pids_are_not_alive(pid):
    assert launcher._is_process_alive(pid) is False


def test_waiting_for_another_launchs_lock_sends_no_ctrl_c(tmp_path, monkeypatch, sleeper):
    # What failed on Windows CI: --stop found the startup lock still held by
    # the server it had just stopped, and checked whether that server was alive.
    monkeypatch.setattr(launcher, "_state_dir", lambda: tmp_path)
    launcher._lockfile().write_text(str(sleeper.pid))
    assert launcher._acquire_startup_lock(timeout=0.5) is None
    _settle()


def test_a_lock_left_by_a_process_that_exited_is_reclaimed(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "_state_dir", lambda: tmp_path)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    launcher._lockfile().write_text(str(child.pid))
    lock = launcher._acquire_startup_lock(timeout=1.0)
    assert lock is not None
    lock.unlink()


def test_a_running_job_can_be_checked_on_repeatedly(tmp_path, monkeypatch):
    # The Workbench checks each running job's process whenever the page asks
    # for job status, every second or two for the whole run.
    monkeypatch.setattr(jobs, "RUNJOB_MODULE", "tests.web.fixtures.fake_runjob")
    manager = jobs.JobManager(tmp_path / "jobs")
    meta = manager.start({"outcome": "hang", "sleep_seconds": 0}, name="run", cwd=REPO_ROOT)
    try:
        time.sleep(0.5)
        for _ in range(10):
            assert manager.get(meta["id"])["status"] == "running"
            assert [j["id"] for j in manager.live()] == [meta["id"]]
        _settle()
    finally:
        manager.stop(meta["id"])
    assert manager.get(meta["id"])["status"] == "stopped"


def test_windows_never_checks_with_os_kill(monkeypatch):
    # Runs everywhere, so a change that brings os.kill back on Windows fails
    # on Linux and macOS too, not only on the Windows job.
    def no_kill(*args):
        raise AssertionError("os.kill must not be used to check a process on Windows")

    checked = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "kill", no_kill)
    monkeypatch.setattr(launcher, "_windows_process_alive", lambda pid: checked.append(pid) or True)
    assert launcher._is_process_alive(4321) is True
    assert jobs._is_alive(4321) is True
    assert checked == [4321, 4321]
