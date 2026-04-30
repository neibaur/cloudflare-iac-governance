from __future__ import annotations

import csv
import re
from pathlib import Path

REPORT_PATTERN = re.compile(r"^\d{8}T\d{6}Z_security_compliance_report\.csv$")


def is_compliant_value(value: str) -> bool:
    return value.strip().lower() == "true"


def compliance_percentage(report_path: Path) -> float:
    with report_path.open(encoding="utf-8", newline="") as report_file:
        rows = list(csv.DictReader(report_file))

    if not rows:
        return 0.0

    compliant_count = sum(1 for row in rows if is_compliant_value(row.get("is_compliant", "false")))
    return compliant_count / len(rows) * 100


def discover_reports(root_dir: Path = Path(".")) -> list[Path]:
    return sorted(
        path
        for path in root_dir.glob("*_security_compliance_report.csv")
        if REPORT_PATTERN.match(path.name)
    )


def compliance_trend(root_dir: Path = Path(".")) -> str:
    reports = discover_reports(root_dir)
    if not reports:
        return "No UTC-stamped compliance reports found."

    start = compliance_percentage(reports[0])
    end = compliance_percentage(reports[-1])
    return (
        f"Compliance Trend: Started at {start:.0f}%, ended at {end:.0f}% "
        f"across {len(reports)} reports."
    )


def main() -> int:
    print(compliance_trend())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
