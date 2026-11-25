"""Replay adapter: returns recorded traces instead of calling a model.

Fixtures live at `<fixtures>/<model>/<task id>.jsonl`, one trace per line; line n (0-based) is
run n. No model, key or network is touched, so tests and the demo are reproducible offline.
"""

from __future__ import annotations

from pathlib import Path

from churnbench.config import Task
from churnbench.trace import Trace, from_jsonl


class FixtureNotFoundError(LookupError):
    """No recorded trace exists for the requested (model, task, run)."""


def _plain(name: str, what: str) -> str:
    if name in ("", ".", "..") or "/" in name or "\\" in name:
        raise FixtureNotFoundError(f"{what} {name!r} is not a plain file name")
    return name


class MockAdapter:
    def __init__(self, fixtures: Path) -> None:
        self.fixtures = Path(fixtures)

    def run(self, task: Task, workdir: Path, model: str, run_index: int = 0) -> Trace:
        path = self.fixtures / _plain(model, "model") / f"{_plain(task.id, 'task id')}.jsonl"
        if not path.is_file():
            raise FixtureNotFoundError(
                f"no recorded trace for model {model!r}, task {task.id!r}: {path} does not exist"
            )
        traces = from_jsonl(path.read_text(encoding="utf-8"))
        if not 0 <= run_index < len(traces):
            raise FixtureNotFoundError(
                f"{path}: run {run_index}: the fixture has {len(traces)} runs (0 to "
                f"{len(traces) - 1})"
            )
        return traces[run_index]
