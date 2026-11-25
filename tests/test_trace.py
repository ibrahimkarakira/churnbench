import json

import pytest

from churnbench.trace import (
    SCHEMA_VERSION,
    SUMMARY_LIMIT,
    AssistantText,
    PermissionDenied,
    ToolCall,
    Trace,
    TraceError,
    from_json,
    from_jsonl,
    summarize,
    to_jsonl,
)

FULL = Trace(
    events=(
        AssistantText(text="Reading the ledger module first."),
        ToolCall(name="Read", input_summary='{"file_path":"ledger.py"}', ok=True),
        ToolCall(name="Bash", input_summary='{"command":"python -m pytest -q"}', ok=False),
        PermissionDenied(tool="Bash", input_summary='{"command":"rm -rf vendor"}'),
        ToolCall(name="Edit", input_summary='{"file_path":"ledger.py"}', ok=True),
        AssistantText(text="Added the fee rule; tests pass."),
    ),
    final_text="Added the fee rule; tests pass.",
    cost_usd=0.0421,
    turns=7,
    model="model-a",
    tool_version="2.1.300 (Claude Code)",
)
EMPTY = Trace(events=(), final_text="", cost_usd=None, turns=0, model="m", tool_version="0")
TEXT_ONLY = Trace(
    events=(AssistantText(text="no tools, \"quotes\" and unicode: é ✓\nsecond line"),),
    final_text="done",
    cost_usd=0.0,
    turns=1,
    model="command:llama3:8b",
    tool_version="codex-cli 0.165.0",
)


@pytest.mark.parametrize("trace", [FULL, EMPTY, TEXT_ONLY], ids=["full", "empty", "text-only"])
def test_round_trip_is_equal(trace):
    line = trace.to_json()
    assert "\n" not in line
    assert from_json(line) == trace


def test_jsonl_round_trip_keeps_trace_order():
    text = to_jsonl([FULL, EMPTY, TEXT_ONLY])
    assert text.count("\n") == 3
    assert from_jsonl(text) == (FULL, EMPTY, TEXT_ONLY)
    assert from_jsonl(text + "\n\n") == (FULL, EMPTY, TEXT_ONLY)


@pytest.mark.parametrize(
    "sep",
    ["\u2028", "\u2029", "\x85", "\x1c", "\x1d", "\x1e", "\x0b", "\x0c"],
    ids=["LS", "PS", "NEL", "FS", "GS", "RS", "VT", "FF"],
)
def test_jsonl_round_trip_keeps_unicode_line_separators(sep):
    trace = Trace(
        events=(AssistantText(text=f"a{sep}b"),),
        final_text=f"end{sep}",
        cost_usd=None,
        turns=1,
        model="m",
        tool_version="0",
    )
    assert from_jsonl(to_jsonl([trace, EMPTY])) == (trace, EMPTY)


def test_jsonl_accepts_crlf_line_endings():
    text = to_jsonl([FULL, EMPTY]).replace("\n", "\r\n")
    assert from_jsonl(text) == (FULL, EMPTY)


def test_events_keep_order():
    kinds = [e["kind"] for e in json.loads(FULL.to_json())["events"]]
    assert kinds == [
        "assistant_text", "tool_call", "tool_call", "permission_denied", "tool_call",
        "assistant_text",
    ]
    names = [e.name for e in from_json(FULL.to_json()).events if isinstance(e, ToolCall)]
    assert names == ["Read", "Bash", "Edit"]


def test_schema_version_is_written():
    assert json.loads(EMPTY.to_json())["schema_version"] == SCHEMA_VERSION


@pytest.mark.parametrize("version", [0, 2, "1", None])
def test_unknown_schema_version_raises(version):
    data = json.loads(EMPTY.to_json())
    data["schema_version"] = version
    with pytest.raises(TraceError, match="schema_version"):
        from_json(json.dumps(data))


def test_missing_schema_version_raises():
    data = json.loads(EMPTY.to_json())
    del data["schema_version"]
    with pytest.raises(TraceError, match="schema_version"):
        from_json(json.dumps(data))


