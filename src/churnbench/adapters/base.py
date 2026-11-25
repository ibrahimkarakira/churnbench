"""The contract every adapter meets: run one task once and return its normalized Trace."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from churnbench.config import Task
from churnbench.trace import Trace


class Adapter(Protocol):
    def run(self, task: Task, workdir: Path, model: str, run_index: int = 0) -> Trace:
        """Run `task` in `workdir` with `model`. `run_index` is the 0-based repeat number; live
        adapters ignore it, replay adapters use it to pick the recorded run."""
        ...
