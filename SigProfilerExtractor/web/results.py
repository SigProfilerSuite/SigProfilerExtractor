"""Read a SigProfilerExtractor output folder for the Results tab.

The interactive dashboard is SigProfilerExtractor's own ``reports.html``,
shown as-is; this module finds it and everything around it: each context's
suggested solution, its PDF plots and its tables. It also knows which files
SigProfilerExtractor writes into an output folder, so that "replace the
earlier results" and "delete this run" remove those and nothing else.
"""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

DASHBOARD = "reports.html"

# What SigProfilerExtractor writes at the top of an output folder.
_ROOT_FILES = ("JOB_METADATA.txt", "Seeds.txt", DASHBOARD, DASHBOARD + ".tmp")
# <CALLER>.CNV48.matrix.tsv, written for segmentation input.
_CNV_MATRIX = re.compile(r"^[A-Z_]+\.CNV48\.matrix\.tsv$")
# A context folder SigProfilerExtractor moved aside on a rerun (sigpro.move_previous_results).
_PREVIOUS = re.compile(r"^(?P<context>[A-Za-z]+\d+)_previous_\d{8}-\d{6}(_\d+)?$")


class ResultsError(ValueError):
    pass


def _real_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def _is_context_dir(path: Path) -> bool:
    return _real_dir(path) and ((path / "All_solutions_stat.csv").is_file() or _real_dir(path / "All_Solutions"))


def _context_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if _is_context_dir(p) and not _PREVIOUS.match(p.name))


def _previous_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if _real_dir(p) and _PREVIOUS.match(p.name))


def _generated(root: Path) -> list[Path]:
    """Everything in ``root`` that SigProfilerExtractor wrote, by its own names."""
    found = [root / name for name in _ROOT_FILES if (root / name).is_file()]
    found += [p for p in root.iterdir() if p.is_file() and _CNV_MATRIX.match(p.name)]
    found += _context_dirs(root) + _previous_dirs(root)
    return found


def earlier_results(output_dir: str) -> dict:
    """Whether ``output_dir`` already holds a SigProfilerExtractor run's results."""
    root = Path(output_dir).expanduser()
    if not _real_dir(root):
        return {"found": False, "contexts": []}
    contexts = [p.name for p in _context_dirs(root)]
    found = bool(contexts) or (root / "JOB_METADATA.txt").is_file()
    return {"found": found, "contexts": contexts}


def next_free_folder(output_dir: str) -> str:
    """A sibling of ``output_dir`` holding no results: name_2, name_3, ..."""
    root = Path(output_dir).expanduser()
    numbered = re.fullmatch(r"(.+)_(\d+)", root.name)
    base, n = (numbered.group(1), int(numbered.group(2)) + 1) if numbered else (root.name, 2)
    while earlier_results(str(root.with_name(f"{base}_{n}")))["found"]:
        n += 1
    return str(root.with_name(f"{base}_{n}"))


def replace_problem(output_dir: str, input_data: str) -> str | None:
    """Why earlier results in ``output_dir`` must not be removed, or None."""
    root = Path(output_dir).expanduser().resolve()
    data = Path(input_data).expanduser().resolve()
    if data == root or root in data.parents:
        return ("The input is inside this output folder, so its earlier results are not "
                "removed automatically. Choose a different output folder.")
    return None


def clear_earlier_results(output_dir: str, input_data: str) -> list[str]:
    """Remove what SigProfilerExtractor wrote into ``output_dir``; keep the rest."""
    problem = replace_problem(output_dir, input_data)
    if problem:
        raise ResultsError(problem)
    root = Path(output_dir).expanduser()
    if not _real_dir(root):
        return []
    removed = []
    for path in _generated(root):
        if _real_dir(path):
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path.name)
    return removed


def generated_size(output_dir: str) -> dict:
    root = Path(output_dir).expanduser()
    files = size = 0
    if _real_dir(root):
        for path in _generated(root):
            for f in ([p for p in path.rglob("*") if p.is_file()] if _real_dir(path) else [path]):
                files += 1
                try:
                    size += f.lstat().st_size
                except OSError:
                    pass
    return {"files": files, "bytes": size}


