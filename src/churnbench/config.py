"""Load and validate churnbench.toml into frozen dataclasses.

Every error is a ConfigError whose message reads "<source>: <key path>: <reason>", for example
"churnbench.toml: task[0].check[1].run: missing required key". Unknown keys fail fast and name the
closest allowed key. Paths such as `workdir` and `overlay` are kept as written; resolving them is
the job of the code that uses them.
"""

from __future__ import annotations

import difflib
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any


class ConfigError(ValueError):
    """The config file is missing, unreadable or invalid."""


@dataclass(frozen=True)
class Project:
    name: str
    workdir: str


@dataclass(frozen=True)
class Side:
    """One side of the matrix, written "adapter:model" in the config."""

    adapter: str
    model: str


@dataclass(frozen=True)
class Matrix:
    baseline: Side
    candidate: Side
    runs: int
    max_budget_usd: float | None = None


@dataclass(frozen=True)
class Check:
    kind: str
    run: str
    expect_exit: int = 0


@dataclass(frozen=True)
class Invariant:
    kind: str
    path_glob: str | None = None
    tool: str | None = None
    contains: str | None = None
    max: int | None = None


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    timeout_s: int = 300
    checks: tuple[Check, ...] = ()
    invariants: tuple[Invariant, ...] = ()


@dataclass(frozen=True)
class AdapterOptions:
    mode: str = "project"
    permission_mode: str | None = None
    allowed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class Variant:
    overlay: str


@dataclass(frozen=True)
class Verdict:
    alpha: float = 0.05
    min_drop: float = 0.20
    min_runs: int = 5


@dataclass(frozen=True)
class Config:
    project: Project
    matrix: Matrix
    tasks: tuple[Task, ...]
    adapters: Mapping[str, AdapterOptions] = field(default_factory=dict)
    variants: Mapping[str, Variant] = field(default_factory=dict)
    verdict: Verdict = Verdict()

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapters", MappingProxyType(dict(self.adapters)))
        object.__setattr__(self, "variants", MappingProxyType(dict(self.variants)))


# kind -> (required keys, optional keys), besides "kind" itself. D06 implements the predicates.
INVARIANT_KEYS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "never_edit": (("path_glob",), ()),
    "never_tool": (("tool",), ()),
    "tool_before_finish": (("tool",), ("contains",)),
    "max_tool_calls": (("max",), ("tool",)),
}
CHECK_KINDS = ("command",)
ADAPTER_MODES = ("project", "bare")
SIDES = ("baseline", "candidate")

_TYPE_NAMES = {str: "string", int: "integer", float: "number", list: "array", dict: "table"}


class _Reader:
    """Validates one parsed document; `where` is the dotted key path of the current table."""

    def __init__(self, source: str) -> None:
        self.source = source

    def fail(self, key: str, reason: str) -> ConfigError:
        return ConfigError(f"{self.source}: {key}: {reason}")

    def keys(
        self,
        table: Mapping[str, Any],
        where: str,
        required: tuple[str, ...],
        optional: tuple[str, ...] = (),
    ) -> None:
        allowed = required + optional
        for key in table:
            if key not in allowed:
                raise self.fail(_join(where, key), "unknown key" + _hint(key, allowed))
        for key in required:
            if key not in table:
                raise self.fail(_join(where, key), "missing required key")

    def get(self, table: Mapping[str, Any], where: str, key: str, kind: type, default: Any = None):
        if key not in table:
            return default
        value = table[key]
        accepted = (int, float) if kind is float else kind
        if isinstance(value, bool) or not isinstance(value, accepted):
            got = type(value).__name__
            raise self.fail(_join(where, key), f"expected {_TYPE_NAMES[kind]}, got {got}")
        if kind is str and not value.strip():
            raise self.fail(_join(where, key), "must not be empty")
        return float(value) if kind is float else value

    def table(self, table: Mapping[str, Any], where: str, key: str) -> dict[str, Any]:
        return self.get(table, where, key, dict, {})

    def tables(self, table: Mapping[str, Any], where: str, key: str) -> list[dict[str, Any]]:
        items = self.get(table, where, key, list, [])
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise self.fail(f"{_join(where, key)}[{i}]", "expected table")
        return items

    def choice(self, value: str, key: str, allowed: tuple[str, ...]) -> str:
        if value not in allowed:
            raise self.fail(key, f"unknown value '{value}'" + _hint(value, allowed))
        return value

    def at_least(self, value: float | None, key: str, low: float) -> None:
        if value is not None and value < low:
            raise self.fail(key, f"must be >= {low}, got {value}")

    def between(self, value: float, key: str, low: float, high: float) -> None:
        # Open at the low end, closed at the high end: (low, high].
        if not low < value <= high:
            raise self.fail(key, f"must be > {low} and <= {high}, got {value}")