def test_input_summary_truncated_to_limit():
    long = "x" * 500
    call = ToolCall(name="Bash", input_summary=long, ok=True)
    assert len(call.input_summary) == SUMMARY_LIMIT == 200
    assert call.input_summary.endswith("…")
    denied = PermissionDenied(tool="Bash", input_summary=long)
    assert len(denied.input_summary) == SUMMARY_LIMIT
    exact = "y" * SUMMARY_LIMIT
    assert ToolCall(name="Bash", input_summary=exact, ok=True).input_summary == exact


def test_truncated_summary_survives_round_trip():
    trace = Trace(
        events=(ToolCall(name="Write", input_summary="z" * 1000, ok=True),),
        final_text="", cost_usd=None, turns=1, model="m", tool_version="0",
    )
    assert from_json(trace.to_json()) == trace


def test_summarize_is_compact_sorted_json_and_truncated():
    assert summarize({"b": 1, "a": "x"}) == '{"a":"x","b":1}'
    assert summarize("plain") == "plain"
    assert len(summarize({"content": "q" * 999})) == SUMMARY_LIMIT


def test_trace_is_frozen():
    with pytest.raises(AttributeError):
        FULL.turns = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda d: d["events"].append({"kind": "thinking", "text": "x"}), "events[6].kind"),
        (lambda d: d["events"][1].pop("ok"), "events[1].ok"),
        (lambda d: d["events"][1].update(ok="yes"), "events[1].ok"),
        (lambda d: d.update(turns="7"), "turns"),
        (lambda d: d.update(extra=1), "extra"),
        (lambda d: d.pop("model"), "model"),
    ],
)
def test_malformed_trace_names_the_field(mutate, fragment):
    data = json.loads(FULL.to_json())
    mutate(data)
    with pytest.raises(TraceError, match=fragment.replace("[", r"\[").replace("]", r"\]")):
        from_json(json.dumps(data))


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "1e999", "-1", "-0.01"])
def test_cost_must_be_finite_and_not_negative(raw):
    line = FULL.to_json().replace('"cost_usd":0.0421', f'"cost_usd":{raw}')
    with pytest.raises(TraceError, match="cost_usd: must be a finite number >= 0"):
        from_json(line)


@pytest.mark.parametrize("cost", [float("nan"), float("inf")])
def test_non_finite_cost_is_not_written(cost):
    trace = Trace(events=(), final_text="", cost_usd=cost, turns=0, model="m", tool_version="0")
    with pytest.raises(ValueError):
        trace.to_json()


def test_invalid_json_raises_trace_error():
    with pytest.raises(TraceError, match="invalid JSON"):
        from_json("{not json")
    with pytest.raises(TraceError, match="line 2"):
        from_jsonl(EMPTY.to_json() + "\n[]\n")


def test_huge_integer_cost_raises_trace_error():
    # 400 digits: a valid JSON integer that float() cannot hold.
    line = FULL.to_json().replace('"cost_usd":0.0421', '"cost_usd":1' + "0" * 400)
    with pytest.raises(TraceError, match="cost_usd: must be a finite number >= 0"):
        from_json(line)


def test_integer_past_python_digit_limit_raises_trace_error():
    # json.loads raises a plain ValueError past sys.get_int_max_str_digits() (4300 by default).
    line = FULL.to_json().replace('"turns":7', '"turns":' + "9" * 5000)
    with pytest.raises(TraceError, match="invalid JSON"):
        from_json(line)


@pytest.mark.parametrize("kind", ["[]", "{}"])
def test_unhashable_event_kind_raises_trace_error(kind):
    line = EMPTY.to_json().replace('"events":[]', '"events":[{"kind":' + kind + "}]")
    with pytest.raises(TraceError, match=r"events\[0\]\.kind: unknown kind"):
        from_json(line)


@pytest.mark.parametrize("line", ["[" * 100_000, '{"a":' * 100_000])
def test_deeply_nested_json_raises_trace_error(line):
    with pytest.raises(TraceError, match="invalid JSON"):
        from_json(line)
