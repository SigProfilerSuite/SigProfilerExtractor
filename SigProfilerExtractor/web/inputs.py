"""Recognize a run's input before anything runs.

Four kinds, as SigProfilerExtractor takes them:

* ``vcf``: a folder of variant calls. SigProfilerExtractor hands it to
  SigProfilerMatrixGenerator, which also reads MAF and simple text, so those
  count too. Recognition follows SigProfilerMatrixGeneratorFunc's own rules
  (copied from its web app): every regular file in the folder, names starting
  with "__" or ".DS" skipped, one format per folder.
* ``matrix``: one tab-separated matrix, mutation types down the first column
  and one column per sample. The context follows from the number of rows, as
  in sigpro.py, and samples are checked as ``sigpro.check_input_samples``
  does: empty or all-zero samples are dropped, partly empty ones fail the run.
* ``bedpe``: a folder of structural-variant BEDPE files (SV32).
* ``seg``: one segmentation file from a copy-number caller (CNV48).
"""

from __future__ import annotations

import re
import os
from pathlib import Path

RECOGNIZED_EXTENSIONS = {".vcf": "VCF", ".maf": "MAF", ".txt": "Txt", ".genome": "Txt"}
PREVIEW_SAMPLES = 6


class InputError(ValueError):
    pass


def browse(path: str) -> dict:
    """List a directory's entries, for a folder picker's own listing view."""
    target = Path(path)
    if not target.is_dir():
        raise InputError(f"not a directory: {path}")
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith("."):
            continue
        entries.append({"name": child.name, "is_dir": child.is_dir()})
    return {"path": str(target), "entries": entries}


def _skipped_by_generator(name: str) -> bool:
    # The same filter SigProfilerMatrixGeneratorFunc applies to its input files.
    return name.startswith("__") or name.startswith(".DS")


def _input_files(folder: Path) -> tuple[Path, list[Path]]:
    files = sorted(p for p in folder.iterdir() if p.is_file() and not _skipped_by_generator(p.name))
    legacy = folder / "input"
    if not files and legacy.is_dir():
        return legacy, _input_files(legacy)[1]
    return folder, files


# How inputs commonly name an assembly, mapped to this package's genome names.
_ASSEMBLY_ALIASES = {
    "grch37": "GRCh37", "37": "GRCh37", "hg19": "GRCh37", "b37": "GRCh37", "hs37d5": "GRCh37",
    "grch38": "GRCh38", "38": "GRCh38", "hg38": "GRCh38",
    "chm13": "CHM13-T2T", "chm13-t2t": "CHM13-T2T", "t2t-chm13": "CHM13-T2T",
    "chm13v2": "CHM13-T2T", "t2t": "CHM13-T2T", "hs1": "CHM13-T2T",
    "mm9": "mm9", "mm10": "mm10", "grcm38": "mm10", "mm39": "mm39", "grcm39": "mm39",
    "rn6": "rn6", "rn7": "rn7",
}


def assembly_of(raw: str) -> str | None:
    """The assembly a declared name refers to, or None if it is not clear."""
    token = raw.strip().lower()
    if token in _ASSEMBLY_ALIASES:
        return _ASSEMBLY_ALIASES[token]
    # A VCF ##reference value is usually a path or URL: look for a known name
    # inside it as a whole word. Bare numbers ("37") are too easy to hit by
    # accident there, so only longer names count.
    hits = {
        assembly for alias, assembly in _ASSEMBLY_ALIASES.items()
        if len(alias) > 2 and re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", token)
    }
    return hits.pop() if len(hits) == 1 else None


def _is_indel(ref: str, alt: str) -> bool:
    # VCF indels carry an anchor base (A>AT); MAF and simple text use "-".
    alt = alt.split(",")[0]
    return ref in ("-", "") or alt in ("-", "") or len(ref) != len(alt)


def _scan_vcf(path: Path, samples: set, preview: list, declared: set, counts: dict) -> None:
    name = path.name.split(".")[0]
    if name not in samples and len(preview) < PREVIEW_SAMPLES:
        preview.append(name)
    samples.add(name)
    with open(path, "r", errors="replace") as handle:
        for line in handle:
            if line.startswith("##reference=") or line.startswith("##assembly="):
                declared.add(line.split("=", 1)[1].strip())
            elif line.strip() and not line.startswith("#"):
                counts["records"] += 1
                fields = line.split("\t")
                if len(fields) > 4 and _is_indel(fields[3].strip(), fields[4].strip()):
                    counts["indels"] += 1


