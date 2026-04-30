from pathlib import Path

from scripts import generate_compliance_summary


class FakeReportRoot:
    def glob(self, pattern):
        assert pattern == "*_security_compliance_report.csv"
        return [
            Path("security_compliance_report.csv"),
            Path("20260430T020000Z_security_compliance_report.csv"),
            Path("notes_security_compliance_report.csv"),
            Path("20260430T010000Z_security_compliance_report.csv"),
        ]


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