def delete_output(output_dir: str, input_data: str) -> list[str]:
    """A run's results go, and the folder too if nothing else is left in it."""
    removed = clear_earlier_results(output_dir, input_data)
    root = Path(output_dir).expanduser()
    if _real_dir(root):
        try:
            root.rmdir()
        except OSError:
            pass
    return removed


# ------------------------------------------------------------------ scanning

def _read_rows(path: Path, delimiter: str) -> list[list[str]]:
    with open(path, newline="", errors="replace") as handle:
        return [row for row in csv.reader(handle, delimiter=delimiter) if row]


def _suggested_rank(stat_file: Path) -> tuple[int | None, list[int]]:
    """The rank SigProfilerExtractor chose (its row ends in '*') and every rank tried."""
    try:
        rows = _read_rows(stat_file, ",")
    except OSError:
        return None, []
    chosen, ranks = None, []
    for row in rows[1:]:
        label = row[0].strip()
        try:
            rank = int(label.rstrip("*"))
        except ValueError:
            continue
        ranks.append(rank)
        if label.endswith("*"):
            chosen = rank
    return chosen, ranks


def _header_names(path: Path) -> list[str]:
    try:
        with open(path, errors="replace") as handle:
            return handle.readline().rstrip("\r\n").split("\t")[1:]
    except OSError:
        return []


def _cosmic_matches(solution: Path) -> list[str]:
    signatures = sorted((solution / "Signatures").glob("*_Signatures.txt")) if _real_dir(solution / "Signatures") else []
    return _header_names(signatures[0]) if signatures else []



# ------------------------------------------------------ de novo vs COSMIC

_COSMIC_GENOMES = ("GRCh37", "GRCh38", "mm9", "mm10", "mm39", "rn6", "rn7")


def run_settings(root: Path) -> dict:
    """The run's parameters, as JOB_METADATA.txt records them ("\tkey: value")."""
    settings: dict = {}
    try:
        lines = (root / "JOB_METADATA.txt").read_text(errors="replace").splitlines()
    except OSError:
        return settings
    for line in lines:
        if line.startswith("\t") and ": " in line:
            key, value = line.strip().split(": ", 1)
            settings.setdefault(key, value.split(";")[0].strip())
    return settings


def cosmic_catalogue(channels: int, settings: dict) -> tuple[Path | None, str]:
    """The COSMIC catalogue SigProfilerAssignment matched a context against.

    Mirrors SigProfilerAssignment's choice (decompose_subroutines): SBS96 and
    DBS78 use the run's genome (the reference genome for VCF input, otherwise
    the COSMIC reference genome) and its exome variant; ID83 and CNV48 use
    GRCh37, SV32 GRCh38. SBS288 and SBS1536 are matched as SBS96 unless the
    run turned collapse_to_SBS96 off. Returns (path or None, label).
    """
    try:
        import SigProfilerAssignment
    except ImportError:
        return None, ""
    base = Path(SigProfilerAssignment.__file__).resolve().parent / "data" / "Reference_Signatures"
    try:
        version = float(settings.get("cosmic_version", "3.6"))
    except ValueError:
        version = 3.6
    genome = (settings.get("reference_genome") if settings.get("input_type") == "vcf"
              else settings.get("opportunity_genome")) or "GRCh37"
    if genome not in _COSMIC_GENOMES:
        genome = "GRCh37"
    exome = settings.get("exome") == "True"
    collapse = settings.get("collapse_to_SBS96", "True") != "False"
    if channels in (288, 1536) and collapse:
        channels = 96
    if channels == 96:
        kind, build = "SBS", genome
    elif channels in (288, 1536):
        kind, build, exome = f"SBS{channels}", "GRCh37", False
    elif channels == 78:
        kind, build, version = "DBS", genome, (version if version >= 3 else 3.6)
    elif channels == 83:
        kind, build, exome, version = "ID", "GRCh37", False, (version if version >= 3 else 3.6)
    elif channels == 48:
        kind, build, exome, version = "CN", "GRCh37", False, (version if version >= 3.3 else 3.6)
    elif channels == 32:
        kind, build, exome, version = "SV", "GRCh38", False, (version if version >= 3.4 else 3.6)
    else:
        return None, ""
    name = f"COSMIC_v{version:g}_{kind}_{build}{'_exome' if exome else ''}.txt"
    label = f"COSMIC v{version:g} {kind} ({build}{', exome' if exome else ''})"
    path = base / build / name
    return (path if path.is_file() else None), label