# Where convertMAF() and convertTxt() read each field (0-based).
_LAYOUTS = {
    # MAF: header row; Tumor_Sample_Barcode is column 16, NCBI_Build 4,
    # Reference_Allele 11 and Tumor_Seq_Allele2 13.
    "MAF": {"sep": "\t", "header": True, "sample": 15, "assembly": 3, "ref": 10, "alt": 12},
    # Simple text, whitespace separated: project, sample, ID, genome, type,
    # chromosome, start, end, ref, alt.
    "Txt": {"sep": None, "header": False, "sample": 1, "assembly": 3, "ref": 8, "alt": 9},
}


def _scan_columns(path: Path, layout: dict, samples: set, preview: list,
                  declared: set, counts: dict) -> None:
    sep, column = layout["sep"], layout["sample"]
    header_pending = layout["header"]
    ref_col, alt_col = layout["ref"], layout["alt"]
    with open(path, "r", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            if header_pending:
                header_pending = False
                continue
            fields = line.rstrip("\n").split(sep)
            if len(fields) <= column:
                continue
            counts["records"] += 1
            sample = fields[column]
            if sample not in samples:
                samples.add(sample)
                if len(preview) < PREVIEW_SAMPLES:
                    preview.append(sample)
            if len(fields) > layout["assembly"] and len(declared) < 10:
                declared.add(fields[layout["assembly"]])
            if len(fields) > max(ref_col, alt_col) and _is_indel(fields[ref_col], fields[alt_col]):
                counts["indels"] += 1


def _inspect_calls(path: str) -> dict:
    """Recognize a folder of variant calls, as SigProfilerMatrixGenerator reads it."""
    target = Path(path)
    if target.is_file():
        raise InputError(
            "SigProfilerMatrixGenerator reads every file in a folder, so choose "
            f"the folder that holds this file instead: {target.parent}"
        )
    if not target.is_dir():
        raise InputError(f"this folder does not exist: {path}")

    source, files = _input_files(target)
    by_format: dict[str, list[Path]] = {}
    other: list[str] = []
    for file in files:
        file_format = RECOGNIZED_EXTENSIONS.get(file.suffix.lower())
        if file_format:
            by_format.setdefault(file_format, []).append(file)
        elif not file.name.startswith("."):
            other.append(file.name)

    if not by_format:
        raise InputError(
            f"no .vcf, .maf or .txt files in {source}. (The ICGC .tsv format "
            "is no longer supported; convert it to VCF, MAF or Txt first.)"
        )
    if len(by_format) > 1:
        found = ", ".join(sorted(by_format))
        raise InputError(
            f"this folder mixes formats ({found}). SigProfilerMatrixGenerator "
            "reads one format per run, so put each format in its own folder."
        )

    (file_format, matched), = by_format.items()
    samples: set = set()
    preview: list = []
    declared: set = set()
    counts = {"records": 0, "indels": 0}
    for file in matched:
        if file_format == "VCF":
            # One sample per VCF, named after the file, as convertVCF() does.
            # The assembly, if any, is in a ##reference or ##assembly header.
            _scan_vcf(file, samples, preview, declared, counts)
        else:
            _scan_columns(file, _LAYOUTS[file_format], samples, preview, declared, counts)

    # The assembly the calls say they were made against, when they all agree.
    assemblies = {assembly_of(value) for value in declared}
    assembly = assemblies.pop() if len(assemblies) == 1 else None

    return {
        "assembly": assembly,
        "declared_assembly": sorted(declared)[:3],
        "path": str(target),
        "source": str(source),
        "format": file_format,
        "file_count": len(matched),
        "sample_count": len(samples),
        "samples_preview": preview[:PREVIEW_SAMPLES],
        "records": counts["records"],
        # Insertions and deletions among them: without any, a run makes no ID
        # matrices (and ID89/ID476, when asked for, are all zeros).
        "indels": counts["indels"],
        "other_files": other[:5],
        "other_count": len(other),
    }


# What each number of matrix rows means to SigProfilerExtractor (sigpro.py).
CONTEXT_BY_ROWS = {96: "SBS96", 288: "SBS288", 384: "SBS384", 1536: "SBS1536", 4608: "SBS4608",
                   78: "DBS78", 83: "ID83", 48: "CNV48", 32: "SV32"}


def _missing(value: str) -> bool:
    return value.strip().lower() in ("", "nan", "na")


def _inspect_matrix(path: str) -> dict:
    target = Path(path).expanduser()
    if target.is_dir():
        raise InputError("A matrix is one file. Choose the matrix file itself, not its folder.")
    if not target.is_file():
        raise InputError(f"this file does not exist: {path}")
    with open(target, "r", errors="replace") as handle:
        lines = [line.rstrip("\r\n") for line in handle if line.strip()]
    if len(lines) < 2:
        raise InputError("This file has no rows under its header, so it is not a mutation matrix.")
    header = lines[0].split("\t")
    if len(header) < 2:
        raise InputError("This does not look like a tab-separated matrix: the header has one column. "
                         "A matrix has mutation types in the first column and one column per sample.")
    samples = header[1:]
    rows = [line.split("\t") for line in lines[1:]]
    totals = [0.0] * len(samples)
    missing = [0] * len(samples)
    for row_number, row in enumerate(rows, start=2):
        for j in range(len(samples)):
            value = row[j + 1] if j + 1 < len(row) else ""
            if _missing(value):
                missing[j] += 1
                continue
            try:
                totals[j] += float(value)
            except ValueError:
                raise InputError(f"Row {row_number} has a value that is not a number for sample "
                                 f"{samples[j]}: {value!r}.") from None
    empty = [s for s, m in zip(samples, missing) if m == len(rows)]
    partial = [s for s, m in zip(samples, missing) if 0 < m < len(rows)]
    if partial:
        raise InputError(f"{len(partial)} sample(s) have missing values, which SigProfilerExtractor "
                         f"refuses: {', '.join(partial[:5])}.")
    zero = [s for s, t, m in zip(samples, totals, missing) if m == 0 and t == 0]
    kept = [s for s in samples if s not in empty and s not in zero]
    if not kept:
        raise InputError("Every sample in this matrix is empty or has no mutations.")
    context = CONTEXT_BY_ROWS.get(len(rows), f"CH{len(rows)}")
    return {
        "input_type": "matrix",
        "path": str(target),
        "format": context,
        "contexts": [context],
        "known_context": len(rows) in CONTEXT_BY_ROWS,
        "rows": len(rows),
        "sample_count": len(kept),
        "samples_preview": kept[:PREVIEW_SAMPLES],
        "records": int(sum(t for s, t in zip(samples, totals) if s in kept)),
        "empty_samples": empty[:10],
        "zero_samples": zero[:10],
        "dropped_count": len(empty) + len(zero),
    }


def _inspect_bedpe(path: str) -> dict:
    target = Path(path).expanduser()
    if target.is_file():
        raise InputError("Structural variants are read from a folder of BEDPE files. "
                         f"Choose the folder that holds this file instead: {target.parent}")
    if not target.is_dir():
        raise InputError(f"this folder does not exist: {path}")
    files = sorted(p for p in target.iterdir() if p.is_file() and p.suffix.lower() in (".bedpe", ".vcf"))
    if not files:
        raise InputError(f"no .bedpe (or SV .vcf) files in {target}.")
    records = 0
    for f in files:
        with open(f, "r", errors="replace") as handle:
            records += sum(1 for line in handle if line.strip() and not line.startswith("#"))
    return {
        "input_type": "bedpe",
        "path": str(target),
        "format": "SV32",
        "contexts": ["SV32"],
        "file_count": len(files),
        "sample_count": len(files),
        "samples_preview": [f.name.split(".")[0] for f in files[:PREVIEW_SAMPLES]],
        "records": records,
        # SigProfilerExtractor writes SV_Matrices beside the folder.
        "writes_beside": str(target.parent / "SV_Matrices"),
        "writable": os.access(target.parent, os.W_OK),
    }


def _inspect_seg(path: str) -> dict:
    target = Path(path).expanduser()
    if target.is_dir():
        raise InputError("Copy-number segments are one file. Choose the segmentation file itself.")
    if not target.is_file():
        raise InputError(f"this file does not exist: {path}")
    with open(target, "r", errors="replace") as handle:
        lines = [line.rstrip("\r\n") for line in handle if line.strip()]
    if len(lines) < 2:
        raise InputError("This file has no segments under its header.")
    header = [h.strip().lower() for h in lines[0].split("\t")]
    samples: list[str] = []
    column = next((i for i, h in enumerate(header) if h in ("sample", "sample_id", "id", "tumor_sample")), None)
    if column is not None:
        seen = set()
        for line in lines[1:]:
            fields = line.split("\t")
            if len(fields) > column and fields[column] not in seen:
                seen.add(fields[column])
                samples.append(fields[column])
    return {
        "input_type": "seg",
        "path": str(target),
        "format": "CNV48",
        "contexts": ["CNV48"],
        "records": len(lines) - 1,
        "sample_count": len(samples) or None,
        "samples_preview": samples[:PREVIEW_SAMPLES],
    }


def inspect(input_type: str, path: str) -> dict:
    """Recognize the input at ``path`` for a run of ``input_type``."""
    path = str(path or "").strip()
    if not path:
        raise InputError("choose the input first")
    if input_type == "vcf":
        found = _inspect_calls(path)
        found["input_type"] = "vcf"
        # SigProfilerMatrixGenerator writes input/ and output/ into this folder.
        found["writable"] = os.access(found["path"], os.W_OK)
        return found
    if input_type == "matrix":
        return _inspect_matrix(path)
    if input_type == "bedpe":
        return _inspect_bedpe(path)
    if input_type == "seg":
        return _inspect_seg(path)
    raise InputError(f"unknown input type: {input_type}")


# --------------------------------------------------------------------- examples

def _data_dir() -> Path:
    import SigProfilerExtractor

    return Path(SigProfilerExtractor.__file__).resolve().parent / "data"


# The example data SigProfilerExtractor ships (sigpro.importdata), with
# settings that finish in minutes. VCF examples are copied before a run,
# because SigProfilerMatrixGenerator writes into the folder it reads.
_EXAMPLES = (
    {"id": "sbs96", "label": "21 breast cancer genomes", "detail": "SBS96 matrix",
     "input_type": "matrix", "data": "TextInput/Samples_SBS.txt", "project": "Breast_SBS96"},
    {"id": "vcf", "label": "5 genomes from VCFs", "detail": "SBS96, DBS78 and ID83 from variant calls (GRCh37)",
     "input_type": "vcf", "data": "VCFInput", "project": "VCF_example", "reference_genome": "GRCh37"},
    {"id": "dbs78", "label": "Doublet substitutions", "detail": "DBS78 matrix",
     "input_type": "matrix", "data": "TextInput/Samples_DBS.txt", "project": "DBS78_example"},
    {"id": "id83", "label": "Small insertions and deletions", "detail": "ID83 matrix",
     "input_type": "matrix", "data": "TextInput/Samples_ID.txt", "project": "ID83_example"},
    {"id": "cnv48", "label": "Copy-number profiles", "detail": "CNV48 matrix, 108 tumours",
     "input_type": "matrix", "data": "TextInput/Samples_CNV.txt", "project": "CNV48_example",
     "opportunity_genome": "GRCh37"},
    {"id": "sv32", "label": "Structural variants", "detail": "SV32 matrix",
     "input_type": "matrix", "data": "TextInput/Samples_SV.txt", "project": "SV32_example",
     "opportunity_genome": "GRCh38"},
    {"id": "battenberg", "label": "Battenberg segments", "detail": "copy-number calls to CNV48",
     "input_type": "seg", "seg_caller": "BATTENBERG", "data": "CNVInput/Battenberg_test.tsv",
     "project": "Battenberg_example", "opportunity_genome": "GRCh37"},
)


def examples() -> list[dict]:
    """The bundled examples that are present in this install."""
    found = []
    base = _data_dir()
    for example in _EXAMPLES:
        path = base / example["data"]
        if path.exists():
            item = {k: v for k, v in example.items() if k != "data"}
            item["input_data"] = str(path)
            item["output"] = str(Path.home() / "SigProfilerExtractor_example" / example["project"])
            found.append(item)
    return found
