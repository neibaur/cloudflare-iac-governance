from __future__ import annotations

import subprocess  # nosec B404
import sys

CHECKS = (
    ("Ruff lint", [sys.executable, "-m", "ruff", "check", "."]),
    ("Ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("mypy", [sys.executable, "-m", "mypy", "scripts/"]),
    (
        "Bandit security scan",
        [sys.executable, "-m", "bandit", "-r", "scripts/", "--severity-level", "medium"],
    ),
    (
        "pytest coverage",
        [
            sys.executable,
            "-m",
            "pytest",
            "scripts/tests/",
        ],
    ),
)


def main() -> int:
    for name, command in CHECKS:
        print(f"Running {name}...", flush=True)
        completed = subprocess.run(command)  # nosec B603
        if completed.returncode != 0:
            print(f"{name} failed with exit code {completed.returncode}.", file=sys.stderr)
            return completed.returncode

    print("All quality checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
