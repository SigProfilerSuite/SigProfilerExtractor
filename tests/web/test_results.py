import os
import time

import pytest

from SigProfilerExtractor.web import results

UUIDLESS = "SBS96"


def _spe_output(root, context="SBS96", rank=3):
    """A folder laid out as SigProfilerExtractor leaves it, plus the user's own files."""
    ctx = root / context
    (ctx / "All_Solutions" / f"{context}_{rank}_Signatures" / "Signatures").mkdir(parents=True)
    (ctx / "All_solutions_stat.csv").write_text(
        "Signatures,Stability (Avg Silhouette)\n1,0.9\n2,0.85\n" + f"{rank}*,0.8\n4,0.4\n")
    (ctx / "Samples.txt").write_text("MutationType\tS1\tS2\nA[C>A]A\t1\t2\n")
    (ctx / f"{context}_selection_plot.pdf").write_bytes(b"%PDF-1.4\n")
    (ctx / "All_Solutions" / f"{context}_{rank}_Signatures" / "Signatures" / "Signature_plot.pdf").write_bytes(b"%PDF")
    denovo = ctx / "Suggested_Solution" / f"{context}_De-Novo_Solution" / "Signatures"
    denovo.mkdir(parents=True)
    (denovo / f"{context}_De-Novo_Signatures.txt").write_text("MutationType\tSBS96A\tSBS96B\tSBS96C\n")
    cosmic = ctx / "Suggested_Solution" / f"COSMIC_{context}_Decomposed_Solution"
    (cosmic / "Signatures").mkdir(parents=True)
    (cosmic / "Signatures" / f"COSMIC_{context}_Signatures.txt").write_text("MutationType\tSBS1\tSBS5\n")
    (cosmic / f"{context}_Decomposition_Plots.pdf").write_bytes(b"%PDF")
    (ctx / "Suggested_Solution" / "De_Novo_map_to_COSMIC_SBS96.csv").write_text("a,b\n")
    for name in ("JOB_METADATA.txt", "Seeds.txt", "reports.html"):
        (root / name).write_text("-------Job Status-------\nAnalysis of mutational signatures completed successfully!\n"
                                 if name == "JOB_METADATA.txt" else "x")
    (root / "SBS96_previous_20261111-120000").mkdir()
    (root / "notes.txt").write_text("mine")
    (root / "figures").mkdir()
    (root / "figures" / "paper.pdf").write_bytes(b"%PDF")


def test_scan_reads_the_suggested_solution(tmp_path):
    _spe_output(tmp_path)
    found = results.scan(str(tmp_path))
    ctx = found["contexts"][0]
    assert (ctx["name"], ctx["suggested_rank"], ctx["ranks"], ctx["samples"]) == ("SBS96", 3, [1, 2, 3, 4], 2)
    assert ctx["denovo_signatures"] == ["SBS96A", "SBS96B", "SBS96C"]
    assert ctx["cosmic_signatures"] == ["SBS1", "SBS5"]
    groups = {p["group"] for p in ctx["plots"]}
    assert groups == {"Choosing the number of signatures", "Rank 3", "COSMIC decomposition"}
    assert found["dashboard"]["name"] == "reports.html"
    assert found["job_status"] == "Analysis of mutational signatures completed successfully!"
    assert found["previous"] == ["SBS96_previous_20261111-120000"]


def test_scan_refuses_a_folder_without_results(tmp_path):
    with pytest.raises(results.ResultsError):
        results.scan(str(tmp_path))


def test_earlier_results_and_the_next_free_folder(tmp_path):
    _spe_output(tmp_path / "run")
    assert results.earlier_results(str(tmp_path / "run")) == {"found": True, "contexts": ["SBS96"]}
    assert results.earlier_results(str(tmp_path / "nothing"))["found"] is False
    _spe_output(tmp_path / "run_2")
    assert results.next_free_folder(str(tmp_path / "run")) == str(tmp_path / "run_3")


def test_replacing_removes_only_what_sigprofilerextractor_wrote(tmp_path):
    _spe_output(tmp_path)
    removed = results.clear_earlier_results(str(tmp_path), str(tmp_path.parent / "input.txt"))
    assert set(removed) == {"JOB_METADATA.txt", "Seeds.txt", "reports.html", "SBS96",
                            "SBS96_previous_20261111-120000"}
    assert (tmp_path / "notes.txt").is_file() and (tmp_path / "figures" / "paper.pdf").is_file()


def test_replacing_refuses_when_the_input_is_inside(tmp_path):
    _spe_output(tmp_path)
    assert results.replace_problem(str(tmp_path), str(tmp_path / "calls"))
    with pytest.raises(results.ResultsError):
        results.clear_earlier_results(str(tmp_path), str(tmp_path / "calls"))
    assert (tmp_path / "SBS96").is_dir()


def test_deleting_keeps_the_folder_when_other_files_remain(tmp_path):
    _spe_output(tmp_path / "shared")
    results.delete_output(str(tmp_path / "shared"), str(tmp_path / "in.txt"))
    assert (tmp_path / "shared" / "notes.txt").is_file()
    lone = tmp_path / "lone"
    lone.mkdir()
    (lone / "JOB_METADATA.txt").write_text("x")
    assert results.generated_size(str(lone))["files"] == 1
    results.delete_output(str(lone), str(tmp_path / "in.txt"))
    assert not lone.exists()


def test_only_reports_html_is_ever_served_as_the_dashboard(tmp_path):
    (tmp_path / "reports.html").write_text("x")
    (tmp_path / "evil.html").write_text("x")
    assert results.dashboard_path(str(tmp_path / "reports.html")).name == "reports.html"
    with pytest.raises(results.ResultsError):
        results.dashboard_path(str(tmp_path / "evil.html"))
