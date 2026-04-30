from __future__ import annotations

import os
import re
from datetime import UTC, datetime
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
INTERNAL_COLUMNS = ("__source_file", "__is_latest_snapshot")


def discover_audit_reports(reports_dir: Path = REPORTS_DIR) -> list[Path]:
    return sorted(
        (path for path in reports_dir.rglob("*.csv") if "security_compliance_report" in path.name),
        key=lambda path: path.name,
    )


def audit_date_from_filename(report_path: Path) -> str:
    match = REPORT_PATTERN.match(report_path.name)
    if match is None and report_path.name == LATEST_REPORT_NAME:
        modified_at = datetime.fromtimestamp(report_path.stat().st_mtime, UTC)
        return modified_at.strftime("%Y%m%dT%H%M%SZ")

    if match is None:
        raise ValueError(f"Report filename does not include a UTC audit timestamp: {report_path}")

    return match.group("audit_date")


def is_latest_report(report_path: Path) -> bool:
    return report_path.name == LATEST_REPORT_NAME


def build_domain_aliases(domain_names: pd.Series) -> dict[str, str]:
    domains = sorted({str(domain) for domain in domain_names.dropna()})
    width = max(2, len(str(len(domains))))
    return {domain: f"Domain {index:0{width}d}" for index, domain in enumerate(domains, start=1)}


def compliance_bit(value: object) -> int:
    if isinstance(value, bool):
        return int(value)

    return int(str(value).strip().lower() == "true")


def normalize_compliance_bits(dataframe: pd.DataFrame) -> pd.DataFrame:
    if "is_compliant" not in dataframe.columns:
        return dataframe

    normalized = dataframe.copy()
    normalized["is_compliant"] = normalized["is_compliant"].map(compliance_bit)
    return normalized


def snapshot_hour(audit_date: str) -> str:
    return audit_date[:11]


def snapshot_signature(dataframe: pd.DataFrame) -> tuple[tuple[object, ...], ...]:
    public_columns = [
        column for column in dataframe.columns if column not in {"audit_date", *INTERNAL_COLUMNS}
    ]
    comparable = dataframe[public_columns].sort_values(public_columns).fillna("")
    return tuple(tuple(row) for row in comparable.itertuples(index=False, name=None))


def drop_duplicate_latest_snapshots(dataframe: pd.DataFrame) -> pd.DataFrame:
    timestamped_signatures_by_hour: dict[str, set[tuple[tuple[object, ...], ...]]] = {}
    latest_sources_to_drop: set[str] = set()

    for source_file, snapshot in dataframe.groupby("__source_file", sort=False):
        audit_date = str(snapshot["audit_date"].iloc[0])
        hour = snapshot_hour(audit_date)
        signature = snapshot_signature(snapshot)
        if bool(snapshot["__is_latest_snapshot"].iloc[0]):
            if signature in timestamped_signatures_by_hour.get(hour, set()):
                latest_sources_to_drop.add(str(source_file))
            continue

        timestamped_signatures_by_hour.setdefault(hour, set()).add(signature)

    if not latest_sources_to_drop:
        return dataframe

    return dataframe[~dataframe["__source_file"].isin(latest_sources_to_drop)]


def aggregate_reports(reports_dir: Path = REPORTS_DIR) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for report_path in discover_audit_reports(reports_dir):
        frame = pd.read_csv(report_path)
        print(f"Discovered report: {report_path} ({len(frame)} rows)")
        frame.insert(0, "audit_date", audit_date_from_filename(report_path))
        frame["__source_file"] = str(report_path)
        frame["__is_latest_snapshot"] = is_latest_report(report_path)
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

    aggregated = normalize_compliance_bits(aggregated)
    aggregated = drop_duplicate_latest_snapshots(aggregated)
    aggregated = aggregated.drop(columns=list(INTERNAL_COLUMNS), errors="ignore")
    return aggregated.sort_values(["audit_date", "domain_name"], ignore_index=True)


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
