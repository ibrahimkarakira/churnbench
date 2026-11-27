# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

- Add the package skeleton, `churnbench --version` and the local check script `scripts/check.py` (#1).
- Add the `churnbench.toml` loader with key-path error messages and an example config (#3).
- Add the normalized trace model with a JSONL round trip and `docs/trace-format.md` (#10).
- Add the mock replay adapter, a seeded demo fixture generator and the invented `fixtures/ledger` repo (#11).
- Add the per-run sandbox copy with overlay and `command` outcome checks with exit code, output tail and timeout (#12).
- Add the tool-call sequence diff (missing, extra, reordered calls per candidate run against the most common baseline sequence) (#18).
