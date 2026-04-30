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
    history_dir = report_workspace / "reports" / "audit_history"
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

    aggregated = aggregate_to_sheets.aggregate_reports(history_dir)

    assert "zone_id" not in aggregated.columns
    assert aggregated["audit_date"].tolist() == [
        "20260430T010000Z",
        "20260430T020000Z",
        "20260430T020000Z",
    ]
    assert aggregated["domain_name"].tolist() == ["Domain 01", "Domain 02", "Domain 01"]


def test_aggregate_reports_ignores_non_utc_csvs(report_workspace):
    history_dir = report_workspace / "reports" / "audit_history"
    history_dir.mkdir(parents=True)
    write_report(
        history_dir / "security_compliance_report.csv",
        [{"domain_name": "ignored.example", "zone_id": "zone-id"}],
    )

    assert aggregate_to_sheets.aggregate_reports(history_dir).empty


def test_sync_to_google_sheets_overwrites_main_sheet(mocker):
    worksheet = mocker.Mock(name="worksheet")
    spreadsheet = mocker.Mock(name="spreadsheet", sheet1=worksheet)
    client = mocker.Mock(name="client")
    client.open.return_value = spreadsheet
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

    aggregate_to_sheets.sync_to_google_sheets(dataframe, Path("service_account.json"))

    service_account.assert_called_once_with(filename="service_account.json")
    client.open.assert_called_once_with("Cloudflare_Compliance_Main")
    worksheet.clear.assert_called_once_with()
    worksheet.update.assert_called_once_with(
        [["audit_date", "domain_name", "is_compliant"], ["20260430T010000Z", "Domain 01", True]]
    )
