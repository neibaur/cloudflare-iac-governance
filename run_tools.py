from __future__ import annotations

import argparse
import re
from pathlib import Path

from scripts.cloudflare_client import CloudflareAuditor

TOKEN_FILE = Path("terraform/secrets.auto.tfvars")
TOKEN_PATTERN = re.compile(r'cloudflare_api_token\s*=\s*"([^"]+)"')


def read_cloudflare_token(path: Path = TOKEN_FILE) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to read Cloudflare token file: {path}") from exc

    match = TOKEN_PATTERN.search(content)
    if match is None:
        raise RuntimeError(f"cloudflare_api_token was not found in {path}")

    return match.group(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Cloudflare IaC helper tools.")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--verify", action="store_true", help="Verify the Cloudflare API token.")
    actions.add_argument(
        "--list",
        action="store_true",
        help="Print Terraform HCL for accessible zones.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    auditor = CloudflareAuditor(read_cloudflare_token())

    if args.verify:
        print(auditor.verify_connection())
        return 0

    if args.list:
        auditor.list_all_zones()
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
