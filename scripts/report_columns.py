"""Column names shared by the audit report and the Google Sheets aggregation.

Kept free of third-party imports so the audit can use them without loading the Sheets dependencies.
"""

AUDIT_DATE_COLUMN = "audit_date"
INTERNAL_COLUMNS = ("__source_file", "__is_latest_snapshot")
# Columns the aggregation adds to report rows, so no security control may use them.
RESERVED_REPORT_COLUMNS = (AUDIT_DATE_COLUMN, *INTERNAL_COLUMNS)
