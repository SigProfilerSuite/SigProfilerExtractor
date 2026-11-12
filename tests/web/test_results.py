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


# ------------------------------------------------------ de novo vs COSMIC

def _catalogue_columns(path, names):
    import csv

    with open(path) as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    index = {n: rows[0].index(n) for n in names}
    return [r[0] for r in rows[1:]], {n: [float(r[i]) for r in rows[1:]] for n, i in index.items()}


def _denovo_output(root, columns, labels, mapping_rows, metadata):
    ctx = root / "SBS96"
    sig = ctx / "Suggested_Solution" / "SBS96_De-Novo_Solution" / "Signatures"
    sig.mkdir(parents=True)
    names = list(columns)
    lines = ["MutationType\t" + "\t".join(names)]
    lines += [label + "\t" + "\t".join(str(columns[n][i]) for n in names) for i, label in enumerate(labels)]
    (sig / "SBS96_De-Novo_Signatures.txt").write_text("\n".join(lines) + "\n")
    cosmic = ctx / "Suggested_Solution" / "COSMIC_SBS96_Decomposed_Solution"
    cosmic.mkdir(parents=True)
    header = "De novo extracted, Global NMF Signatures, L1 Error %, L2 Error %, KL Divergence, Cosine Similarity, Correlation"
    (cosmic / "De_Novo_map_to_COSMIC_SBS96.csv").write_text("\n".join([header, *mapping_rows]) + "\n")
    (ctx / "All_solutions_stat.csv").write_text("Signatures,x\n2*,0.9\n")
    (root / "JOB_METADATA.txt").write_text("INPUT DATA\n" + "".join(f"\t{k}: {v}\n" for k, v in metadata.items()))


def test_comparison_reads_the_split_and_finds_the_closest_cosmic_signature(tmp_path):
    catalogue, _ = results.cosmic_catalogue(96, {"cosmic_version": "3.6", "opportunity_genome": "GRCh37"})
    if catalogue is None:
        pytest.skip("SigProfilerAssignment's COSMIC catalogue is not installed")
    labels, cols = _catalogue_columns(catalogue, ["SBS13", "SBS3"])
    _denovo_output(tmp_path, {"SBS96A": cols["SBS13"], "SBS96B": cols["SBS3"]}, labels, [
        "Signature 96-SBS96A, Signature SBS2 (44.02%) & Signature SBS13 (55.98%), 10.18,  6.02, 0.022, 1.00, 0.99",
        "Signature 96-SBS96B, Signature SBS3 (100.00%), 1.0,  1.0, 0.001, 1.00, 1.00",
    ], {"input_type": "matrix", "opportunity_genome": "GRCh37", "cosmic_version": "3.6", "exome": "False"})

    comparison = results.scan(str(tmp_path))["contexts"][0]["comparison"]

    assert comparison["catalogue"] == "COSMIC v3.6 SBS (GRCh37)"
    a, b = comparison["signatures"]
    assert a["name"] == "SBS96A"
    assert a["decomposition"] == [{"name": "SBS13", "percent": 55.98}, {"name": "SBS2", "percent": 44.02}]
    assert a["fit"] == {"cosine": 1.0, "correlation": 0.99, "l1": 10.18, "l2": 6.02, "kl": 0.022}
    assert a["closest"][0] == {"name": "SBS13", "cosine": 1.0}
    assert len(a["closest"]) == 3 and a["closest"][1]["cosine"] < 1.0
    assert b["closest"][0] == {"name": "SBS3", "cosine": 1.0}


def test_sbs1536_signatures_are_compared_as_sbs96(tmp_path):
    catalogue, _ = results.cosmic_catalogue(96, {})
    if catalogue is None:
        pytest.skip("SigProfilerAssignment's COSMIC catalogue is not installed")
    labels, cols = _catalogue_columns(catalogue, ["SBS1"])
    # Spread each SBS96 channel evenly over its 16 pentanucleotide contexts.
    signature = {f"{a}{l}{b}": v / 16 for l, v in zip(labels, cols["SBS1"]) for a in "ACGT" for b in "ACGT"}
    assert results.closest_cosmic(signature, catalogue)[0] == {"name": "SBS1", "cosine": 1.0}


@pytest.mark.parametrize("channels, settings, expected", [
    (96, {"input_type": "vcf", "reference_genome": "GRCh38", "opportunity_genome": "GRCh37"}, "COSMIC_v3.6_SBS_GRCh38.txt"),
    (96, {"input_type": "matrix", "opportunity_genome": "mm10", "exome": "True"}, "COSMIC_v3.6_SBS_mm10_exome.txt"),
    (96, {"opportunity_genome": "hg19"}, "COSMIC_v3.6_SBS_GRCh37.txt"),
    (78, {"opportunity_genome": "GRCh38", "cosmic_version": "3.4"}, "COSMIC_v3.4_DBS_GRCh38.txt"),
    (83, {"opportunity_genome": "GRCh38"}, "COSMIC_v3.6_ID_GRCh37.txt"),
    (48, {}, "COSMIC_v3.6_CN_GRCh37.txt"),
    (32, {"opportunity_genome": "GRCh37"}, "COSMIC_v3.6_SV_GRCh38.txt"),
    (1536, {}, "COSMIC_v3.6_SBS_GRCh37.txt"),
    (78, {"cosmic_version": "2"}, "COSMIC_v3.6_DBS_GRCh37.txt"),
])
def test_the_catalogue_follows_sigprofilerassignments_rules(channels, settings, expected):
    path, label = results.cosmic_catalogue(channels, {"cosmic_version": "3.6", **settings})
    if path is None:
        pytest.skip("SigProfilerAssignment's COSMIC catalogue is not installed")
    assert path.name == expected and label


def test_no_comparison_without_a_suggested_solution(tmp_path):
    (tmp_path / "SBS96" / "All_Solutions").mkdir(parents=True)
    (tmp_path / "JOB_METADATA.txt").write_text("x")
    assert results.scan(str(tmp_path))["contexts"][0]["comparison"] is None
