from pathlib import Path

from SigProfilerExtractor.web import progress

LOGS = Path(__file__).parent / "fixtures" / "logs"


def _lines(name):
    return (LOGS / name).read_text().splitlines()


QUICK = {"contexts": ["SBS96"], "minimum_signatures": 1, "maximum_signatures": 5,
         "nmf_replicates": 10, "samples": 21, "assignment": True, "status": "running"}
VCF = {"contexts": ["SBS96", "DBS78", "ID83"], "minimum_signatures": 1, "maximum_signatures": 3,
       "nmf_replicates": 5, "samples": 5, "assignment": True, "status": "running"}


def _at(lines, needle, job, offset=1):
    cut = next(i for i, line in enumerate(lines) if needle in line) + offset
    return progress.parse("\n".join(lines[:cut]), job)


def test_context_shorthand_maps_to_folder_names():
    assert [progress.context_name(x) for x in ("96", "1536", "DINUC", "ID", "CNV", "SV", "78")] == \
        ["SBS96", "SBS1536", "DBS78", "ID83", "CNV48", "SV32", "DBS78"]


def test_a_single_context_run_moves_through_ranks_replicates_and_assignment():
    lines = _lines("quick_sbs96.log")
    start = progress.parse("\n".join(lines[:2]), QUICK)
    assert start["phase"] == "input" and start["fraction"] == 0

    p = _at(lines, "Extracting signature 3 for", QUICK, offset=6)
    ctx = p["contexts"][0]
    assert (p["phase"], ctx["rank"], ctx["ranks_done"]) == ("extract", 3, 2)
    assert 0 < ctx["replicates_done"] <= 10
    assert p["remaining_seconds"] is not None

    p = _at(lines, "De Novo Fitting", QUICK)
    assert p["phase"] == "assign" and p["contexts"][0]["stage"] == "assign"
    assert p["contexts"][0]["ranks_done"] == 5

    done = progress.parse("\n".join(lines), dict(QUICK, status="done"))
    assert done["phase"] == "done" and done["fraction"] == 1.0
    assert done["contexts"][0]["state"] == "done"


def test_fraction_never_goes_backwards():
    lines = _lines("quick_sbs96.log")
    fractions = [progress.parse("\n".join(lines[:i]), QUICK)["fraction"] for i in range(0, len(lines), 5)]
    assert fractions == sorted(fractions)


def test_a_vcf_run_builds_matrices_then_takes_contexts_in_turn_and_skips_missing_ones():
    lines = _lines("vcf.log")
    p = _at(lines, "Starting matrix generation", VCF)
    assert p["phase"] == "matrices"

    p = _at(lines, "Extracting signature 1 for mutation type DINUC", VCF)
    states = {c["name"]: c["state"] for c in p["contexts"]}
    assert states == {"SBS96": "done", "DBS78": "active", "ID83": "waiting"}

    done = progress.parse("\n".join(lines), dict(VCF, status="done"))
    states = {c["name"]: c["state"] for c in done["contexts"]}
    assert states == {"SBS96": "done", "DBS78": "done", "ID83": "skipped"}


def test_the_dashboard_step_shows_after_the_last_assignment():
    lines = _lines("vcf.log")
    p = _at(lines, "Interactive results dashboard", VCF)
    assert p["phase"] == "dashboard"
