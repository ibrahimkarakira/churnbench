"""Command line entry point."""

import argparse
from collections.abc import Sequence

from churnbench import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="churnbench",
        description="Re-run coding-agent tasks across model versions and gate the upgrade.",
    )
    parser.add_argument("--version", action="version", version=f"churnbench {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
