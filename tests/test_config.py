from pathlib import Path

import pytest

from churnbench.config import (
    AdapterOptions,
    Check,
    Config,
    ConfigError,
    Invariant,
    Matrix,
    Project,
    Side,
    Task,
    Variant,
    Verdict,
    load,
    loads,
)

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "churnbench.toml"

MINIMAL = """
[project]
name = "demo"
workdir = "fixtures/ledger"

[matrix]
baseline = "mock:model-a"
candidate = "mock:model-b"
runs = 3

[[task]]
id = "t1"
prompt = "Do the thing."
"""


def test_example_loads_and_equals_expected_object():
    expected = Config(
        project=Project(name="ledger-demo", workdir="fixtures/ledger"),
        matrix=Matrix(
            baseline=Side(adapter="claude-code", model="model-a"),
            candidate=Side(adapter="claude-code", model="model-b"),
            runs=10,
            max_budget_usd=5.0,
        ),
        tasks=(
            Task(
                id="add-fee-rule",
                prompt="Add a 2 percent fee to transfers over 1000 and update tests.",
                timeout_s=300,
                checks=(Check(kind="command", run="python -m pytest -q", expect_exit=0),),
                invariants=(
                    Invariant(kind="never_edit", path_glob="vendor/**"),
                    Invariant(kind="tool_before_finish", tool="Bash", contains="pytest"),
                ),
            ),
        ),
        adapters={
            "claude-code": AdapterOptions(
                mode="project",
                permission_mode="dontAsk",
                allowed_tools=("Read", "Edit", "Bash(python -m pytest *)"),
            )
        },
        variants={"candidate": Variant(overlay="variants/claude-md-v2")},
        verdict=Verdict(alpha=0.05, min_drop=0.20, min_runs=5),
    )
    assert load(EXAMPLE) == expected


def test_minimal_config_gets_defaults():
    cfg = loads(MINIMAL)
    assert cfg.verdict == Verdict()
    assert cfg.matrix.max_budget_usd is None
    assert cfg.tasks[0].timeout_s == 300
    assert cfg.adapters == {} and cfg.variants == {}


def test_config_is_frozen():
    cfg = loads(MINIMAL)
    with pytest.raises(AttributeError):
        cfg.matrix.runs = 99  # type: ignore[misc]
    with pytest.raises(TypeError):
        cfg.adapters["x"] = AdapterOptions()  # type: ignore[index]


def test_model_id_may_contain_colons():
    cfg = loads(MINIMAL.replace('"mock:model-b"', '"command:llama3:8b"'))
    assert cfg.matrix.candidate == Side(adapter="command", model="llama3:8b")


def _fails(text: str, *fragments: str) -> str:
    with pytest.raises(ConfigError) as exc:
        loads(text, source="cfg.toml")
    msg = str(exc.value)
    assert msg.startswith("cfg.toml: ")
    for fragment in fragments:
        assert fragment in msg, msg
    return msg


def test_missing_matrix_names_the_key():
    text = MINIMAL.split("[matrix]")[0] + MINIMAL.split("runs = 3")[1]
    _fails(text, "matrix: missing required key")


def test_unknown_key_suggests_the_closest_name():
    _fails(MINIMAL.replace("runs = 3", "runs = 3\nrun = 2"), "matrix.run: unknown key", "'runs'")


def test_unknown_key_without_close_match_lists_allowed_keys():
    _fails(MINIMAL + '\n[zzz]\na = 1\n', "zzz: unknown key", "allowed:", "matrix")


@pytest.mark.parametrize("runs", ["0", "-1"])
def test_runs_below_one_rejected(runs):
    _fails(MINIMAL.replace("runs = 3", f"runs = {runs}"), "matrix.runs", ">= 1")


def test_wrong_type_rejected_and_bool_is_not_an_int():
    _fails(MINIMAL.replace("runs = 3", 'runs = "3"'), "matrix.runs", "expected integer")
    _fails(MINIMAL.replace("runs = 3", "runs = true"), "matrix.runs", "expected integer")


def test_side_without_adapter_prefix_rejected():
    _fails(MINIMAL.replace('"mock:model-a"', '"model-a"'), "matrix.baseline", "adapter:model")


def test_duplicate_task_ids_rejected():
    _fails(MINIMAL + '\n[[task]]\nid = "t1"\nprompt = "again"\n', "task[1].id", "duplicate")


def test_no_tasks_rejected():
    _fails(MINIMAL.split("[[task]]")[0], "task: missing required key")


def test_unknown_invariant_kind_rejected_with_suggestion():
    text = MINIMAL + '[[task.invariant]]\nkind = "never_edits"\npath_glob = "x"\n'
    _fails(text, "task[0].invariant[0].kind", "'never_edit'")


def test_invariant_missing_required_field():
    _fails(MINIMAL + '[[task.invariant]]\nkind = "never_edit"\n', "path_glob: missing")


def test_check_without_run_rejected():
    _fails(MINIMAL + '[[task.check]]\nkind = "command"\n', "task[0].check[0].run: missing")


@pytest.mark.parametrize(
    ("line", "key"),
    [("alpha = 1.5", "verdict.alpha"), ("min_drop = 0", "verdict.min_drop"),
     ("min_runs = 0", "verdict.min_runs")],
)
def test_verdict_thresholds_range_checked(line, key):
    _fails(MINIMAL + f"\n[verdict]\n{line}\n", key)


def test_variant_side_must_be_baseline_or_candidate():
    _fails(MINIMAL + '\n[variant.candidat]\noverlay = "v"\n', "variant.candidat", "'candidate'")


def test_invalid_toml_reports_source():
    _fails("[matrix\n", "invalid TOML")


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load(tmp_path / "nope.toml")


def test_adapter_options_validated():
    _fails(MINIMAL + '\n[adapter.mock]\nmod = "bare"\n', "adapter.mock.mod: unknown key", "'mode'")
    _fails(MINIMAL + '\n[adapter.mock]\nmode = "naked"\n', "adapter.mock.mode", "allowed:")
