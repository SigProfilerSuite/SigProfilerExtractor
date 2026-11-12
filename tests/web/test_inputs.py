from pathlib import Path

import pytest

from SigProfilerExtractor.web import inputs


def _matrix(path, rows, samples, value=lambda i, j: i + j):
    lines = ["MutationType\t" + "\t".join(samples)]
    for i in range(rows):
        lines.append(f"T{i}\t" + "\t".join(str(value(i, j)) for j in range(len(samples))))
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.mark.parametrize("rows, context", [(96, "SBS96"), (288, "SBS288"), (1536, "SBS1536"),
                                           (78, "DBS78"), (83, "ID83"), (48, "CNV48"), (32, "SV32"), (10, "CH10")])
def test_matrix_context_follows_the_number_of_rows(tmp_path, rows, context):
    found = inputs.inspect("matrix", str(_matrix(tmp_path / "m.txt", rows, ["S1", "S2"])))
    assert found["format"] == context
    assert found["known_context"] is (not context.startswith("CH"))


def test_empty_and_all_zero_samples_are_reported_as_dropped(tmp_path):
    def value(i, j):
        return {0: i + 1, 1: 0, 2: ""}[j]

    found = inputs.inspect("matrix", str(_matrix(tmp_path / "m.txt", 96, ["keep", "zero", "empty"], value)))
    assert found["sample_count"] == 1
    assert found["zero_samples"] == ["zero"]
    assert found["empty_samples"] == ["empty"]
    assert found["dropped_count"] == 2


def test_partly_empty_samples_are_refused_as_sigpro_refuses_them(tmp_path):
    def value(i, j):
        return "" if (j == 1 and i == 3) else 1

    with pytest.raises(inputs.InputError, match="missing values"):
        inputs.inspect("matrix", str(_matrix(tmp_path / "m.txt", 96, ["ok", "holes"], value)))


def test_a_non_numeric_value_is_named(tmp_path):
    with pytest.raises(inputs.InputError, match="not a number"):
        inputs.inspect("matrix", str(_matrix(tmp_path / "m.txt", 96, ["S1"], lambda i, j: "x" if i == 5 else 1)))


def test_matrix_must_be_a_file_and_calls_a_folder(tmp_path):
    with pytest.raises(inputs.InputError, match="one file"):
        inputs.inspect("matrix", str(tmp_path))
    f = tmp_path / "a.vcf"
    f.write_text("#CHROM\n")
    with pytest.raises(inputs.InputError, match="folder"):
        inputs.inspect("vcf", str(f))


def test_vcf_folder_reports_samples_indels_and_writability(tmp_path):
    (tmp_path / "S1.vcf").write_text("##reference=GRCh38\n#CHROM\n1\t10\t.\tA\tG\n1\t20\t.\tA\tAT\n")
    (tmp_path / "S2.vcf").write_text("#CHROM\n1\t10\t.\tC\tT\n")
    found = inputs.inspect("vcf", str(tmp_path))
    assert (found["format"], found["sample_count"], found["records"], found["indels"]) == ("VCF", 2, 3, 1)
    assert found["assembly"] == "GRCh38"
    assert found["writable"] is True


def test_bedpe_and_seg_inputs(tmp_path):
    sv = tmp_path / "sv"
    sv.mkdir()
    (sv / "A.bedpe").write_text("#h\n1\t2\n3\t4\n")
    (sv / "B.bedpe").write_text("1\t2\n")
    found = inputs.inspect("bedpe", str(sv))
    assert (found["format"], found["sample_count"], found["records"]) == ("SV32", 2, 3)
    seg = tmp_path / "seg.tsv"
    seg.write_text("sample\tchr\nT1\t1\nT1\t2\nT2\t1\n")
    found = inputs.inspect("seg", str(seg))
    assert (found["format"], found["sample_count"], found["records"]) == ("CNV48", 2, 3)


def test_every_bundled_example_is_recognised():
    examples = inputs.examples()
    assert {e["id"] for e in examples} >= {"sbs96", "vcf", "dbs78", "id83", "cnv48", "sv32", "battenberg"}
    for ex in examples:
        found = inputs.inspect(ex["input_type"], ex["input_data"])
        assert found["sample_count"] or ex["input_type"] == "seg", ex["id"]
        assert ex["output"].startswith(str(Path.home()))
    sbs = next(e for e in examples if e["id"] == "sbs96")
    assert inputs.inspect("matrix", sbs["input_data"])["sample_count"] == 21