def _join(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def _hint(key: str, allowed: tuple[str, ...]) -> str:
    close = difflib.get_close_matches(key, allowed, n=1)
    if close:
        return f"; did you mean '{close[0]}'?"
    return f"; allowed: {', '.join(allowed)}"


def load(path: str | Path) -> Config:
    """Read and validate a churnbench.toml file."""
    try:
        with open(path, "rb") as fp:
            data = tomllib.load(fp)
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc
    return parse(data, source=str(path))


def loads(text: str, source: str = "<string>") -> Config:
    """Validate config text; `source` names it in error messages."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{source}: invalid TOML: {exc}") from exc
    return parse(data, source=source)


def parse(data: Mapping[str, Any], source: str = "<string>") -> Config:
    """Validate an already-parsed TOML document."""
    r = _Reader(source)
    r.keys(data, "", ("project", "matrix", "task"), ("adapter", "variant", "verdict"))
    return Config(
        project=_project(r, r.table(data, "", "project")),
        matrix=_matrix(r, r.table(data, "", "matrix")),
        tasks=_tasks(r, r.tables(data, "", "task")),
        adapters=_adapters(r, r.table(data, "", "adapter")),
        variants=_variants(r, r.table(data, "", "variant")),
        verdict=_verdict(r, r.table(data, "", "verdict")),
    )


def _project(r: _Reader, raw: dict[str, Any]) -> Project:
    r.keys(raw, "project", ("name", "workdir"))
    return Project(
        name=r.get(raw, "project", "name", str),
        workdir=r.get(raw, "project", "workdir", str),
    )


def _side(r: _Reader, raw: dict[str, Any], key: str) -> Side:
    spec = r.get(raw, "matrix", key, str)
    adapter, sep, model = spec.partition(":")
    if not (sep and adapter.strip() and model.strip()):
        raise r.fail(f"matrix.{key}", f"expected 'adapter:model', got '{spec}'")
    return Side(adapter=adapter, model=model)


def _matrix(r: _Reader, raw: dict[str, Any]) -> Matrix:
    r.keys(raw, "matrix", ("baseline", "candidate", "runs"), ("max_budget_usd",))
    runs = r.get(raw, "matrix", "runs", int)
    r.at_least(runs, "matrix.runs", 1)
    budget = r.get(raw, "matrix", "max_budget_usd", float)
    if budget is not None and budget <= 0:
        raise r.fail("matrix.max_budget_usd", f"must be > 0, got {budget}")
    return Matrix(
        baseline=_side(r, raw, "baseline"),
        candidate=_side(r, raw, "candidate"),
        runs=runs,
        max_budget_usd=budget,
    )


def _tasks(r: _Reader, items: list[dict[str, Any]]) -> tuple[Task, ...]:
    if not items:
        raise r.fail("task", "missing required key (at least one [[task]])")
    tasks: list[Task] = []
    seen: set[str] = set()
    for i, raw in enumerate(items):
        where = f"task[{i}]"
        r.keys(raw, where, ("id", "prompt"), ("timeout_s", "check", "invariant"))
        task_id = r.get(raw, where, "id", str)
        if task_id in seen:
            raise r.fail(f"{where}.id", f"duplicate task id '{task_id}'")
        seen.add(task_id)
        timeout = r.get(raw, where, "timeout_s", int, 300)
        r.at_least(timeout, f"{where}.timeout_s", 1)
        checks = r.tables(raw, where, "check")
        invariants = r.tables(raw, where, "invariant")
        tasks.append(
            Task(
                id=task_id,
                prompt=r.get(raw, where, "prompt", str),
                timeout_s=timeout,
                checks=tuple(_check(r, c, f"{where}.check[{j}]") for j, c in enumerate(checks)),
                invariants=tuple(
                    _invariant(r, v, f"{where}.invariant[{j}]") for j, v in enumerate(invariants)
                ),
            )
        )
    return tuple(tasks)


def _check(r: _Reader, raw: dict[str, Any], where: str) -> Check:
    r.keys(raw, where, ("kind", "run"), ("expect_exit",))
    return Check(
        kind=r.choice(r.get(raw, where, "kind", str), f"{where}.kind", CHECK_KINDS),
        run=r.get(raw, where, "run", str),
        expect_exit=r.get(raw, where, "expect_exit", int, 0),
    )


def _invariant(r: _Reader, raw: dict[str, Any], where: str) -> Invariant:
    r.keys(raw, where, ("kind",), ("path_glob", "tool", "contains", "max"))
    kind = r.choice(r.get(raw, where, "kind", str), f"{where}.kind", tuple(INVARIANT_KEYS))
    required, optional = INVARIANT_KEYS[kind]
    r.keys(raw, where, ("kind", *required), optional)
    limit = r.get(raw, where, "max", int)
    r.at_least(limit, f"{where}.max", 0)
    return Invariant(
        kind=kind,
        path_glob=r.get(raw, where, "path_glob", str),
        tool=r.get(raw, where, "tool", str),
        contains=r.get(raw, where, "contains", str),
        max=limit,
    )


def _adapters(r: _Reader, raw: dict[str, Any]) -> dict[str, AdapterOptions]:
    return {name: _adapter(r, r.table(raw, "adapter", name), f"adapter.{name}") for name in raw}


def _adapter(r: _Reader, raw: dict[str, Any], where: str) -> AdapterOptions:
    r.keys(raw, where, (), ("mode", "permission_mode", "allowed_tools"))
    tools = r.get(raw, where, "allowed_tools", list, [])
    for i, tool in enumerate(tools):
        if not isinstance(tool, str) or not tool.strip():
            raise r.fail(f"{where}.allowed_tools[{i}]", "expected non-empty string")
    return AdapterOptions(
        mode=r.choice(r.get(raw, where, "mode", str, "project"), f"{where}.mode", ADAPTER_MODES),
        permission_mode=r.get(raw, where, "permission_mode", str),
        allowed_tools=tuple(tools),
    )


def _variants(r: _Reader, raw: dict[str, Any]) -> dict[str, Variant]:
    r.keys(raw, "variant", (), SIDES)
    variants = {}
    for side in raw:
        body = r.table(raw, "variant", side)
        r.keys(body, f"variant.{side}", ("overlay",))
        variants[side] = Variant(overlay=r.get(body, f"variant.{side}", "overlay", str))
    return variants


def _verdict(r: _Reader, raw: dict[str, Any]) -> Verdict:
    r.keys(raw, "verdict", (), ("alpha", "min_drop", "min_runs"))
    default = Verdict()
    alpha = r.get(raw, "verdict", "alpha", float, default.alpha)
    min_drop = r.get(raw, "verdict", "min_drop", float, default.min_drop)
    min_runs = r.get(raw, "verdict", "min_runs", int, default.min_runs)
    r.between(alpha, "verdict.alpha", 0.0, 1.0)
    r.between(min_drop, "verdict.min_drop", 0.0, 1.0)
    r.at_least(min_runs, "verdict.min_runs", 1)
    return Verdict(alpha=alpha, min_drop=min_drop, min_runs=min_runs)
