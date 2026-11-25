"""Outcome checks: run a task's `command` checks inside the sandbox and record what happened.

Invariant checks (predicates over the trace) are added in D06.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from churnbench.config import Check

TAIL_LINES = 20


@dataclass(frozen=True)
class CheckResult:
    check: Check
    passed: bool
    exit_code: int | None  # None when the command timed out
    reason: str  # "ok", "exit <n>, expected <m>" or "timeout"
    tail: str  # last TAIL_LINES lines of combined stdout and stderr


def run_check(check: Check, cwd: Path, timeout_s: float) -> CheckResult:
    """Run one check's shell command in `cwd`; kill it and its children after `timeout_s`."""
    if check.kind != "command":
        raise ValueError(f"unsupported check kind '{check.kind}'")
    # Output goes to a file, not a pipe: a grandchild that outlives a killed shell cannot then
    # block the read.
    with tempfile.TemporaryFile() as out:
        proc = subprocess.Popen(
            check.run,
            shell=True,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
        )
        try:
            code: int | None = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            code = None
        out.seek(0)
        tail = _tail(out.read())
    if code is None:
        return CheckResult(check, False, None, "timeout", tail)
    if code != check.expect_exit:
        return CheckResult(check, False, code, f"exit {code}, expected {check.expect_exit}", tail)
    return CheckResult(check, True, code, "ok", tail)


def run_checks(checks: tuple[Check, ...], cwd: Path, timeout_s: float) -> tuple[CheckResult, ...]:
    """Run every check in order; a failing check does not stop the ones after it."""
    return tuple(run_check(check, cwd, timeout_s) for check in checks)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the shell and everything it started, then reap it."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.kill()  # no-op if already gone; covers taskkill failing
    proc.wait()


def _tail(raw: bytes) -> str:
    lines = raw.decode("utf-8", errors="replace").splitlines()
    return "\n".join(lines[-TAIL_LINES:])
