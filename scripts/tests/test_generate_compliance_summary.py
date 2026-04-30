import shutil
from pathlib import Path

import pytest

from scripts import generate_compliance_summary


class FakeReportRoot:
    def rglob(self, pattern):
        assert pattern == "*_security_compliance_report.csv"
        return [
            Path("security_compliance_report.csv"),
            Path("20260430T020000Z_security_compliance_report.csv"),
            Path("notes_security_compliance_report.csv"),
            Path("20260430T010000Z_security_compliance_report.csv"),
        ]


@pytest.fixture
def report_workspace():
    root = Path("pytest-cache-files-dataops")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()

    yield root

    shutil.rmtree(root, ignore_errors=True)


def test_discover_reports_uses_only_utc_stamped_reports():
    assert [
        path.name for path in generate_compliance_summary.discover_reports(FakeReportRoot())
    ] == [
        "20260430T010000Z_security_compliance_report.csv",
        "20260430T020000Z_security_compliance_report.csv",
    ]


def test_compliance_trend_reports_start_and_end(monkeypatch):
    reports = [
        Path("20260430T010000Z_security_compliance_report.csv"),
        Path("20260430T020000Z_security_compliance_report.csv"),
    ]
    monkeypatch.setattr(generate_compliance_summary, "discover_reports", lambda _root: reports)
    monkeypatch.setattr(
        generate_compliance_summary,
        "compliance_percentage",
        lambda path: 0.0 if path == reports[0] else 100.0,
    )

    assert generate_compliance_summary.compliance_trend(Path(".")) == (
        "Compliance Trend: Started at 0%, ended at 100% across 2 reports."
    )


def write_report(path: Path, compliant_values: list[str]) -> None:
    rows = ["domain_name,is_compliant"]
    rows.extend(f"example-{index}.test,{value}" for index, value in enumerate(compliant_values))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_compliance_percentage_counts_only_true_values(report_workspace):
    report = report_workspace / "20260430T010000Z_security_compliance_report.csv"
    write_report(report, ["true", " TRUE ", "false", ""])

    assert generate_compliance_summary.compliance_percentage(report) == 50.0


def test_compliance_percentage_returns_zero_for_empty_report(report_workspace):
    report = report_workspace / "20260430T010000Z_security_compliance_report.csv"
    report.write_text("domain_name,is_compliant\n", encoding="utf-8")

    assert generate_compliance_summary.compliance_percentage(report) == 0.0


def test_compliance_trend_calculates_zero_to_one_hundred_from_multiple_csvs(report_workspace):
    reports_dir = report_workspace / "reports"
    history_dir = reports_dir / "audit_history"
    history_dir.mkdir(parents=True)

    write_report(history_dir / "20260430T010000Z_security_compliance_report.csv", ["false"])
    write_report(history_dir / "20260430T020000Z_security_compliance_report.csv", ["true", "false"])
    write_report(reports_dir / "20260430T030000Z_security_compliance_report.csv", ["true", "true"])
    write_report(reports_dir / "security_compliance_report.csv", ["false"])
    write_report(reports_dir / "notes_security_compliance_report.csv", ["false"])

    assert generate_compliance_summary.compliance_trend(reports_dir) == (
        "Compliance Trend: Started at 0%, ended at 100% across 3 reports."
    )


def test_compliance_trend_reports_when_no_utc_stamped_reports(report_workspace):
    reports_dir = report_workspace / "reports"
    reports_dir.mkdir()
    write_report(reports_dir / "security_compliance_report.csv", ["true"])

    assert (
        generate_compliance_summary.compliance_trend(reports_dir)
        == "No UTC-stamped compliance reports found."
    )


def test_main_prints_default_report_trend(monkeypatch, capsys):
    monkeypatch.setattr(
        generate_compliance_summary,
        "compliance_trend",
        lambda root: f"summary for {root}",
    )

    assert generate_compliance_summary.main() == 0
    assert capsys.readouterr().out == "summary for reports\n"
