# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Set up

Install [uv](https://docs.astral.sh/uv/), then from the repository root:

```
uv run churnbench --version
uv run scripts/check.py
```

`scripts/check.py` runs `ruff check`, `pytest` and `uv build`, stops at the first failure and exits
with its code. There is no CI here, so please paste its output in your pull request.

## Pull requests

- Open or link an issue first and say what problem the change solves.
- Add a test that fails before your change and passes after it.
- Keep runtime dependencies at zero; the standard library covers this tool's needs.
- Tests run offline. Anything that calls a real model must be opt-in.
- Say whether AI tools helped write the change.

By contributing you agree that your code is licensed under Apache-2.0 and your prose under CC BY 4.0.
