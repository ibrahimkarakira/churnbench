import hashlib
import sys
from pathlib import Path

import pytest

from churnbench.checks import run_check, run_checks
from churnbench.config import Check
from churnbench.sandbox import sandbox

PY = f'"{sys.executable}"'


def tree_hash(root: Path) -> str:
    """Hash every path and file byte under `root`, in a stable order."""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        h.update(path.relative_to(root).as_posix().encode())
        if path.is_file():
            h.update(path.read_bytes())
    return h.hexdigest()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An invented repo with one passing and one failing test script, plus .git and runs/."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (root / "test_ok.py").write_text(
        "import sys\nsys.path.insert(0, 'src')\nfrom calc import add\nassert add(2, 2) == 4\n"
    )
    (root / "test_bad.py").write_text(
        "for i in range(50):\n    print('line', i, flush=True)\nraise SystemExit('add is wrong')\n"
    )
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (root / "runs").mkdir()
    (root / "runs" / "old.json").write_text("{}")
    return root


def test_sandbox_copies_tree_without_git_and_runs(repo: Path) -> None:
    with sandbox(repo) as work:
        assert (work / "src" / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"
        assert not (work / ".git").exists()
        assert not (work / "runs").exists()


def test_original_workdir_is_byte_unchanged_after_a_run(repo: Path) -> None:
    before = tree_hash(repo)
    with sandbox(repo) as work:
        (work / "src" / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        (work / "new.txt").write_text("agent output")
        (work / "test_ok.py").unlink()
    assert tree_hash(repo) == before


def test_overlay_is_applied_on_top_of_the_copy(repo: Path, tmp_path: Path) -> None:
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "CLAUDE.md").write_text("Never edit vendor/.\n")
    (overlay / "src").mkdir()
    (overlay / "src" / "calc.py").write_text("def add(a, b):\n    return 0\n")
    with sandbox(repo, overlay) as work:
        assert (work / "CLAUDE.md").read_text() == "Never edit vendor/.\n"
        assert (work / "src" / "calc.py").read_text() == "def add(a, b):\n    return 0\n"
        assert (work / "test_ok.py").exists()
    assert not (repo / "CLAUDE.md").exists()


def test_temp_dir_is_removed_on_normal_exit_and_on_exception(repo: Path) -> None:
    with sandbox(repo) as work:
        pass
    assert not work.parent.exists()
    with pytest.raises(RuntimeError), sandbox(repo) as work:
        raise RuntimeError("adapter crashed")
    assert not work.parent.exists()


def test_missing_workdir_raises_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="workdir"), sandbox(tmp_path / "nope"):
        pass


def test_passing_check(repo: Path) -> None:
    with sandbox(repo) as work:
        result = run_check(Check(kind="command", run=f"{PY} test_ok.py"), work, timeout_s=60)
    assert result.passed
    assert result.exit_code == 0
    assert result.reason == "ok"


def test_failing_check_returns_false_with_captured_tail(repo: Path) -> None:
    with sandbox(repo) as work:
        result = run_check(Check(kind="command", run=f"{PY} test_bad.py"), work, timeout_s=60)
    assert not result.passed
    assert result.exit_code == 1
    assert result.reason == "exit 1, expected 0"
    assert "add is wrong" in result.tail
    assert "line 49" in result.tail
    assert len(result.tail.splitlines()) == 20  # only the tail is kept
    assert "line 29" not in result.tail


def test_expected_nonzero_exit_passes(repo: Path) -> None:
    check = Check(kind="command", run=f"{PY} test_bad.py", expect_exit=1)
    with sandbox(repo) as work:
        assert run_check(check, work, timeout_s=60).passed


def test_timeout_returns_false_with_reason_timeout(repo: Path) -> None:
    check = Check(kind="command", run=f'{PY} -c "import time; time.sleep(30)"')
    with sandbox(repo) as work:
        result = run_check(check, work, timeout_s=1)
    assert not result.passed
    assert result.exit_code is None
    assert result.reason == "timeout"


def test_run_checks_runs_each_check_in_order(repo: Path) -> None:
    checks = (
        Check(kind="command", run=f"{PY} test_ok.py"),
        Check(kind="command", run=f"{PY} test_bad.py"),
    )
    with sandbox(repo) as work:
        results = run_checks(checks, work, timeout_s=60)
    assert [r.passed for r in results] == [True, False]
    assert [r.check for r in results] == list(checks)


def test_unknown_check_kind_is_rejected(repo: Path) -> None:
    with pytest.raises(ValueError, match="kind"):
        run_check(Check(kind="invariant", run="x"), repo, timeout_s=1)
