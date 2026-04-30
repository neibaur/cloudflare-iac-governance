from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, cast

import gspread
import pandas as pd

REPORTS_DIR = Path(os.path.abspath(os.path.join("reports")))
SERVICE_ACCOUNT_FILE = Path("service_account.json")
MAIN_SHEET_NAME = "Cloudflare_Compliance_Main"
GOOGLE_SHEET_ID_ENV = "GOOGLE_SHEET_ID"
REPORT_PATTERN = re.compile(r"^(?P<audit_date>\d{8}T\d{6}Z)_security_compliance_report\.csv$")
LATEST_REPORT_NAME = "security_compliance_report.csv"
SENSITIVE_COLUMNS = ("zone_id",)


def discover_audit_reports(reports_dir: Path = REPORTS_DIR) -> list[Path]:
    return sorted(
        (path for path in reports_dir.rglob("*.csv") if "security_compliance_report" in path.name),
        key=lambda path: path.name,
    )


def audit_date_from_filename(report_path: Path) -> str:
    match = REPORT_PATTERN.match(report_path.name)
    if match is None and report_path.name == LATEST_REPORT_NAME:
        return "latest"

    if match is None:
        raise ValueError(f"Report filename does not include a UTC audit timestamp: {report_path}")

    return match.group("audit_date")


def build_domain_aliases(domain_names: pd.Series) -> dict[str, str]:
    domains = sorted({str(domain) for domain in domain_names.dropna()})
    width = max(2, len(str(len(domains))))
    return {domain: f"Domain {index:0{width}d}" for index, domain in enumerate(domains, start=1)}


def aggregate_reports(reports_dir: Path = REPORTS_DIR) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for report_path in discover_audit_reports(reports_dir):
        frame = pd.read_csv(report_path)
        print(f"Discovered report: {report_path} ({len(frame)} rows)")
        frame.insert(0, "audit_date", audit_date_from_filename(report_path))
        frame = frame.drop(columns=list(SENSITIVE_COLUMNS), errors="ignore")
        frames.append(frame)

    if not frames:
        raise RuntimeError(f"No compliance CSV reports found in {reports_dir}.")

    aggregated = pd.concat(frames, ignore_index=True)
    if aggregated.empty:
        raise RuntimeError(f"Compliance CSV reports in {reports_dir} did not contain any rows.")

    if "domain_name" in aggregated.columns:
        domain_aliases = build_domain_aliases(aggregated["domain_name"])
        aggregated["domain_name"] = aggregated["domain_name"].map(domain_aliases)

    return aggregated


def sheet_rows(dataframe: pd.DataFrame) -> list[list[Any]]:
    if dataframe.empty:
        return []

    sanitized = dataframe.fillna("")
    return [
        list(sanitized.columns),
        *cast(list[list[Any]], sanitized.values.tolist()),
    ]


def sync_to_google_sheets(
    dataframe: pd.DataFrame,
    credentials_path: Path = SERVICE_ACCOUNT_FILE,
    spreadsheet_id: str | None = None,
) -> None:
    sheet_id = spreadsheet_id or os.getenv(GOOGLE_SHEET_ID_ENV)
    if not sheet_id:
        raise RuntimeError(f"{GOOGLE_SHEET_ID_ENV} is required to sync compliance data.")

    client = gspread.service_account(filename=str(credentials_path))
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1
    rows = sheet_rows(dataframe)

    worksheet.clear()
    if rows:
        worksheet.update(rows)
    print(f"Success: wrote {len(dataframe)} compliance rows to Google Sheet ID {sheet_id}.")


def main() -> int:
    dataframe = aggregate_reports()
    sync_to_google_sheets(dataframe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
