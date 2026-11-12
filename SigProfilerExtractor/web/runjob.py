"""Subprocess entry point for one Workbench job.

Invoked as ``python -m SigProfilerExtractor.web.runjob <config.json>`` by
jobs.py, in its own process group, so a run that takes hours never blocks the
server and Stop can end SigProfilerExtractor's worker pools with it.

config.json holds ``mode`` and its settings:

* ``run``: ``kwargs`` for sigpro.sigProfilerExtractor (already validated by
  params.validate), plus ``replace_existing`` and ``copy_input``.
* ``install``: install a reference genome for VCF input.
* ``dashboard``: build reports.html for an existing output folder.

SigProfilerExtractor itself is untouched: progress is read from what it
prints (see progress.py). The ``__main__`` guard matters: its worker pools
use the spawn start method, which re-imports this module in every worker.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path


def _say(message: str) -> None:
    print(f"== {message}", flush=True)


def _write_result_atomic(result_path: Path, result: dict) -> None:
    tmp = result_path.with_name(result_path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    os.replace(tmp, result_path)


def _metadata_warnings(output: Path) -> list[str]:
    try:
        lines = (output / "JOB_METADATA.txt").read_text(errors="replace").splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines if line.strip().startswith("WARNING")]


def _summary(output: Path) -> dict:
    from SigProfilerExtractor.web import results

    try:
        scanned = results.scan(str(output))
    except results.ResultsError:
        return {}
    # "found_contexts", not "contexts": the job record already holds the
    # contexts asked for, and a result's keys are merged into it.
    return {
        "found_contexts": [
            {"name": c["name"], "suggested_rank": c["suggested_rank"], "samples": c["samples"],
             "cosmic_signatures": c["cosmic_signatures"]}
            for c in scanned["contexts"]
        ],
        "dashboard": scanned["dashboard"]["path"] if scanned["dashboard"] else None,
    }


def _run(config: dict, result_path: Path) -> None:
    from SigProfilerExtractor import sigpro
    from SigProfilerExtractor.web import results

    kwargs = dict(config["kwargs"])
    output = Path(kwargs["output"]).expanduser()
    started = time.monotonic()

    if config.get("replace_existing"):
        removed = results.clear_earlier_results(str(output), kwargs["input_data"])
        _say(f"removed {len(removed)} earlier results from {output}")
    if config.get("copy_input"):
        # SigProfilerMatrixGenerator writes input/ and output/ into the folder
        # it reads, so a bundled example is copied into this job's folder first.
        copy = result_path.parent / "input"
        if copy.exists():
            shutil.rmtree(copy)
        shutil.copytree(kwargs["input_data"], copy)
        kwargs["input_data"] = str(copy)
        _say(f"copied the example input to {copy}")

    _say("starting SigProfilerExtractor")
    sigpro.sigProfilerExtractor(**kwargs)

    _write_result_atomic(result_path, {
        "status": "done",
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "warnings": _metadata_warnings(output),
        **_summary(output),
    })
    _say(f"finished in {round(time.monotonic() - started)} seconds")


def _install(config: dict, result_path: Path) -> None:
    from SigProfilerExtractor.web import genomes

    started = time.monotonic()
    genome = config["reference_genome"]
    _say(f"installing reference genome {genome}")
    genomes.install(genome, volume=config.get("volume"))
    _write_result_atomic(result_path, {"status": "done", "installed": genome,
                                       "elapsed_seconds": round(time.monotonic() - started, 2)})
    _say("done")


def _dashboard(config: dict, result_path: Path) -> None:
    from SigProfilerExtractor.dashboard import create_dashboard

    started = time.monotonic()
    _say(f"building the results dashboard for {config['output']}")
    path = create_dashboard(config["output"])
    _write_result_atomic(result_path, {"status": "done", "dashboard": str(path),
                                       "elapsed_seconds": round(time.monotonic() - started, 2)})
    _say(f"dashboard written to {path}")


MODES = {"run": _run, "install": _install, "dashboard": _dashboard}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: runjob.py <config.json>", file=sys.stderr)
        return 2
    config_path = Path(argv[0])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    result_path = config_path.with_name("result.json")
    try:
        MODES[config.get("mode", "run")](config, result_path)
    except Exception as exc:  # noqa: BLE001 -- job boundary, must always report back
        traceback.print_exc()
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        if config.get("mode", "run") == "run":
            result["warnings"] = _metadata_warnings(Path(config["kwargs"]["output"]).expanduser())
        _write_result_atomic(result_path, result)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
