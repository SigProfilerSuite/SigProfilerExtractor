import inspect
from pathlib import Path

import pytest

from SigProfilerExtractor.web import params


def _settings(tmp_path, **over):
    matrix = tmp_path / "m.txt"
    matrix.write_text("MutationType\tS1\nA[C>A]A\t1\n")
    base = {"input_type": "matrix", "input_data": str(matrix), "output": str(tmp_path / "out")}
    base.update(over)
    return base


def test_defaults_are_sigprofilerextractors_own():
    # The Workbench must start from exactly the defaults the function has.
    from SigProfilerExtractor import sigpro

    signature = inspect.signature(sigpro.sigProfilerExtractor)
    real = {name: p.default for name, p in signature.parameters.items()
            if p.default is not inspect.Parameter.empty}
    assert params.DEFAULTS == real


def test_standard_preset_is_the_published_setting():
    d = params.DEFAULTS
    assert params.PRESETS["standard"]["values"] == {
        "minimum_signatures": d["minimum_signatures"], "maximum_signatures": d["maximum_signatures"],
        "nmf_replicates": d["nmf_replicates"]}


def test_supported_cosmic_versions_match_sigpro():
    from SigProfilerExtractor import sigpro

    assert params.COSMIC_VERSIONS == sigpro.SUPPORTED_COSMIC_VERSIONS


def test_a_matrix_run_with_nothing_changed_gets_the_defaults(tmp_path):
    kwargs = params.validate(_settings(tmp_path))
    for key, value in params.DEFAULTS.items():
        if key in ("context_type", "reference_genome", "volume"):
            continue
        assert kwargs[key] == value, key
    assert kwargs["input_type"] == "matrix"


def test_vcf_run_builds_context_type_and_uses_its_genome_for_cosmic(tmp_path):
    folder = tmp_path / "calls"
    folder.mkdir()
    kwargs = params.validate({"input_type": "vcf", "input_data": str(folder), "output": str(tmp_path / "o"),
                              "reference_genome": "GRCh38", "contexts": ["ID83", "SBS96"]})
    assert kwargs["context_type"] == "SBS96,ID83"
    assert kwargs["opportunity_genome"] == "GRCh38"


def test_seg_input_names_its_caller(tmp_path):
    kwargs = params.validate(_settings(tmp_path, input_type="seg", seg_caller="BATTENBERG"))
    assert kwargs["input_type"] == "seg:BATTENBERG"
    with pytest.raises(params.ParamsError) as err:
        params.validate(_settings(tmp_path, input_type="seg"))
    assert "caller" in str(err.value)


@pytest.mark.parametrize("over, fragment", [
    ({"minimum_signatures": 5, "maximum_signatures": 2}, "cannot be larger"),
    ({"nmf_replicates": 0}, "at least 1"),
    ({"nmf_replicates": "ten"}, "whole number"),
    ({"min_nmf_iterations": 500, "max_nmf_iterations": 100}, "cannot be more than"),
    ({"matrix_normalization": "zscore"}, "gmm, 100X"),
    ({"matrix_normalization": "-5"}, "gmm, 100X"),
    ({"nmf_init": "best"}, "NMF initialization"),
    ({"precision": "half"}, "Precision"),
    ({"clustering_distance": "euclid"}, "Clustering distance"),
    ({"cosmic_version": 4}, "COSMIC version"),
    ({"stability": 1.5}, "between 0 and 1"),
    ({"combined_stability": 3}, "between 0 and 2"),
    ({"nmf_tolerance": 0}, "greater than 0"),
    ({"cpu": 0}, "at least 1"),
    ({"opportunity_genome": "hg19"}, "COSMIC reference genome"),
    ({"output": ""}, "output folder"),
    ({"input_type": "csv"}, "kind of input"),
])
def test_every_rule_is_checked_with_a_plain_message(tmp_path, over, fragment):
    with pytest.raises(params.ParamsError) as err:
        params.validate(_settings(tmp_path, **over))
    assert fragment in str(err.value)


def test_all_problems_are_reported_at_once(tmp_path):
    with pytest.raises(params.ParamsError) as err:
        params.validate(_settings(tmp_path, nmf_replicates=0, precision="half", output=""))
    assert len(err.value.problems) == 3


def test_the_input_must_be_the_right_kind_of_path(tmp_path):
    with pytest.raises(params.ParamsError, match="must be a folder"):
        params.validate(_settings(tmp_path, input_type="vcf"))
    with pytest.raises(params.ParamsError, match="must be a file"):
        params.validate(_settings(tmp_path, input_data=str(tmp_path)))


def test_gpu_only_with_cuda(tmp_path):
    with pytest.raises(params.ParamsError, match="No CUDA GPU"):
        params.validate(_settings(tmp_path, gpu=True), cuda_available=False)
    assert params.validate(_settings(tmp_path, gpu=True), cuda_available=True)["gpu"] is True


def test_seed_files_follow_read_seed_file_rules(tmp_path):
    good = tmp_path / "Seeds.txt"
    good.write_text("\tSeed\n0\t123456789012345678901234567890\n")
    assert params.seed_file_problem(str(good)) is None
    assert params.validate(_settings(tmp_path, seeds=str(good)))["seeds"] == str(good)
    two = tmp_path / "two.txt"
    two.write_text("\tSeed\n0\t1\n1\t2\n")
    assert "exactly one" in params.seed_file_problem(str(two))
    nocol = tmp_path / "nocol.txt"
    nocol.write_text("a\tb\n1\t2\n")
    assert "'Seed' column" in params.seed_file_problem(str(nocol))
    assert "does not exist" in params.seed_file_problem(str(tmp_path / "missing.txt"))


def test_a_good_seed_file_is_accepted_by_sigpro_too(tmp_path):
    from SigProfilerExtractor import sigpro

    good = tmp_path / "Seeds.txt"
    good.write_text("\tSeed\n0\t42\n")
    assert params.seed_file_problem(str(good)) is None
    assert sigpro.read_seed_file(str(good))[1] == 42


def test_effort_counts_fits_and_caps_ranks_at_samples():
    kwargs = {"minimum_signatures": 1, "maximum_signatures": 25, "nmf_replicates": 100}
    assert params.effort(kwargs, contexts=3)["fits"] == 3 * 25 * 100
    assert params.effort(kwargs, contexts=1, samples=5) == {"contexts": 1, "ranks": 5, "replicates": 100, "fits": 500}
