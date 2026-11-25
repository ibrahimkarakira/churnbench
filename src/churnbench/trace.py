"""The adapter-independent trace of one agent run, stored as one JSON object per line (JSONL).

Adapters turn their CLI's own stream (Claude Code `stream-json`, Codex `exec --json`, ...) into a
Trace; checks, diffs and fixtures read only this model. The format is documented in
docs/trace-format.md. Every error is a TraceError whose message names the field, for example
"events[3].ok: expected boolean, got str".
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
SUMMARY_LIMIT = 200


class TraceError(ValueError):
    """A serialized trace is invalid or uses an unsupported schema_version."""


def _truncate(text: str) -> str:
    return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 1] + "…"


def summarize(tool_input: Any) -> str:
    """Compact, key-sorted JSON of a tool input (strings pass through), cut to SUMMARY_LIMIT."""
    if isinstance(tool_input, str):
        return _truncate(tool_input)
    return _truncate(
        json.dumps(tool_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


@dataclass(frozen=True)
class ToolCall:
    name: str
    input_summary: str
    ok: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_summary", _truncate(self.input_summary))


@dataclass(frozen=True)
class AssistantText:
    text: str


@dataclass(frozen=True)
class PermissionDenied:
    tool: str
    input_summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_summary", _truncate(self.input_summary))


Event = ToolCall | AssistantText | PermissionDenied

# kind -> (class, {field: type}). The order of fields is the order they are written.
_EVENTS: dict[str, tuple[type, dict[str, type]]] = {
    "tool_call": (ToolCall, {"name": str, "input_summary": str, "ok": bool}),
    "assistant_text": (AssistantText, {"text": str}),
    "permission_denied": (PermissionDenied, {"tool": str, "input_summary": str}),
}
_KIND_OF = {cls: kind for kind, (cls, _) in _EVENTS.items()}


@dataclass(frozen=True)
class Trace:
    """One run: ordered events, the final answer, and what produced it."""

    events: tuple[Event, ...]
    final_text: str
    cost_usd: float | None
    turns: int
    model: str
    tool_version: str
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model": self.model,
            "tool_version": self.tool_version,
            "turns": self.turns,
            "cost_usd": self.cost_usd,
            "final_text": self.final_text,
            "events": [_event_dict(e) for e in self.events],
        }

    def to_json(self) -> str:
        """One line of JSON, no trailing newline. A non-finite cost_usd raises ValueError."""
        return json.dumps(
            self.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )


def _event_dict(event: Event) -> dict[str, Any]:
    kind = _KIND_OF[type(event)]
    return {"kind": kind, **{f: getattr(event, f) for f in _EVENTS[kind][1]}}


_TYPE_NAMES = {str: "string", int: "integer", bool: "boolean", float: "number", list: "array"}
_FIELDS = ("model", "tool_version", "turns", "cost_usd", "final_text", "events")


def _keys(raw: dict[str, Any], where: str, allowed: tuple[str, ...]) -> None:
    for key in raw:
        if key not in allowed:
            raise TraceError(f"{where}{key}: unknown key")
    for key in allowed:
        if key not in raw:
            raise TraceError(f"{where}{key}: missing required key")


def _typed(value: Any, key: str, kind: type) -> Any:
    accepted = (int, float) if kind is float else kind
    if (isinstance(value, bool) and kind is not bool) or not isinstance(value, accepted):
        raise TraceError(f"{key}: expected {_TYPE_NAMES[kind]}, got {type(value).__name__}")
    if kind is not float:
        return value
    try:
        return float(value)
    except OverflowError:  # a JSON integer too large for a float, e.g. 1 followed by 400 zeros
        return math.inf


def _event(raw: Any, where: str) -> Event:
    if not isinstance(raw, dict):
        raise TraceError(f"{where}: expected object, got {type(raw).__name__}")
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in _EVENTS:
        raise TraceError(f"{where}.kind: unknown kind {kind!r}; allowed: {', '.join(_EVENTS)}")
    cls, fields = _EVENTS[kind]
    _keys(raw, f"{where}.", ("kind", *fields))
    return cls(**{f: _typed(raw[f], f"{where}.{f}", t) for f, t in fields.items()})


def from_dict(data: Any) -> Trace:
    if not isinstance(data, dict):
        raise TraceError(f"expected object, got {type(data).__name__}")
    version = data.get("schema_version")
    if type(version) is not int or version != SCHEMA_VERSION:
        raise TraceError(
            f"schema_version: unsupported value {version!r}; this churnbench reads {SCHEMA_VERSION}"
        )
    _keys(data, "", ("schema_version", *_FIELDS))
    events = _typed(data["events"], "events", list)
    turns = _typed(data["turns"], "turns", int)
    if turns < 0:
        raise TraceError(f"turns: must be >= 0, got {turns}")
    cost = data["cost_usd"]
    if cost is not None:
        cost = _typed(cost, "cost_usd", float)
        if not math.isfinite(cost) or cost < 0:
            raise TraceError(f"cost_usd: must be a finite number >= 0, got {cost!r}")
    return Trace(
        events=tuple(_event(e, f"events[{i}]") for i, e in enumerate(events)),
        final_text=_typed(data["final_text"], "final_text", str),
        cost_usd=cost,
        turns=turns,
        model=_typed(data["model"], "model", str),
        tool_version=_typed(data["tool_version"], "tool_version", str),
    )


def from_json(line: str) -> Trace:
    try:
        data = json.loads(line)
    # JSONDecodeError, an integer past sys.get_int_max_str_digits(), or nesting past the stack.
    except (ValueError, RecursionError) as exc:
        raise TraceError(f"invalid JSON: {exc}") from exc
    return from_dict(data)


def to_jsonl(traces: Iterable[Trace]) -> str:
    """One trace per line, each line ending in a newline."""
    return "".join(t.to_json() + "\n" for t in traces)


def from_jsonl(text: str) -> tuple[Trace, ...]:
    """Read every non-blank line; errors are prefixed with the 1-based line number."""
    traces = []
    # Split on "\n" only: str.splitlines() also breaks on U+2028, U+2029 and U+0085, which
    # to_json leaves unescaped (ensure_ascii=False) inside strings.
    for number, line in enumerate(text.split("\n"), start=1):
        line = line.removesuffix("\r")
        if not line.strip():
            continue
        try:
            traces.append(from_json(line))
        except TraceError as exc:
            raise TraceError(f"line {number}: {exc}") from exc
    return tuple(traces)
