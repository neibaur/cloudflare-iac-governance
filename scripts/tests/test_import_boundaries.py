from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SHEETS_DEPENDENCIES = ("gspread", "pandas")


def test_audit_entry_points_do_not_import_sheets_dependencies():
    # A fresh interpreter is required: this test session already imports aggregate_to_sheets, and
    # therefore gspread and pandas, while collecting other test modules.
    code = (
        "import sys\n"
        "import run_tools\n"
        "import scripts.cloudflare_client\n"
        f"print(','.join(name for name in {SHEETS_DEPENDENCIES!r} if name in sys.modules))\n"
    )
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", code],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == ""
