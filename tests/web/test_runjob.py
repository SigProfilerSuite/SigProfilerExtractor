import json
from pathlib import Path

import pytest

from SigProfilerExtractor.web import runjob

DATA = Path(runjob.__file__).resolve().parents[1] / "data"
TINY = {"minimum_signatures": 2, "maximum_signatures": 2, "nmf_replicates": 3,
        "min_nmf_iterations": 100, "max_nmf_iterations": 1000, "nmf_test_conv": 100,
        "cpu": 2, "assignment_cpu": 2}


@pytest.fixture
def stub_extractor(monkeypatch):
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        out = Path(kwargs["output"])
        out.mkdir(parents=True, exist_ok=True)
        (out / "JOB_METADATA.txt").write_text("WARNING: Results dashboard could not be created: test\n")

    from SigProfilerExtractor import sigpro

    monkeypatch.setattr(sigpro, "sigProfilerExtractor", fake)
    return calls


def _write_config(tmp_path, config):
    job = tmp_path / "job"
    job.mkdir()
    path = job / "config.json"
    path.write_text(json.dumps(config))
    return path


def test_a_run_passes_its_settings_through_and_reports_warnings(tmp_path, stub_extractor):
    kwargs = {"input_type": "matrix", "input_data": str(DATA / "TextInput" / "Samples_SBS.txt"),
              "output": str(tmp_path / "out"), "nmf_replicates": 7}
    path = _write_config(tmp_path, {"mode": "run", "kwargs": kwargs})
    assert runjob.main([str(path)]) == 0
    assert stub_extractor[0] == kwargs
    result = json.loads((path.parent / "result.json").read_text())
    assert result["status"] == "done"
    assert result["warnings"] == ["WARNING: Results dashboard could not be created: test"]


def test_a_bundled_vcf_example_is_copied_before_the_run(tmp_path, stub_extractor):
    kwargs = {"input_type": "vcf", "input_data": str(DATA / "VCFInput"), "output": str(tmp_path / "out")}
    path = _write_config(tmp_path, {"mode": "run", "kwargs": kwargs, "copy_input": True})
    assert runjob.main([str(path)]) == 0
    used = Path(stub_extractor[0]["input_data"])
    assert used == path.parent / "input"
    assert sorted(p.name for p in used.iterdir()) == sorted(p.name for p in (DATA / "VCFInput").iterdir())


def test_replacing_clears_earlier_results_first(tmp_path, stub_extractor):
    out = tmp_path / "out"
    (out / "SBS96" / "All_Solutions").mkdir(parents=True)
    (out / "mine.txt").write_text("keep")
    kwargs = {"input_type": "matrix", "input_data": str(DATA / "TextInput" / "Samples_SBS.txt"), "output": str(out)}
    path = _write_config(tmp_path, {"mode": "run", "kwargs": kwargs, "replace_existing": True})
    assert runjob.main([str(path)]) == 0
    assert not (out / "SBS96").exists() and (out / "mine.txt").exists()


def test_a_failure_is_reported_with_its_message(tmp_path, monkeypatch):
    from SigProfilerExtractor import sigpro

    def boom(**kwargs):
        raise ValueError("Please set valid seeds")

    monkeypatch.setattr(sigpro, "sigProfilerExtractor", boom)
    kwargs = {"input_type": "matrix", "input_data": "x", "output": str(tmp_path / "out")}
    path = _write_config(tmp_path, {"mode": "run", "kwargs": kwargs})
    assert runjob.main([str(path)]) == 1
    result = json.loads((path.parent / "result.json").read_text())
    assert result == {"status": "failed", "error": "ValueError: Please set valid seeds", "warnings": []}


def test_a_real_tiny_run_through_the_job_runner(tmp_path):
    # SigProfilerExtractor itself, on the bundled 21-genome SBS96 matrix, with
    # settings small enough for a test: a real result folder and dashboard.
    from SigProfilerExtractor.web import jobs, params

    settings = {"input_type": "matrix", "input_data": str(DATA / "TextInput" / "Samples_SBS.txt"),
                "output": str(tmp_path / "out"), "stop_after_extraction": True, **TINY}
    kwargs = params.validate(settings)
    manager = jobs.JobManager(tmp_path / "jobs")
    meta = manager.start({"mode": "run", "kwargs": kwargs}, "tiny",
                         cwd=str(Path(runjob.__file__).resolve().parents[2]))
    import time

    deadline = time.monotonic() + 600
    while manager.get(meta["id"])["status"] == "running" and time.monotonic() < deadline:
        time.sleep(1)
    job = manager.get(meta["id"])
    assert job["status"] == "done", manager.log(meta["id"])["text"][-3000:]
    assert job["found_contexts"][0]["name"] == "SBS96"
    assert job["found_contexts"][0]["suggested_rank"] == 2
    assert (tmp_path / "out" / "reports.html").is_file()
    assert "Extracting signature 2 for mutation type 96" in manager.log(meta["id"])["text"]
