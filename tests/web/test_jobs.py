import time

import pytest

from SigProfilerExtractor.web import jobs

REPO_ROOT = jobs.Path(__file__).resolve().parents[2]


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "RUNJOB_MODULE", "tests.web.fixtures.fake_runjob")
    return jobs.JobManager(tmp_path / "jobs")


def _start(manager, **config):
    return manager.start(config, name="test run", cwd=REPO_ROOT)


def _wait_for_status(manager, job_id, status, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        meta = manager.get(job_id)
        if meta["status"] == status:
            return meta
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never reached status {status!r} (last: {meta})")


def test_successful_job_reaches_done(manager):
    meta = _start(manager, outcome="done")
    done = _wait_for_status(manager, meta["id"], "done")
    assert done["found_contexts"] == [{"name": "SBS96", "suggested_rank": 3}]
    assert "elapsed_seconds" in done


def test_extra_metadata_is_recorded_and_survives_completion(manager):
    meta = manager.start(
        {"outcome": "done"}, name="run", cwd=REPO_ROOT,
        extra={"kind": "run", "output_dir": "/out", "id": "must-not-override"},
    )
    assert meta["kind"] == "run"
    assert meta["id"] != "must-not-override"
    done = _wait_for_status(manager, meta["id"], "done")
    assert done["output_dir"] == "/out"


def test_failed_job_reports_error(manager):
    meta = _start(manager, outcome="failed")
    failed = _wait_for_status(manager, meta["id"], "failed")
    assert failed["error"] == "simulated failure"


def test_crashed_job_without_result_is_reported_failed(manager, monkeypatch):
    # Simulate a process that dies without ever writing result.json (e.g.
    # killed externally) by starting a "hang" job and then killing it
    # directly, bypassing manager.stop() (which marks it "stopped").
    meta = _start(manager, outcome="hang", sleep_seconds=0)
    time.sleep(0.3)
    import os
    import signal

    os.kill(meta["pid"], signal.SIGKILL)
    _wait_for_status(manager, meta["id"], "failed")


def test_stop_kills_a_running_job(manager):
    meta = _start(manager, outcome="hang")
    time.sleep(0.3)
    assert manager.stop(meta["id"]) is True
    stopped = manager.get(meta["id"])
    assert stopped["status"] == "stopped"


def test_stop_on_already_finished_job_is_a_noop(manager):
    meta = _start(manager, outcome="done")
    _wait_for_status(manager, meta["id"], "done")
    assert manager.stop(meta["id"]) is True
    assert manager.get(meta["id"])["status"] == "done"


def test_stop_unknown_job_raises(manager):
    with pytest.raises(jobs.JobError):
        manager.stop("does-not-exist")


def test_log_returns_new_text_from_offset(manager):
    meta = _start(manager, outcome="done")
    _wait_for_status(manager, meta["id"], "done")
    first = manager.log(meta["id"], offset=0)
    assert "step 1/1" in first["text"]
    second = manager.log(meta["id"], offset=first["offset"])
    assert second["text"] == ""


def test_log_unknown_job_raises(manager):
    with pytest.raises(jobs.JobError):
        manager.log("does-not-exist")


def test_listing_orders_newest_first(manager):
    first = _start(manager, outcome="done")
    time.sleep(0.05)
    second = _start(manager, outcome="done")
    listing = manager.listing()
    ids = [job["id"] for job in listing]
    assert ids.index(second["id"]) < ids.index(first["id"])


def test_live_only_returns_running_jobs(manager):
    running = _start(manager, outcome="hang")
    finished = _start(manager, outcome="done")
    _wait_for_status(manager, finished["id"], "done")
    time.sleep(0.2)
    live_ids = {job["id"] for job in manager.live()}
    assert running["id"] in live_ids
    assert finished["id"] not in live_ids
    manager.stop(running["id"])


def test_stop_all_stops_every_running_job(manager):
    a = _start(manager, outcome="hang")
    b = _start(manager, outcome="hang")
    time.sleep(0.3)
    manager.stop_all()
    assert manager.get(a["id"])["status"] == "stopped"
    assert manager.get(b["id"])["status"] == "stopped"


def test_job_records_survive_a_new_manager_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "RUNJOB_MODULE", "tests.web.fixtures.fake_runjob")
    jobs_dir = tmp_path / "jobs"
    first_manager = jobs.JobManager(jobs_dir)
    meta = _start(first_manager, outcome="done")
    _wait_for_status(first_manager, meta["id"], "done")

    second_manager = jobs.JobManager(jobs_dir)
    assert second_manager.get(meta["id"])["status"] == "done"


def test_a_finished_job_can_leave_the_list_and_come_back(manager):
    job = _start(manager, outcome="done")
    _wait_for_status(manager, job["id"], "done")

    manager.set_hidden(job["id"], True)
    assert job["id"] not in [j["id"] for j in manager.listing()]
    assert job["id"] in [j["id"] for j in manager.listing(include_hidden=True)]

    manager.set_hidden(job["id"], False)
    assert job["id"] in [j["id"] for j in manager.listing()]


def test_deleting_a_job_record_removes_it_for_good(manager):
    job = _start(manager, outcome="done")
    _wait_for_status(manager, job["id"], "done")

    manager.delete_record(job["id"])

    assert manager.get(job["id"]) is None
    assert not (manager.jobs_dir / job["id"]).exists()


def test_a_running_job_can_be_neither_hidden_nor_deleted(manager):
    job = _start(manager, outcome="hang")
    try:
        with pytest.raises(jobs.JobError):
            manager.set_hidden(job["id"], True)
        with pytest.raises(jobs.JobError):
            manager.delete_record(job["id"])
    finally:
        manager.stop(job["id"])


@pytest.mark.parametrize("bad", ["..", "../jobs", "ABCDEF123456", "abc", "0123456789abc"])
def test_job_ids_of_any_other_shape_are_refused(manager, bad):
    assert manager.get(bad) is None
    with pytest.raises(jobs.JobError):
        manager.delete_record(bad)
    with pytest.raises(jobs.JobError):
        manager.log(bad)
