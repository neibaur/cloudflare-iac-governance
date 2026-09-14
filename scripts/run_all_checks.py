from __future__ import annotations

import shutil
import subprocess  # nosec B404
import sys
import uuid
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
# pytest empties its basetemp when a run starts, so each gate run gets its own directory. A plain
# pytest run uses .pytest_tmp from pyproject.toml and can't delete a concurrent gate run's files.
GATE_BASETEMP_ROOT = REPOSITORY_ROOT / ".pytest_gate_tmp"

CHECKS = (
    ("Ruff lint", [sys.executable, "-m", "ruff", "check", "."]),
    ("Ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("mypy", [sys.executable, "-m", "mypy", "scripts/"]),
    (
        "Bandit security scan",
        [sys.executable, "-m", "bandit", "-r", "scripts/", "--severity-level", "medium"],
    ),
)
PYTEST_COMMAND = [sys.executable, "-m", "pytest", "scripts/tests/"]


def main() -> int:
    run_basetemp = GATE_BASETEMP_ROOT / uuid.uuid4().hex
    checks = (
        *CHECKS,
        ("pytest coverage", [*PYTEST_COMMAND, f"--basetemp={run_basetemp}"]),
    )
    GATE_BASETEMP_ROOT.mkdir(exist_ok=True)
    try:
        for name, command in checks:
            print(f"Running {name}...", flush=True)
            completed = subprocess.run(command, cwd=REPOSITORY_ROOT)  # nosec B603
            if completed.returncode != 0:
                print(f"{name} failed with exit code {completed.returncode}.", file=sys.stderr)
                return completed.returncode
    finally:
        shutil.rmtree(run_basetemp, ignore_errors=True)

    print("All quality checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
