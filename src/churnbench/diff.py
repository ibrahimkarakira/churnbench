"""Tool-call sequence diff between baseline and candidate runs of one task.

Each run is reduced to its signature: the ordered tool-call names. The baseline is the most
common baseline signature (ties broken alphabetically); every candidate run is aligned against
it with difflib.SequenceMatcher and its divergences are classified:

- missing: a baseline call the run does not make,
- extra: a call the run makes that the baseline does not,
- reordered: a call both make, but in a different position.

A divergence is counted once per run however often the tool repeats there, so "missing Bash:
6 of 10 runs" reads directly next to the outcome rates. Output is sorted and deterministic.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from churnbench.trace import ToolCall, Trace

Signature = tuple[str, ...]


@dataclass(frozen=True)
class Divergence:
    kind: str  # "missing", "extra" or "reordered"
    tool: str
    runs: int


@dataclass(frozen=True)
class TraceDiff:
    baseline: Signature
    candidate_runs: int
    clusters: tuple[tuple[Signature, int], ...]  # candidate signatures, most common first
    divergences: tuple[Divergence, ...]  # most runs first, then kind, then tool


def signature(trace: Trace) -> Signature:
    return tuple(e.name for e in trace.events if isinstance(e, ToolCall))


def _clusters(traces: Sequence[Trace]) -> tuple[tuple[Signature, int], ...]:
    counts = Counter(signature(t) for t in traces)
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _run_divergences(baseline: Signature, run: Signature) -> set[tuple[str, str]]:
    missing: Counter[str] = Counter()
    extra: Counter[str] = Counter()
    matcher = SequenceMatcher(None, baseline, run, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            missing.update(baseline[i1:i2])
        if tag in ("insert", "replace"):
            extra.update(run[j1:j2])
    reordered = missing & extra
    return (
        {("missing", t) for t in missing - reordered}
        | {("extra", t) for t in extra - reordered}
        | {("reordered", t) for t in reordered}
    )


def diff_runs(baseline: Sequence[Trace], candidate: Sequence[Trace]) -> TraceDiff:
    base_clusters = _clusters(baseline)
    reference = base_clusters[0][0] if base_clusters else ()
    clusters = _clusters(candidate)
    counts: Counter[tuple[str, str]] = Counter()
    for sig, n in clusters:
        for key in _run_divergences(reference, sig):
            counts[key] += n
    divergences = sorted(
        (Divergence(kind, tool, n) for (kind, tool), n in counts.items()),
        key=lambda d: (-d.runs, d.kind, d.tool),
    )
    return TraceDiff(reference, len(candidate), clusters, tuple(divergences))


def _show(sig: Signature) -> str:
    return " > ".join(sig) if sig else "(no tool calls)"


def render(result: TraceDiff) -> str:
    """Plain-text summary: baseline signature, divergences, then candidate clusters."""
    total = result.candidate_runs
    lines = [f"baseline: {_show(result.baseline)}", f"candidate: {total} runs"]
    if not result.divergences:
        lines.append("  no divergences")
    lines += [f"  {d.kind} {d.tool}: {d.runs} of {total} runs" for d in result.divergences]
    lines.append("candidate signatures:")
    lines += [f"  {n} x {_show(sig)}" for sig, n in result.clusters]
    return "\n".join(lines) + "\n"
