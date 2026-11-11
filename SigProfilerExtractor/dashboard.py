"""Build a self-contained interactive report from completed extraction output."""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import re
from importlib import resources
from pathlib import Path
from typing import Iterable


DASHBOARD_FILENAME = "reports.html"
_ASSET_PACKAGE = "SigProfilerExtractor.dashboard_assets"
_RANK_DIRECTORY = re.compile(r"_(\d+)_Signatures$")
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_INTEGER = re.compile(r"^[+-]?\d+$")
_MAX_SAFE_INTEGER = 2**53 - 1


class DashboardError(RuntimeError):
    """Raised when completed output cannot be represented as a dashboard."""


def _coerce(value: str):
    text = value.strip()
    if text == "":
        return None
    if _INTEGER.fullmatch(text):
        number = int(text)
        return number if abs(number) <= _MAX_SAFE_INTEGER else text
    if _NUMBER.fullmatch(text):
        number = float(text)
        if math.isfinite(number):
            return number
    return text


def _read_table(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    with path.open(encoding="utf-8-sig", newline="") as handle:
        first_line = handle.readline()
        if not first_line:
            return {"columns": [], "rows": [], "source": path.name}
        delimiter = "\t" if first_line.count("\t") >= first_line.count(",") else ","
        handle.seek(0)
        rows = list(csv.reader(handle, delimiter=delimiter))
    if not rows:
        return {"columns": [], "rows": [], "source": path.name}
    width = max(len(row) for row in rows)
    columns = [cell.strip() or "Index" for cell in rows[0]]
    columns.extend(f"Column {index + 1}" for index in range(len(columns), width))
    values = []
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue
        padded = row + [""] * (width - len(row))
        values.append([_coerce(cell) for cell in padded])
    return {"columns": columns, "rows": values, "source": path.name}


def _first(paths: Iterable[Path], excluded: Iterable[str] = ()) -> Path | None:
    excluded = tuple(excluded)
    return next(
        (
            path
            for path in sorted(paths)
            if path.is_file() and not any(token in path.name for token in excluded)
        ),
        None,
    )


def _relative(path: Path | None, root: Path) -> str | None:
    return path.relative_to(root).as_posix() if path is not None else None


def _profile_payload(path: Path | None, root: Path, warnings: list[str]) -> dict | None:
    if path is None:
        return None
    try:
        from sigProfilerPlotting.web import load_matrix, render_sample

        matrix = load_matrix(path)
        figures = {}
        for name in matrix.columns:
            figures[name] = render_sample(matrix, name, unit="proportion")
        return {
            "source": _relative(path, root),
            "context": matrix.context,
            "labels_count": len(matrix.labels),
            "names": list(matrix.columns),
            "figures": figures,
            "table": _read_table(path),
            # SigProfilerPlotting 1.5.0 introduced the public dashboard API;
            # its post-release master adds per-matrix warnings. Accept both
            # shapes so the report works with the released minimum version.
            "warnings": list(getattr(matrix, "warnings", ())),
        }
    except Exception as exc:
        warnings.append(f"Could not render {path.name}: {exc}")
        return {
            "source": _relative(path, root),
            "context": None,
            "labels_count": 0,
            "names": [],
            "figures": {},
            "table": _read_table(path),
            "warnings": [str(exc)],
        }


def _rank_from_directory(path: Path) -> int | None:
    match = _RANK_DIRECTORY.search(path.name)
    return int(match.group(1)) if match else None


def _selected_rank(table: dict | None) -> int | None:
    if not table or not table["rows"]:
        return None
    for row in table["rows"]:
        value = str(row[0])
        if value.endswith("*"):
            match = re.search(r"\d+", value)
            return int(match.group()) if match else None
    columns = table["columns"]
    pvalue_index = columns.index("P-value") if "P-value" in columns else None
    if pvalue_index is not None:
        for row in table["rows"]:
            if pvalue_index < len(row) and str(row[pvalue_index]).startswith("Most Stab"):
                match = re.search(r"\d+", str(row[0]))
                return int(match.group()) if match else None
    return None


def _solution_payload(path: Path, root: Path, selected_rank: int | None) -> dict:
    rank = _rank_from_directory(path)
    warnings: list[str] = []
    signatures = _first(
        (path / "Signatures").glob("*_Signatures.txt"), ("SEM_Error",)
    )
    activities = _first(
        (path / "Activities").glob("*_NMF_Activities.txt"), ("SEM_Error",)
    )
    stats = path / "Solution_Stats"
    return {
        "rank": rank,
        "selected": rank == selected_rank,
        "signatures": _profile_payload(signatures, root, warnings),
        "activities": _read_table(activities),
        "signature_stats": _read_table(
            _first(stats.glob("*_Signatures_stats.txt"))
        ),
        "sample_stats": _read_table(_first(stats.glob("*_Samples_stats.txt"))),
        "convergence": _read_table(
            _first(stats.glob("*_NMF_Convergence_Information.txt"))
        ),
        "source": _relative(path, root),
        "warnings": warnings,
    }


def _selected_bundle(path: Path, root: Path, kind: str) -> dict:
    warnings: list[str] = []
    signatures = _first(
        (path / "Signatures").glob("*_Signatures.txt"), ("SEM_Error",)
    )
    activity_paths = list((path / "Activities").glob("*.txt"))
    preferred = [item for item in activity_paths if "Activities_refit" in item.name]
    if kind == "cosmic":
        preferred = [item for item in activity_paths if "Activities" in item.name]
    activities = _first(preferred) or _first(
        (item for item in activity_paths if "Activities" in item.name),
        ("Probabilities",),
    )
    stats = path / "Solution_Stats"
    return {
        "kind": kind,
        "name": path.name,
        "source": _relative(path, root),
        "signatures": _profile_payload(signatures, root, warnings),
        "activities": _read_table(activities),
        "sample_stats": _read_table(_first(stats.glob("*_Samples_Stats*.txt"))),
        "mapping": _read_table(_first(path.glob("*map_to_COSMIC*.csv"))),
        "warnings": warnings,
    }


def _sample_summary(path: Path | None) -> dict:
    table = _read_table(path)
    if not table or len(table["columns"]) < 2:
        return {"samples": 0, "channels": 0, "totals": []}
    names = table["columns"][1:]
    totals = [0.0] * len(names)
    for row in table["rows"]:
        for index, value in enumerate(row[1 : len(names) + 1]):
            if isinstance(value, (int, float)):
                totals[index] += float(value)
    return {
        "samples": len(names),
        "channels": len(table["rows"]),
        "totals": [
            {"sample": name, "mutations": round(total, 8)}
            for name, total in zip(names, totals)
        ],
    }


def _context_payload(path: Path, root: Path) -> dict:
    overall = _read_table(path / "All_solutions_stat.csv")
    selected_rank = _selected_rank(overall)
    solution_dirs = [
        item
        for item in (path / "All_Solutions").glob("*_Signatures")
        if item.is_dir() and _rank_from_directory(item) is not None
    ]
    solutions = [
        _solution_payload(item, root, selected_rank)
        for item in sorted(solution_dirs, key=lambda item: _rank_from_directory(item) or 0)
    ]
    if selected_rank is None:
        selected = next((item["rank"] for item in solutions if item["selected"]), None)
        selected_rank = selected if selected is not None else (
            solutions[0]["rank"] if solutions else None
        )
        for item in solutions:
            item["selected"] = item["rank"] == selected_rank

    suggested = path / "Suggested_Solution"
    selected_bundles = []
    if suggested.is_dir():
        for item in sorted(suggested.iterdir()):
            if not item.is_dir():
                continue
            kind = "cosmic" if item.name.startswith("COSMIC_") else "denovo"
            selected_bundles.append(_selected_bundle(item, root, kind))

    return {
        "name": path.name,
        "source": _relative(path, root),
        "selected_rank": selected_rank,
        "overall_stats": overall,
        "sample_summary": _sample_summary(path / "Samples.txt"),
        "solutions": solutions,
        "selected_bundles": selected_bundles,
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _asset(name: str) -> str:
    return resources.files(_ASSET_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def _safe_json(value) -> str:
    from plotly.utils import PlotlyJSONEncoder

    return (
        json.dumps(
            value,
            cls=PlotlyJSONEncoder,
            allow_nan=False,
            separators=(",", ":"),
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def create_dashboard(
    output: str | os.PathLike,
    filename: str = DASHBOARD_FILENAME,
) -> Path:
    """Create an offline dashboard for one completed extraction output folder.

    The generated HTML embeds its data and Plotly runtime. It can be opened
    directly from disk and does not start a server or send results elsewhere.
    """

    root = Path(output).expanduser().resolve()
    if not root.is_dir():
        raise DashboardError(f"Extraction output directory does not exist: {root}")
    if Path(filename).name != filename or not filename.lower().endswith(".html"):
        raise DashboardError("Dashboard filename must be a plain .html filename.")

    context_dirs = sorted(
        item
        for item in root.iterdir()
        if item.is_dir()
        and (item / "All_solutions_stat.csv").is_file()
        and (item / "All_Solutions").is_dir()
    )
    if not context_dirs:
        raise DashboardError(
            f"No completed mutation-context results were found under {root}."
        )

    try:
        import SigProfilerExtractor
        import sigProfilerPlotting
        from plotly.offline import get_plotlyjs
    except ImportError as exc:  # pragma: no cover - packaging guards this dependency
        raise DashboardError(
            "Dashboard generation requires SigProfilerPlotting 1.5.0 or newer."
        ) from exc

    payload = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project": root.name,
        "extractor_version": SigProfilerExtractor.__version__,
        "plotting_version": sigProfilerPlotting.__version__,
        "contexts": [_context_payload(path, root) for path in context_dirs],
        "job_metadata": _read_text(root / "JOB_METADATA.txt")
        if (root / "JOB_METADATA.txt").is_file()
        else "",
        "seeds": _read_table(root / "Seeds.txt"),
    }

    html = _asset("template.html")
    replacements = {
        "{{TITLE}}": f"{root.name} - SigProfilerExtractor results",
        "{{STYLES}}": _asset("styles.css"),
        "{{PLOTLY_JS}}": get_plotlyjs(),
        "{{DASHBOARD_DATA}}": _safe_json(payload),
        "{{APP_JS}}": _asset("app.js"),
    }
    for marker, value in replacements.items():
        html = html.replace(marker, value)

    destination = root / filename
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(html, encoding="utf-8")
    os.replace(temporary, destination)
    return destination


__all__ = ["DASHBOARD_FILENAME", "DashboardError", "create_dashboard"]
