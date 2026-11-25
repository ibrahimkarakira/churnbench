import hashlib
import importlib.util
from pathlib import Path

import pytest

from churnbench.adapters.base import Adapter
from churnbench.adapters.mock import FixtureNotFoundError, MockAdapter
from churnbench.config import Task
from churnbench.trace import ToolCall, from_jsonl

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "src" / "churnbench" / "demo" / "traces"
TASK = Task(id="add-fee-rule", prompt="Add a 2 percent fee to transfers over 1000.")


def _generator():
    path = ROOT / "scripts" / "make_demo_fixtures.py"
    spec = importlib.util.spec_from_file_location("make_demo_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_generator_is_byte_identical_and_matches_committed_fixtures(tmp_path):
    gen = _generator()
    gen.generate(tmp_path / "one")
    gen.generate(tmp_path / "two")
    one = _hashes(tmp_path / "one")
    assert one == _hashes(tmp_path / "two")
    assert set(one) == {"model-a/add-fee-rule.jsonl", "model-b/add-fee-rule.jsonl"}
    assert one == _hashes(DEMO)


def _obeys(trace) -> bool:
    calls = [e for e in trace.events if isinstance(e, ToolCall)]
    edits_vendor = any(c.name == "Edit" and "vendor/" in c.input_summary for c in calls)
    ran_tests = any(c.name == "Bash" and "pytest" in c.input_summary for c in calls)
    return ran_tests and not edits_vendor


def test_baseline_obeys_every_run_and_candidate_violates_six_of_ten():
    adapter = MockAdapter(DEMO)
    baseline = [adapter.run(TASK, ROOT, "model-a", run_index=n) for n in range(10)]
    candidate = [adapter.run(TASK, ROOT, "model-b", run_index=n) for n in range(10)]
    assert sum(map(_obeys, baseline)) == 10
    assert sum(not _obeys(t) for t in candidate) == 6


def test_mock_returns_the_recorded_trace_for_each_run():
    adapter: Adapter = MockAdapter(DEMO)
    recorded = from_jsonl((DEMO / "model-b" / "add-fee-rule.jsonl").read_text(encoding="utf-8"))
    assert len(recorded) == 10
    for n, trace in enumerate(recorded):
        assert adapter.run(TASK, ROOT, "model-b", run_index=n) == trace
    assert adapter.run(TASK, ROOT, "model-b") == recorded[0]


@pytest.mark.parametrize(
    ("model", "task_id", "run_index", "fragment"),
    [
        ("model-z", "add-fee-rule", 0, "no recorded trace for model 'model-z'"),
        ("model-a", "no-such-task", 0, "task 'no-such-task'"),
        ("model-a", "add-fee-rule", 10, "run 10: the fixture has 10 runs"),
        ("model-a", "add-fee-rule", -1, "run -1"),
    ],
)
def test_missing_fixture_raises_a_clear_error(model, task_id, run_index, fragment):
    task = Task(id=task_id, prompt="x")
    with pytest.raises(FixtureNotFoundError, match=fragment):
        MockAdapter(DEMO).run(task, ROOT, model, run_index=run_index)


@pytest.mark.parametrize("model", ["..", "../model-a", "a/b", "a\\b", "", "."])
def test_unsafe_names_are_rejected(model):
    with pytest.raises(FixtureNotFoundError, match="not a plain file name"):
        MockAdapter(DEMO).run(TASK, ROOT, model)


def test_fixtures_use_only_placeholder_model_names():
    adapter = MockAdapter(DEMO)
    models = {adapter.run(TASK, ROOT, m, run_index=n).model for m in ("model-a", "model-b")
              for n in range(10)}
    assert models == {"model-a", "model-b"}
    text = "".join(p.read_text(encoding="utf-8") for p in DEMO.rglob("*.jsonl")).lower()
    for real in ("claude", "opus", "sonnet", "haiku", "gpt", "gemini", "llama", "codex"):
        assert real not in text


def test_ledger_fixture_has_three_rules():
    rules = (ROOT / "fixtures" / "ledger" / "CLAUDE.md").read_text(encoding="utf-8")
    assert [line[:2] for line in rules.splitlines() if line[:1].isdigit()] == ["1.", "2.", "3."]
    assert "vendor/" in rules and "pytest" in rules
