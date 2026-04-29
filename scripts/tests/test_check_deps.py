from __future__ import annotations

import subprocess
from types import SimpleNamespace

from scripts import check_deps


def test_dependency_version_returns_none_for_missing_package(monkeypatch):
    def missing_version(package_name):
        raise check_deps.metadata.PackageNotFoundError(package_name)

    monkeypatch.setattr(check_deps.metadata, "version", missing_version)

    assert check_deps.dependency_version("missing-package") is None


def test_check_python_dependency_reports_available_module(monkeypatch, capsys):
    monkeypatch.setattr(check_deps.util, "find_spec", lambda module: object())
    monkeypatch.setattr(check_deps, "dependency_version", lambda display_name: "1.2.3")

    assert check_deps.check_python_dependency("example", ("example",))

    captured = capsys.readouterr()
    assert "example: available via module 'example' (1.2.3)" in captured.out


def test_check_python_dependency_reports_missing_module(monkeypatch, capsys):
    monkeypatch.setattr(check_deps.util, "find_spec", lambda module: None)

    assert not check_deps.check_python_dependency("example", ("example",))

    captured = capsys.readouterr()
    assert "example was not found" in captured.err


def test_main_passes_when_all_dependencies_are_available(monkeypatch, capsys):
    monkeypatch.setattr(check_deps.shutil, "which", lambda command: "terraform.exe")
    monkeypatch.setattr(
        check_deps.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="Terraform v1.15.0\n"),
    )
    monkeypatch.setattr(check_deps, "check_python_dependency", lambda *args, **kwargs: True)

    assert check_deps.main() == 0

    captured = capsys.readouterr()
    assert "Terraform binary: terraform.exe" in captured.out
    assert "Terraform v1.15.0" in captured.out


def test_main_fails_when_terraform_is_missing(monkeypatch, capsys):
    monkeypatch.setattr(check_deps.shutil, "which", lambda command: None)
    monkeypatch.setattr(check_deps, "check_python_dependency", lambda *args, **kwargs: True)

    assert check_deps.main() == 1

    captured = capsys.readouterr()
    assert "Terraform was not found" in captured.err


def test_main_fails_when_terraform_cannot_run(monkeypatch, capsys):
    def fail_run(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])

    monkeypatch.setattr(check_deps.shutil, "which", lambda command: "terraform.exe")
    monkeypatch.setattr(check_deps.subprocess, "run", fail_run)
    monkeypatch.setattr(check_deps, "check_python_dependency", lambda *args, **kwargs: True)

    assert check_deps.main() == 1

    captured = capsys.readouterr()
    assert "could not run" in captured.err


def test_main_fails_when_python_dependency_is_missing(monkeypatch):
    dependency_results = iter([True, False, True, True])

    monkeypatch.setattr(check_deps.shutil, "which", lambda command: "terraform.exe")
    monkeypatch.setattr(
        check_deps.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="Terraform v1.15.0\n"),
    )
    monkeypatch.setattr(
        check_deps,
        "check_python_dependency",
        lambda *args, **kwargs: next(dependency_results),
    )

    assert check_deps.main() == 1
