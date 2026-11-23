"""Run the full local check: lint, tests, build. Stops at the first failure.

Usage: uv run scripts/check.py
There is no CI in this repository; this is the gate every PR pastes the output of.
"""

import subprocess
import sys

STEPS = (
    ("uv", "run", "ruff", "check"),
    ("uv", "run", "python", "-m", "pytest", "-q"),
    ("uv", "build"),
)


def main() -> int:
    for cmd in STEPS:
        print(f"== {' '.join(cmd)}", flush=True)
        code = subprocess.run(cmd).returncode
        if code != 0:
            print(f"== FAILED ({code}): {' '.join(cmd)}", flush=True)
            return code
    print("== all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
