import shutil
from pathlib import Path

import pytest

from scripts import check_compliance_gaps


@pytest.fixture
def report_workspace():
    root = Path("pytest-cache-files-gaps")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()

    yield root

    shutil.rmtree(root, ignore_errors=True)


def write_report(path: Path, compliant_values: list[str]) -> None:
    rows = ["domain_name,is_compliant"]
    rows.extend(f"Domain {index:02d},{value}" for index, value in enumerate(compliant_values, 1))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_count_security_gaps_handles_integer_and_boolean_values(report_workspace):
    report = report_workspace / "security_compliance_report.csv"
    write_report(report, ["1", "true", "0", "false"])

    assert check_compliance_gaps.count_security_gaps(report) == 2


def test_count_security_gaps_requires_existing_report(report_workspace):
    with pytest.raises(RuntimeError, match="Compliance report not found"):
        check_compliance_gaps.count_security_gaps(report_workspace / "missing.csv")


def test_main_returns_failure_when_gaps_exist(monkeypatch):
    monkeypatch.setattr(check_compliance_gaps, "count_security_gaps", lambda: 1)

    assert check_compliance_gaps.main() == 1


def test_main_returns_success_when_no_gaps_exist(monkeypatch):
    monkeypatch.setattr(check_compliance_gaps, "count_security_gaps", lambda: 0)

    assert check_compliance_gaps.main() == 0
