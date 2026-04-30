import shutil
from pathlib import Path

import pandas as pd
import pytest

from scripts import aggregate_to_sheets


@pytest.fixture
def report_workspace():
    root = Path("pytest-cache-files-sheets")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()

    yield root

    shutil.rmtree(root, ignore_errors=True)


def write_report(path: Path, rows: list[dict[str, object]]) -> None:
    dataframe = pd.DataFrame(rows)
    dataframe.to_csv(path, index=False)


def test_aggregate_reports_masks_zone_ids_and_aliases_domains(report_workspace):
    reports_dir = report_workspace / "reports"
    history_dir = reports_dir / "audit_history"
    history_dir.mkdir(parents=True)
    write_report(
        history_dir / "20260430T020000Z_security_compliance_report.csv",
        [
            {
                "domain_name": "zeta.example",
                "zone_id": "zone-zeta",
                "ssl_mode": "full",
                "is_compliant": True,
            },
            {
                "domain_name": "alpha.example",
                "zone_id": "zone-alpha",
                "ssl_mode": "full",
                "is_compliant": False,
            },
        ],
    )
    write_report(
        history_dir / "20260430T010000Z_security_compliance_report.csv",
        [
            {
                "domain_name": "alpha.example",
                "zone_id": "zone-alpha",
                "ssl_mode": "flexible",
                "is_compliant": False,
            }
        ],
    )

    write_report(
        reports_dir / "security_compliance_report.csv",
        [
            {
                "domain_name": "zeta.example",
                "zone_id": "zone-zeta",
                "ssl_mode": "full",
                "is_compliant": True,
            }
        ],
    )

    aggregated = aggregate_to_sheets.aggregate_reports(reports_dir)

    assert "zone_id" not in aggregated.columns
    assert aggregated["audit_date"].tolist() == [
        "20260430T010000Z",
        "20260430T020000Z",
        "20260430T020000Z",
        "latest",
    ]
    assert aggregated["domain_name"].tolist() == [
        "Domain 01",
        "Domain 02",
        "Domain 01",
        "Domain 02",
    ]


def test_aggregate_reports_logs_each_discovered_file(report_workspace, capsys):
    reports_dir = report_workspace / "reports"
    reports_dir.mkdir()
    write_report(
        reports_dir / "security_compliance_report.csv",
        [{"domain_name": "example.test", "zone_id": "zone-id"}],
    )

    aggregate_to_sheets.aggregate_reports(reports_dir)

    output = capsys.readouterr().out
    assert "Discovered report:" in output
    assert "security_compliance_report.csv (1 rows)" in output


def test_aggregate_reports_fails_when_no_matching_csvs(report_workspace):
    reports_dir = report_workspace / "reports"
    reports_dir.mkdir()
    write_report(reports_dir / "other_report.csv", [{"domain_name": "ignored.example"}])

    with pytest.raises(RuntimeError, match="No compliance CSV reports found"):
        aggregate_to_sheets.aggregate_reports(reports_dir)


def test_aggregate_reports_fails_when_matching_csvs_are_empty(report_workspace):
    reports_dir = report_workspace / "reports"
    reports_dir.mkdir()
    (reports_dir / "security_compliance_report.csv").write_text(
        "domain_name,zone_id,is_compliant\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="did not contain any rows"):
        aggregate_to_sheets.aggregate_reports(reports_dir)


def test_sync_to_google_sheets_overwrites_main_sheet(mocker):
    worksheet = mocker.Mock(name="worksheet")
    spreadsheet = mocker.Mock(name="spreadsheet", sheet1=worksheet)
    client = mocker.Mock(name="client")
    client.open_by_key.return_value = spreadsheet
    service_account = mocker.patch(
        "scripts.aggregate_to_sheets.gspread.service_account",
        return_value=client,
    )
    dataframe = pd.DataFrame(
        [
            {
                "audit_date": "20260430T010000Z",
                "domain_name": "Domain 01",
                "is_compliant": True,
            }
        ]
    )

    aggregate_to_sheets.sync_to_google_sheets(
        dataframe,
        Path("service_account.json"),
        spreadsheet_id="sheet-id-123",
    )

    service_account.assert_called_once_with(filename="service_account.json")
    client.open_by_key.assert_called_once_with("sheet-id-123")
    worksheet.clear.assert_called_once_with()
    worksheet.update.assert_called_once_with(
        [["audit_date", "domain_name", "is_compliant"], ["20260430T010000Z", "Domain 01", True]]
    )


def test_sync_to_google_sheets_requires_sheet_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_SHEET_ID"):
        aggregate_to_sheets.sync_to_google_sheets(pd.DataFrame())