def _read_matrix(path: Path) -> tuple[list[str], list[str], list[list[float]]]:
    """Row labels, column names and columns of a tab-separated signature matrix."""
    rows = _read_rows(path, "\t")
    names = [n.strip() for n in rows[0][1:]]
    labels, columns = [], [[] for _ in names]
    for row in rows[1:]:
        labels.append(row[0].strip())
        for j in range(len(names)):
            try:
                columns[j].append(float(row[j + 1]))
            except (IndexError, ValueError):
                columns[j].append(0.0)
    return labels, names, columns


def _to_sbs96(label: str) -> str:
    """An SBS288 ("T:A[C>A]A") or SBS1536 ("AA[C>A]AA") channel's SBS96 channel."""
    label = label.split(":", 1)[-1]
    return label[1:-1] if len(label) == 9 else label


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def closest_cosmic(signature: dict[str, float], catalogue: Path, top: int = 3) -> list[dict]:
    """The COSMIC signatures most similar to one de novo signature (cosine)."""
    labels, names, columns = _read_matrix(catalogue)
    if not set(labels) <= set(signature):
        collapsed: dict[str, float] = {}
        for label, value in signature.items():
            collapsed[_to_sbs96(label)] = collapsed.get(_to_sbs96(label), 0.0) + value
        signature = collapsed
    if not set(labels) <= set(signature):
        return []
    vector = [signature[label] for label in labels]
    scored = sorted(((_cosine(vector, col), name) for name, col in zip(names, columns)), reverse=True)
    return [{"name": name, "cosine": round(score, 3)} for score, name in scored[:top]]


_COMPONENT = re.compile(r"Signature\s+(?P<name>\S+)\s+\((?P<percent>[\d.]+)%\)")


def _decompositions(mapping: Path) -> dict[str, dict]:
    """SigProfilerAssignment's split of each de novo signature into COSMIC ones."""
    rows = _read_rows(mapping, ",")
    header = [h.strip() for h in rows[0]]
    found = {}
    for row in rows[1:]:
        cells = dict(zip(header, (c.strip() for c in row)))
        label = cells.get("De novo extracted", "")
        parts = [{"name": m.group("name"), "percent": float(m.group("percent"))}
                 for m in _COMPONENT.finditer(cells.get("Global NMF Signatures", ""))]
        fit = {}
        for key, column in (("cosine", "Cosine Similarity"), ("correlation", "Correlation"),
                            ("l1", "L1 Error %"), ("l2", "L2 Error %"), ("kl", "KL Divergence")):
            try:
                fit[key] = float(cells.get(column, ""))
            except ValueError:
                pass
        found[label] = {"decomposition": sorted(parts, key=lambda p: -p["percent"]), "fit": fit}
    return found


def cosmic_comparison(folder: Path, settings: dict) -> dict | None:
    """For each de novo signature of the suggested solution: how it splits into
    COSMIC signatures, and the closest single COSMIC signatures."""
    suggested = folder / "Suggested_Solution"
    if not _real_dir(suggested):
        return None
    denovo_files = sorted(suggested.glob("*_De-Novo_Solution/Signatures/*_De-Novo_Signatures.txt"))
    if not denovo_files:
        return None
    labels, names, columns = _read_matrix(denovo_files[0])
    mappings = sorted(suggested.glob("COSMIC_*_Decomposed_Solution/De_Novo_map_to_COSMIC_*.csv"))
    decompositions = _decompositions(mappings[0]) if mappings else {}
    catalogue, label = cosmic_catalogue(len(labels), settings)
    signatures = []
    for name, column in zip(names, columns):
        mapped = next((v for k, v in decompositions.items()
                       if k == name or k.endswith(f"-{name}") or k.endswith(f" {name}")), None)
        signatures.append({
            "name": name,
            "decomposition": mapped["decomposition"] if mapped else [],
            "fit": mapped["fit"] if mapped else {},
            "closest": closest_cosmic(dict(zip(labels, column)), catalogue) if catalogue else [],
        })
    return {"catalogue": label if catalogue else None, "signatures": signatures}

