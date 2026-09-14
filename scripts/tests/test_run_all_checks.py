from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import run_all_checks


@pytest.fixture
def gate(monkeypatch, tmp_path):
    """Record every check command and every cleanup instead of running them."""
    calls: list[tuple[list[str], Path]] = []
    removed: list[Path] = []
    return_codes: dict[int, int] = {}

    def fake_run(command, cwd):
        calls.append((command, cwd))
        return subprocess.CompletedProcess(command, return_codes.get(len(calls), 0))

    monkeypatch.setattr(run_all_checks, "GATE_BASETEMP_ROOT", tmp_path / "gate")
    monkeypatch.setattr(run_all_checks.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_all_checks.shutil, "rmtree", lambda path, ignore_errors: removed.append(path)
    )
    return calls, removed, return_codes, tmp_path / "gate"


def basetemp_of(command: list[str]) -> Path:
    [option] = [part for part in command if part.startswith("--basetemp=")]
    return Path(option.removeprefix("--basetemp="))


def test_repository_root_is_the_checkout_root():
    assert (run_all_checks.REPOSITORY_ROOT / "pyproject.toml").is_file()
    assert (run_all_checks.REPOSITORY_ROOT / "scripts" / "run_all_checks.py").is_file()


def test_main_runs_every_check_from_the_repository_root_with_pytest_last(gate):
    calls, removed, _, gate_root = gate

    assert run_all_checks.main() == 0

    commands = [command for command, _ in calls]
    assert commands[:-1] == [command for _, command in run_all_checks.CHECKS]
    assert commands[-1][: len(run_all_checks.PYTEST_COMMAND)] == run_all_checks.PYTEST_COMMAND
    assert all(cwd == run_all_checks.REPOSITORY_ROOT for _, cwd in calls)
    assert gate_root.is_dir()
    assert basetemp_of(commands[-1]).parent == gate_root
    assert removed == [basetemp_of(commands[-1])]


def test_each_gate_run_uses_a_unique_basetemp(gate):
    calls, _, _, _ = gate

    run_all_checks.main()
    run_all_checks.main()

    pytest_commands = [command for command, _ in calls if "pytest" in command]
    assert len(pytest_commands) == 2
    assert basetemp_of(pytest_commands[0]) != basetemp_of(pytest_commands[1])


def test_main_stops_at_the_first_failure_and_still_cleans_up(gate, capsys):
    calls, removed, return_codes, _ = gate
    return_codes[2] = 3

    assert run_all_checks.main() == 3

    assert len(calls) == 2
    assert len(removed) == 1
    assert "Ruff format failed with exit code 3." in capsys.readouterr().err


def test_main_cleans_up_when_a_check_raises(gate, monkeypatch):
    _, removed, _, _ = gate

    def interrupted(command, cwd):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_all_checks.subprocess, "run", interrupted)

    with pytest.raises(KeyboardInterrupt):
        run_all_checks.main()

    assert len(removed) == 1
