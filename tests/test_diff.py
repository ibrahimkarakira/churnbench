from pathlib import Path

from churnbench.diff import Divergence, diff_runs, render, signature
from churnbench.trace import AssistantText, ToolCall, Trace, from_jsonl

DEMO = Path(__file__).resolve().parents[1] / "src" / "churnbench" / "demo" / "traces"


def _demo(model: str) -> tuple[Trace, ...]:
    return from_jsonl((DEMO / model / "add-fee-rule.jsonl").read_text(encoding="utf-8"))


def _run(*names: str) -> Trace:
    events = [ToolCall(name=n, input_summary="{}", ok=True) for n in names]
    return Trace(
        events=(AssistantText(text="hi"), *events),
        final_text="done",
        cost_usd=None,
        turns=len(events),
        model="m",
        tool_version="t",
    )


def test_signature_keeps_only_tool_call_names_in_order():
    assert signature(_run("Read", "Edit", "Bash")) == ("Read", "Edit", "Bash")


def test_demo_candidate_skips_the_test_run_in_6_of_10_runs():
    result = diff_runs(_demo("model-a"), _demo("model-b"))
    assert result.candidate_runs == 10
    assert Divergence("missing", "Bash", 6) in result.divergences
    assert not any(d.tool == "Bash" and d.kind != "missing" for d in result.divergences)


def test_identical_runs_give_an_empty_diff():
    runs = (_run("Read", "Edit", "Bash"),) * 3
    result = diff_runs(runs, runs)
    assert result.divergences == ()
    assert "no divergences" in render(result)


def test_output_is_deterministic():
    one = render(diff_runs(_demo("model-a"), _demo("model-b")))
    two = render(diff_runs(tuple(reversed(_demo("model-a"))), _demo("model-b")))
    assert one == two


def test_baseline_tie_is_broken_alphabetically():
    tied = (_run("Read", "Edit"), _run("Glob", "Edit"))
    assert diff_runs(tied, tied).baseline == ("Glob", "Edit")
    assert diff_runs(tuple(reversed(tied)), tied).baseline == ("Glob", "Edit")


def test_clusters_are_sorted_by_count_then_alphabetically():
    candidate = (_run("Read"), _run("Bash"), _run("Bash"), _run("Edit"))
    clusters = diff_runs((_run("Read"),), candidate).clusters
    assert clusters == ((("Bash",), 2), (("Edit",), 1), (("Read",), 1))


def test_reorder_only():
    # SequenceMatcher keeps the longest match (Read, Edit) and reports Bash as the moved call.
    result = diff_runs((_run("Read", "Edit", "Bash"),), (_run("Read", "Bash", "Edit"),))
    assert result.divergences == (Divergence("reordered", "Bash", 1),)


def test_extra_call_only():
    result = diff_runs((_run("Read", "Edit"),), (_run("Read", "Grep", "Edit"),) * 2)
    assert result.divergences == (Divergence("extra", "Grep", 2),)


def test_replace_counts_as_missing_and_extra():
    result = diff_runs((_run("Read", "Edit"),), (_run("Read", "Write"),))
    assert result.divergences == (Divergence("extra", "Write", 1), Divergence("missing", "Edit", 1))


def test_repeated_name_counts_each_run_once():
    result = diff_runs((_run("Read"),), (_run("Read", "Bash", "Bash"),))
    assert result.divergences == (Divergence("extra", "Bash", 1),)


def test_render_demo():
    text = render(diff_runs(_demo("model-a"), _demo("model-b")))
    assert "missing Bash: 6 of 10 runs" in text
    assert text.startswith("baseline: Read > Read > Edit > Edit > Bash")


def test_empty_inputs():
    result = diff_runs((), ())
    assert result.baseline == ()
    assert result.divergences == ()
    assert "0 runs" in render(result)
