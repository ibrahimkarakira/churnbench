import pytest

from churnbench import __version__
from churnbench.cli import main


def test_version_flag_prints_name_and_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"churnbench {__version__}"


def test_version_is_0_0_1():
    assert __version__ == "0.0.1"


def test_no_arguments_prints_help_and_exits_0(capsys):
    assert main([]) == 0
    assert "usage: churnbench" in capsys.readouterr().out
