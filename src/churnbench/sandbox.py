"""Give every run its own throwaway copy of the project workdir.

The agent and the outcome checks only ever touch the copy, so the user's checkout stays
byte-unchanged. `.git` (at any depth) and the top-level `runs/` results directory are not copied.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SKIP_ANYWHERE = frozenset({".git"})
SKIP_AT_ROOT = frozenset({"runs"})


@contextmanager
def sandbox(workdir: str | Path, overlay: str | Path | None = None) -> Iterator[Path]:
    """Copy `workdir` (then `overlay` on top of it) into a temp dir, yield the copy, delete it.

    The temp dir is removed when the block exits, including when it exits with an exception.
    """
    src = Path(workdir)
    if not src.is_dir():
        raise FileNotFoundError(f"workdir is not a directory: {src}")
    if overlay is not None and not Path(overlay).is_dir():
        raise FileNotFoundError(f"overlay is not a directory: {overlay}")

    def skip(directory: str, names: list[str]) -> set[str]:
        skipped = SKIP_ANYWHERE | (SKIP_AT_ROOT if Path(directory) == src else frozenset())
        return skipped.intersection(names)

    with tempfile.TemporaryDirectory(prefix="churnbench-") as tmp:
        work = Path(tmp) / "work"
        shutil.copytree(src, work, ignore=skip)
        if overlay is not None:
            shutil.copytree(overlay, work, dirs_exist_ok=True)
        yield work
