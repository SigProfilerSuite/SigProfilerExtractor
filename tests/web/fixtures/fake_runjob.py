"""A stand-in job process for jobs.py tests, with the same contract as the
real SigProfilerExtractor.web.runjob: read a config JSON path from
argv[1], print progress, write result.json next to it.

config keys: "outcome" ("done" | "failed" | "hang"), "sleep_seconds".
The FAKE_RUNJOB_RESULT environment variable, a JSON object, replaces the
result outright (for runs started from the page, whose config the test does
not write).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    config_path = Path(argv[0])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    result_path = config_path.with_name("result.json")

    print("== step 1/1: working", flush=True)
    time.sleep(config.get("sleep_seconds", 0))

    outcome = config.get("outcome", "done")
    if outcome == "hang":
        time.sleep(3600)
        return 0

    tmp = result_path.with_name(result_path.name + f".tmp{os.getpid()}")
    forced = os.environ.get("FAKE_RUNJOB_RESULT")
    if forced:
        tmp.write_text(forced)
        os.replace(tmp, result_path)
        return 0 if json.loads(forced)["status"] == "done" else 1
    if outcome == "failed":
        tmp.write_text(json.dumps({"status": "failed", "error": "simulated failure"}))
        os.replace(tmp, result_path)
        return 1

    tmp.write_text(json.dumps({"status": "done", "found_contexts": [{"name": "SBS96", "suggested_rank": 3}], "elapsed_seconds": 0.0}))
    os.replace(tmp, result_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
