# churnbench

Will your agent setup survive the next model? churnbench aims to re-run your coding-agent tasks,
skills and instruction files against two model versions and give a pass or fail verdict on the
upgrade. That is the goal, not what it does today.

Status: early scaffold. Nothing beyond `churnbench --version` works yet.

## Develop

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer.

```
uv run churnbench --version
uv run scripts/check.py
```

`scripts/check.py` runs lint, tests and the package build. There is no CI in this repository; the
check runs on the maintainer's machine before every push.

## License

Code: Apache-2.0 (`LICENSE`). Prose and docs: CC BY 4.0 (`LICENSE-docs`).
