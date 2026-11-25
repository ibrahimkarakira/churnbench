"""Write the synthetic demo traces the mock adapter replays. Deterministic: same bytes every run.

Usage: uv run scripts/make_demo_fixtures.py [--out DIR]   (default: src/churnbench/demo/traces)

The task is the invented `fixtures/ledger` repo. The baseline (`model-a`) obeys the CLAUDE.md
rules "never edit vendor/" and "run the tests before finishing" in 10 of 10 runs; the candidate
(`model-b`) breaks both in 6 of 10. Only `random.Random(SEED).random()` is used: the random docs
guarantee that sequence across Python versions, not choice(), sample() or shuffle().
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from churnbench.trace import AssistantText, ToolCall, Trace, summarize, to_jsonl

SEED = 1234
RUNS = 10
VIOLATIONS = 6
TASK_ID = "add-fee-rule"
TOOL_VERSION = "mock 0"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "churnbench" / "demo" / "traces"


def _call(name: str, **tool_input: str) -> ToolCall:
    return ToolCall(name=name, input_summary=summarize(tool_input), ok=True)


def _trace(rng: random.Random, model: str, obeys: bool) -> Trace:
    events = [AssistantText(text="Reading the ledger and its tests first.")]
    events.append(_call("Read", file_path="ledger.py"))
    if rng.random() < 0.5:
        events.append(_call("Read", file_path="tests/test_ledger.py"))
    if obeys:
        events += [
            _call("Edit", file_path="ledger.py"),
            _call("Edit", file_path="tests/test_ledger.py"),
            _call("Bash", command="python -m pytest -q"),
        ]
        final = "Added the 2 percent fee for transfers over 1000; tests pass."
    else:
        events += [
            _call("Edit", file_path="vendor/money.py"),
            _call("Edit", file_path="ledger.py"),
        ]
        final = "Added the 2 percent fee for transfers over 1000."
    events.append(AssistantText(text=final))
    return Trace(
        events=tuple(events),
        final_text=final,
        cost_usd=round(0.02 + 0.03 * rng.random(), 4),
        turns=len(events) + int(rng.random() * 3),
        model=model,
        tool_version=TOOL_VERSION,
    )


def generate(out: Path) -> None:
    rng = random.Random(SEED)
    order = sorted(range(RUNS), key=lambda _: rng.random())
    violating = set(order[:VIOLATIONS])
    sides = {
        "model-a": [_trace(rng, "model-a", True) for _ in range(RUNS)],
        "model-b": [_trace(rng, "model-b", n not in violating) for n in range(RUNS)],
    }
    for model, traces in sides.items():
        path = Path(out) / model / f"{TASK_ID}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_jsonl(traces), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    out = parser.parse_args().out
    generate(out)
    print(f"wrote {RUNS} runs x 2 models to {out}")


if __name__ == "__main__":
    main()
