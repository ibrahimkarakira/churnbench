# Ledger: rules for coding agents

This is an invented demo repository for churnbench. Follow these rules on every task.

1. Never edit anything under `vendor/`. It is a vendored copy; change `ledger.py` instead.
2. Run `python -m pytest -q` before you finish, and say whether it passed.
3. Every behaviour change gets a test in `tests/`.
