from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import gspread
import pandas as pd

AUDIT_HISTORY_DIR = Path("reports/audit_history")
SERVICE_ACCOUNT_FILE = Path("service_account.json")
MAIN_SHEET_NAME = "Cloudflare_Compliance_Main"
REPORT_PATTERN = re.compile(r"^(?P<audit_date>\d{8}T\d{6}Z)_security_compliance_report\.csv$")
SENSITIVE_COLUMNS = ("zone_id",)


def discover_audit_reports(audit_history_dir: Path = AUDIT_HISTORY_DIR) -> list[Path]:
    return sorted(
        (
            path
            for path in audit_history_dir.glob("*_security_compliance_report.csv")
            if REPORT_PATTERN.match(path.name)
        ),
        key=lambda path: path.name,
    )


def audit_date_from_filename(report_path: Path) -> str:
    match = REPORT_PATTERN.match(report_path.name)
    if match is None:
        raise ValueError(f"Report filename does not include a UTC audit timestamp: {report_path}")

    return match.group("audit_date")


def build_domain_aliases(domain_names: pd.Series) -> dict[str, str]:
    domains = sorted({str(domain) for domain in domain_names.dropna()})
    width = max(2, len(str(len(domains))))
    return {domain: f"Domain {index:0{width}d}" for index, domain in enumerate(domains, start=1)}


def aggregate_reports(audit_history_dir: Path = AUDIT_HISTORY_DIR) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for report_path in discover_audit_reports(audit_history_dir):
        frame = pd.read_csv(report_path)
        frame.insert(0, "audit_date", audit_date_from_filename(report_path))
        frame = frame.drop(columns=list(SENSITIVE_COLUMNS), errors="ignore")
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    aggregated = pd.concat(frames, ignore_index=True)
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
    sheet_name: str = MAIN_SHEET_NAME,
) -> None:
    client = gspread.service_account(filename=str(credentials_path))
    spreadsheet = client.open(sheet_name)
    worksheet = spreadsheet.sheet1
    rows = sheet_rows(dataframe)

    worksheet.clear()
    if rows:
        worksheet.update(rows)


def main() -> int:
    dataframe = aggregate_reports()
    sync_to_google_sheets(dataframe)
    print(f"Synced {len(dataframe)} compliance rows to {MAIN_SHEET_NAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
