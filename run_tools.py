from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from scripts.cloudflare_client import CloudflareAuditor

ENV_FILE = Path(".env")
REPORT_DIR = Path("reports")
CLOUDFLARE_API_TOKEN = "CLOUDFLARE_API_TOKEN"
CLOUDFLARE_ACCOUNT_ID = "CLOUDFLARE_ACCOUNT_ID"
TOKEN_EXPIRY_WARNING_DAYS = 14


def warn_if_token_expires_soon(
    verification: dict[str, object],
    *,
    now: datetime | None = None,
) -> None:
    """Warn on stderr when Cloudflare reports an expired or soon-expiring token."""
    expires_on = verification.get("expires_on")
    if not isinstance(expires_on, str):
        return

    try:
        expires_at = datetime.fromisoformat(expires_on.replace("Z", "+00:00"))
    except ValueError:
        return
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    current_time = now or datetime.now(UTC)
    if expires_at <= current_time:
        print(f"ERROR: Cloudflare API token expired on {expires_on}.", file=sys.stderr)
    elif expires_at <= current_time + timedelta(days=TOKEN_EXPIRY_WARNING_DAYS):
        print(
            f"WARNING: Cloudflare API token expires on {expires_on} "
            f"(within {TOKEN_EXPIRY_WARNING_DAYS} days).",
            file=sys.stderr,
        )


def read_cloudflare_env(env_file: Path = ENV_FILE) -> tuple[str, str]:
    load_dotenv(env_file)

    token = os.getenv(CLOUDFLARE_API_TOKEN)
    account_id = os.getenv(CLOUDFLARE_ACCOUNT_ID)

    if not token:
        raise RuntimeError(f"{CLOUDFLARE_API_TOKEN} was not found in {env_file}")
    if not account_id:
        raise RuntimeError(f"{CLOUDFLARE_ACCOUNT_ID} was not found in {env_file}")

    return token, account_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Cloudflare IaC helper tools.")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--verify", action="store_true", help="Verify the Cloudflare API token.")
    actions.add_argument(
        "--list",
        action="store_true",
        help="Print Terraform HCL for accessible zones.",
    )
    actions.add_argument(
        "--audit",
        action="store_true",
        help="Audit Cloudflare zone security settings.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token, account_id = read_cloudflare_env()
    with CloudflareAuditor(token, account_id) as auditor:
        verification = auditor.verify_connection()
        warn_if_token_expires_soon(verification)

        if args.verify:
            print(verification)
            return 0

        if args.list:
            auditor.list_all_zones()
            return 0

        if args.audit:
            auditor.audit_security_posture(REPORT_DIR)
            return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
