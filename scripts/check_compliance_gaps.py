from __future__ import annotations

import csv
from pathlib import Path

LATEST_REPORT = Path("reports/security_compliance_report.csv")


def compliant_value(value: str) -> bool:
    return value.strip().lower() in {"1", "true"}


def count_security_gaps(report_path: Path = LATEST_REPORT) -> int:
    if not report_path.exists():
        raise RuntimeError(f"Compliance report not found: {report_path}")

    with report_path.open(encoding="utf-8", newline="") as report_file:
        rows = list(csv.DictReader(report_file))

    if not rows:
        raise RuntimeError(f"Compliance report has no rows: {report_path}")

    return sum(1 for row in rows if not compliant_value(row.get("is_compliant", "0")))


def main() -> int:
    gap_count = count_security_gaps()
    if gap_count:
        print(f"Detected {gap_count} non-compliant domain(s).")
        return 1

    print("No compliance gaps detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
