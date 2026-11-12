"""Turn a running job's log into progress the Monitor tab can draw.

SigProfilerExtractor is not instrumented for the Workbench; it already says
where it is. For each mutation context in turn it prints, for every number of
signatures (rank) it tries:

    Extracting signature 3 for mutation type 96
    process 1 continues please wait...          (once per NMF replicate)
    Time taken to collect 10 iterations for 3 signatures is 10.14 seconds
    The reconstruction error is ..., average process stability is ...

then assigns the chosen solution to COSMIC (" De Novo Fitting .....",
" Decomposing De Novo Signatures .....", " Assigning decomposed signature")
before the next context. After the last one it builds reports.html and prints
"Interactive results dashboard: <path>". Context names come out in its
internal shorthand: "96" for SBS96, "DINUC" for DBS78, "ID" for ID83.
"""

from __future__ import annotations

import re

_EXTRACT = re.compile(r"^Extracting signature (\d+) for mutation type (\S+)")
_REPLICATE = re.compile(r"^process \d+ continues please wait")
_RANK_TIME = re.compile(r"^Time taken to collect \d+ iterations for (\d+) signatures is ([\d.]+) seconds")
_RANK_DONE = re.compile(r"^the minimum process stability is .* for (\d+) signatures")
_SKIPPED = re.compile(r"^(?:Context (\S+) is not available|Sample is not a no[n]?zero matrix for the mutation context (\S+))")
_ASSIGN = ("De Novo Fitting", "Decomposing De Novo Signatures", "Assigning decomposed signature")
_DASHBOARD = "Interactive results dashboard:"
_DONE = "Your Job Is Successfully Completed"
_MATRICES = "Starting matrix generation"


def context_name(label: str) -> str:
    """SigProfilerExtractor's printed shorthand -> the context's folder name."""
    label = label.strip()
    named = {"DINUC": "DBS78", "ID": "ID83", "CNV": "CNV48", "SV": "SV32"}
    if label in named:
        return named[label]
    if label.isdigit():
        return {"78": "DBS78", "83": "ID83", "48": "CNV48", "32": "SV32"}.get(label, f"SBS{label}")
    return label


def parse(text: str, job: dict) -> dict:
    """Progress of one run, from its log so far and its record (job meta)."""
    planned = list(job.get("contexts") or [])
    low = int(job.get("minimum_signatures") or 1)
    high = int(job.get("maximum_signatures") or low)
    samples = job.get("samples")
    if samples:
        low, high = min(low, samples), min(high, samples)
    ranks_total = max(1, high - low + 1)
    replicates_total = int(job.get("nmf_replicates") or 1)
    assignment = job.get("assignment", True)

    contexts: dict[str, dict] = {}
    order: list[str] = []
    current = None
    phase = "input"
    rank_seconds: list[tuple[int, float]] = []

    def entry(name: str) -> dict:
        if name not in contexts:
            contexts[name] = {"name": name, "state": "waiting", "stage": None, "rank": None,
                              "ranks_done": 0, "ranks_total": ranks_total,
                              "replicates_done": 0, "replicates_total": replicates_total}
            order.append(name)
        return contexts[name]

    for name in planned:
        entry(name)

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _EXTRACT.match(line)
        if match:
            name = context_name(match.group(2))
            if current is not None and current != name:
                contexts[current]["state"] = "done"
                contexts[current]["stage"] = None
            current = name
            ctx = entry(name)
            ctx.update(state="active", stage="extract", rank=int(match.group(1)), replicates_done=0)
            phase = "extract"
            continue
        if current is None:
            if line.startswith(_MATRICES):
                phase = "matrices"
            skipped = _SKIPPED.match(line)
            if skipped:
                name = context_name(skipped.group(1) or skipped.group(2))
                entry(name).update(state="skipped")
            continue
        ctx = contexts[current]
        if _REPLICATE.match(line):
            ctx["replicates_done"] = min(ctx["replicates_done"] + 1, replicates_total)
            continue
        match = _RANK_TIME.match(line)
        if match:
            rank_seconds.append((int(match.group(1)), float(match.group(2))))
            ctx["replicates_done"] = replicates_total
            continue
        match = _RANK_DONE.match(line)
        if match:
            ctx["ranks_done"] = min(ctx["ranks_done"] + 1, ranks_total)
            continue
        if any(marker in line for marker in _ASSIGN):
            ctx["stage"] = "assign"
            phase = "assign"
            continue
        skipped = _SKIPPED.match(line)
        if skipped:
            entry(context_name(skipped.group(1) or skipped.group(2))).update(state="skipped")
            continue
        if line.startswith(_DASHBOARD) or line.startswith(_DONE):
            ctx.update(state="done", stage=None)
            phase = "done" if line.startswith(_DONE) else "dashboard"

    # The last context finished its assignment step: only the dashboard is left.
    if phase == "assign" and current and order and current == [n for n in order if contexts[n]["state"] != "skipped"][-1]:
        if "Assigning decomposed signature" in text.rsplit("Extracting signature", 1)[-1]:
            phase = "dashboard"
    if job.get("status") == "done":
        phase = "done"
        for ctx in contexts.values():
            if ctx["state"] in ("active", "waiting"):
                ctx.update(state="done", stage=None)

    return {
        "phase": phase,
        "contexts": [contexts[name] for name in order],
        "current": current,
        "fraction": _fraction(contexts, order, assignment, phase),
        "remaining_seconds": _remaining(contexts, order, low, high, rank_seconds),
    }


def _fraction(contexts: dict, order: list, assignment: bool, phase: str) -> float:
    if phase == "done":
        return 1.0
    counted = [contexts[n] for n in order if contexts[n]["state"] != "skipped"]
    if not counted:
        return 0.0
    share = 0.85 if assignment else 1.0
    total = 0.0
    for ctx in counted:
        if ctx["state"] == "done":
            total += 1.0
        elif ctx["state"] == "active":
            if ctx["stage"] == "assign":
                total += share + (1 - share) * 0.5
            else:
                within = ctx["replicates_done"] / max(1, ctx["replicates_total"])
                total += share * min(1.0, (ctx["ranks_done"] + within) / max(1, ctx["ranks_total"]))
    fraction = total / len(counted)
    return round(min(fraction, 0.99), 4)


def _remaining(contexts: dict, order: list, low: int, high: int, rank_seconds: list) -> float | None:
    """A rough estimate: a rank's NMF time grows about linearly with its number
    of signatures, so seconds per signature from finished ranks prices the rest."""
    if len(rank_seconds) < 2:
        return None
    per_signature = sum(t for _, t in rank_seconds) / max(1, sum(k for k, _ in rank_seconds))
    left = 0.0
    for name in order:
        ctx = contexts[name]
        if ctx["state"] == "waiting":
            left += per_signature * sum(range(low, high + 1))
        elif ctx["state"] == "active" and ctx["stage"] == "extract":
            done_upto = low + ctx["ranks_done"]
            left += per_signature * sum(range(done_upto, high + 1))
            if ctx["rank"] is not None:
                fraction = ctx["replicates_done"] / max(1, ctx["replicates_total"])
                left -= per_signature * ctx["rank"] * fraction
    return round(max(left, 0.0), 1)