def _file(path: Path, root: Path, group: str) -> dict:
    stat = path.stat()
    return {"path": str(path), "name": path.name, "rel": str(path.relative_to(root)),
            "size": stat.st_size, "modified": stat.st_mtime, "group": group}


def _context(folder: Path, root: Path, settings: dict | None = None) -> dict:
    chosen, ranks = _suggested_rank(folder / "All_solutions_stat.csv")
    samples = _header_names(folder / "Samples.txt")
    suggested = folder / "Suggested_Solution"
    denovo = next((p for p in sorted(suggested.glob("*_De-Novo_Solution"))), None) if _real_dir(suggested) else None
    cosmic = next((p for p in sorted(suggested.glob("COSMIC_*_Decomposed_Solution"))), None) if _real_dir(suggested) else None
    plots, tables = [], []
    for pdf in sorted(folder.rglob("*.pdf")):
        rel = pdf.relative_to(folder)
        if rel.parts[0] == "All_Solutions":
            group = f"Rank {rel.parts[1].rsplit('_', 2)[-2]}" if len(rel.parts) > 1 else "All solutions"
        elif rel.parts[0] == "Suggested_Solution":
            group = "COSMIC decomposition" if "COSMIC" in rel.parts[1] else "De novo solution"
        else:
            group = "Choosing the number of signatures"
        plots.append(_file(pdf, root, group))
    for pattern, group in (("All_solutions_stat.csv", "Choosing the number of signatures"),
                           ("Samples.txt", "Input"),
                           ("Suggested_Solution/*/Signatures/*.txt", "Signatures"),
                           ("Suggested_Solution/*/Activities/*.txt", "Activities"),
                           ("Suggested_Solution/*/Solution_Stats/*", "Statistics"),
                           ("Suggested_Solution/*/*.csv", "COSMIC decomposition")):
        tables += [_file(p, root, group) for p in sorted(folder.glob(pattern)) if p.is_file()]
    return {
        "name": folder.name,
        "suggested_rank": chosen,
        "ranks": ranks,
        "samples": len(samples),
        "denovo_signatures": _cosmic_matches(denovo) if denovo else [],
        "cosmic_signatures": _cosmic_matches(cosmic) if cosmic else [],
        "assigned": bool(cosmic),
        "comparison": cosmic_comparison(folder, settings or {}),
        "plots": plots,
        "tables": tables,
    }


def scan(output_dir: str) -> dict:
    """Everything the Results tab shows for one output folder."""
    root = Path(output_dir).expanduser()
    if not root.is_dir():
        raise ResultsError(f"not a folder: {output_dir}")
    settings = run_settings(root)
    contexts = [_context(folder, root, settings) for folder in _context_dirs(root)]
    if not contexts and not (root / "JOB_METADATA.txt").is_file():
        raise ResultsError("This folder does not hold SigProfilerExtractor results "
                           "(no JOB_METADATA.txt and no context folders such as SBS96).")
    dashboard = root / DASHBOARD
    files = [_file(root / name, root, "Run") for name in ("JOB_METADATA.txt", "Seeds.txt")
             if (root / name).is_file()]
    status = None
    metadata = root / "JOB_METADATA.txt"
    if metadata.is_file():
        # "-------Job Status-------" is a heading; the status is the next line.
        lines = [line.strip() for line in metadata.read_text(errors="replace").splitlines()]
        for i, line in enumerate(lines):
            if "Job Status" in line:
                status = next((later for later in lines[i + 1:] if later), None)
    return {
        "output_dir": str(root),
        "contexts": contexts,
        "dashboard": _file(dashboard, root, "Run") if dashboard.is_file() else None,
        "files": files,
        "job_status": status,
        "previous": [p.name for p in _previous_dirs(root)],
    }


def dashboard_path(path: str) -> Path:
    """The reports.html to show, refusing anything else (it runs scripts)."""
    target = Path(path).expanduser()
    if target.name != DASHBOARD or not target.is_file():
        raise ResultsError("only a SigProfilerExtractor reports.html can be shown here")
    return target
