from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import httpx

from scripts.security_standard import (
    BOT_MANAGEMENT_RESOURCE,
    ZONE_SETTING_RESOURCE,
    SecurityControl,
    expected_values,
    load_security_standard,
    validate_controls,
)

# Compatibility mapping: the ssl control keeps its historical CSV column name.
CSV_COLUMN_BY_CONTROL = {"ssl": "ssl_mode"}
# Columns that existed before the policy file, kept first and in their original order so existing
# report consumers see a stable layout. Any other control column follows in policy order.
LEGACY_CONTROL_COLUMNS = ("ssl_mode", "always_use_https", "security_level", "bot_fight_mode")


def csv_column(control: SecurityControl) -> str:
    return CSV_COLUMN_BY_CONTROL.get(control.key, control.key)


def security_csv_headers(controls: tuple[SecurityControl, ...]) -> tuple[str, ...]:
    """Return report headers for the configured controls, preserving the legacy column order."""
    columns = [csv_column(control) for control in controls]
    reserved = {"domain_name", "zone_id", "is_compliant"}
    if len(set(columns)) != len(columns) or reserved.intersection(columns):
        raise ValueError(
            "Security controls must map to unique CSV columns that do not reuse "
            "domain_name, zone_id, or is_compliant."
        )
    legacy = [column for column in LEGACY_CONTROL_COLUMNS if column in columns]
    additional = [column for column in columns if column not in LEGACY_CONTROL_COLUMNS]
    return ("domain_name", "zone_id", *legacy, *additional, "is_compliant")


LATEST_SECURITY_REPORT = "security_compliance_report.csv"
DEFAULT_REPORT_DIR = Path("reports")

ACCOUNT_TOKEN_VERIFY_SUFFIX = "/tokens/verify"
USER_TOKEN_VERIFY_PATH = "/user/tokens/verify"
REDACTED_ACCOUNT_ID = "<redacted-account-id>"

# Cloudflare rejects a token that is not valid *for the endpoint it was sent to* with the same
# code it uses for a genuinely bad secret, so code 1000 alone cannot tell the two apart.
TOKEN_INVALID_CODE = 1000
# 9109 is the opposite situation: the secret is recognised but the token is expired, revoked,
# deleted, or blocked by client IP filtering.
TOKEN_REVOKED_CODE = 9109
AUTH_FAILURE_STATUS_CODES = frozenset({400, 401, 403})


class CloudflareAuditor:
    """Read-only Cloudflare audit client using a scoped API token."""

    def __init__(
        self,
        api_token: str,
        account_id: str,
        base_url: str = "https://api.cloudflare.com/client/v4",
        *,
        controls: tuple[SecurityControl, ...] | None = None,
    ):
        if not api_token:
            raise ValueError("A scoped Cloudflare API token is required.")
        if not account_id:
            raise ValueError("A Cloudflare account ID is required.")

        self.api_token = api_token
        self.account_id = account_id
        self.base_url = base_url.rstrip("/")
        self.controls = (
            validate_controls(controls) if controls is not None else load_security_standard()
        )
        self.expected_values = expected_values(self.controls)
        self.csv_headers = security_csv_headers(self.controls)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    def __enter__(self) -> CloudflareAuditor:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Release the reusable HTTP connection pool."""
        self._client.close()

    def verify_connection(self) -> dict[str, Any]:
        """Verify the API token against whichever token list actually owns it.

        Cloudflare keeps account-owned and user-owned tokens in separate namespaces with
        separate verify endpoints. ``/accounts/{id}/tokens/verify`` accepts only an Account
        API Token; a perfectly valid User API Token is rejected there with HTTP 401 and
        code 1000. The account endpoint is tried first, and an auth-shaped failure falls
        back to ``/user/tokens/verify``.

        The returned value is the raw Cloudflare token object. A successful verification can
        still report a ``status`` of ``expired`` or ``disabled``, so callers must read
        ``status`` rather than treating a returned result as proof of health.
        """
        account_path = f"{self._account_path}{ACCOUNT_TOKEN_VERIFY_SUFFIX}"

        try:
            return self._verify_token_at(account_path)
        except CloudflareAPIError as exc:
            if not self._is_auth_failure(exc):
                raise
            account_failure = exc

        try:
            return self._verify_token_at(USER_TOKEN_VERIFY_PATH)
        except CloudflareAPIError as user_failure:
            raise self._error(
                "Unable to verify the Cloudflare API token against either token endpoint. "
                f"Account token endpoint ({account_path}) failed: {account_failure} | "
                f"User token endpoint ({USER_TOKEN_VERIFY_PATH}) failed: {user_failure}. "
                + self._token_failure_hint(account_failure, user_failure),
                status_code=user_failure.status_code,
                error_codes=user_failure.error_codes,
            ) from user_failure

    def _verify_token_at(self, path: str) -> dict[str, Any]:
        payload = self._request(path)

        if not payload.get("success", False):
            errors = payload.get("errors") or []
            raise self._error(
                f"Cloudflare rejected token verification at {path}: {errors}",
                error_codes=self._error_codes(errors),
            )

        result = payload.get("result")
        if not isinstance(result, dict):
            raise self._error(
                f"Cloudflare token verification at {path} did not include a result object."
            )

        return result

    @staticmethod
    def _is_auth_failure(exc: CloudflareAPIError) -> bool:
        """True when a failure looks like a token/endpoint problem worth retrying elsewhere."""
        if TOKEN_INVALID_CODE in exc.error_codes or TOKEN_REVOKED_CODE in exc.error_codes:
            return True

        return exc.status_code in AUTH_FAILURE_STATUS_CODES

    @staticmethod
    def _token_failure_hint(*failures: CloudflareAPIError) -> str:
        codes = {code for failure in failures for code in failure.error_codes}

        hints: list[str] = []
        if TOKEN_INVALID_CODE in codes:
            hints.append(
                f"Cloudflare error {TOKEN_INVALID_CODE} means the token is not valid for the "
                "endpoint it was sent to, or the token secret itself is wrong. It does not "
                "indicate a missing or mismatched account ID."
            )
        if TOKEN_REVOKED_CODE in codes:
            hints.append(
                f"Cloudflare error {TOKEN_REVOKED_CODE} means the opposite: the token is "
                "expired, revoked, or deleted, or client IP filtering blocked this caller."
            )
        if not hints:
            hints.append(
                "Confirm CLOUDFLARE_API_TOKEN holds the token secret and that the token still "
                "exists in either the user or the account token list."
            )

        hints.append("See docs/cloudflare-api-token-runbook.md.")
        return " ".join(hints)

    def list_all_zones(self) -> str:
        zones = self._list_zones()
        hcl = self._zones_to_hcl(zones)
        print(hcl)
        return hcl

    def audit_security_posture(
        self,
        report_dir: Path = DEFAULT_REPORT_DIR,
        *,
        show_identities: bool = True,
    ) -> list[dict[str, Any]]:
        """Audit every zone, write the CSV report, and print a summary.

        With ``show_identities=False`` the printed summary contains counts only, so it is safe for
        public CI logs. The CSV report on disk always contains full identities.
        """
        zones = self._list_zones()
        rows: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []

        sorted_zones = sorted(zones, key=lambda item: cast(str, item["name"]))
        for index, zone in enumerate(sorted_zones, start=1):
            print(f"[{index}/{len(sorted_zones)}] checking zone...", flush=True)
            settings = self.get_zone_security_settings(cast(str, zone["id"]))
            deviations = {
                key: value for key, value in settings.items() if value != self.expected_values[key]
            }
            is_compliant = int(not deviations)
            row: dict[str, Any] = {"domain_name": zone["name"], "zone_id": zone["id"]}
            row.update({csv_column(control): settings[control.key] for control in self.controls})
            row["is_compliant"] = is_compliant
            rows.append(row)

            if deviations:
                findings.append(
                    {
                        "domain": zone["name"],
                        "zone_id": zone["id"],
                        "settings": settings,
                        "deviations": deviations,
                    }
                )

        report_path = self._write_security_audit_csv(rows, report_dir, self.csv_headers)
        self._print_security_audit_report(
            len(zones),
            findings,
            report_path,
            self.expected_values,
            show_identities=show_identities,
        )
        return findings

    def get_zone_security_settings(self, zone_id: str) -> dict[str, Any]:
        if not zone_id:
            raise ValueError("zone_id is required.")

        settings: dict[str, Any] = {}
        for control in self.controls:
            if control.resource == ZONE_SETTING_RESOURCE:
                # load_security_standard guarantees zone-setting controls carry a setting_id.
                setting_id = cast(str, control.setting_id)
                settings[control.key] = self._setting_value(
                    self._get_zone_setting(zone_id, setting_id),
                    setting_id,
                )
            elif control.resource == BOT_MANAGEMENT_RESOURCE:
                settings[control.key] = self._get_bot_fight_mode(zone_id)
            else:  # pragma: no cover - validate_controls rejects other resources
                raise ValueError(f"Unsupported security control resource: {control.resource}")
        return settings

    def _get_bot_fight_mode(self, zone_id: str) -> str:
        payload = self._request(f"/zones/{zone_id}/bot_management")

        if not payload.get("success", False):
            errors = payload.get("errors") or []
            raise self._error(f"Cloudflare bot management request failed: {errors}")

        result = payload.get("result")
        if not result:
            return "off"

        if not isinstance(result, dict):
            raise self._error("Cloudflare bot management response did not include a result object.")

        fight_mode = result.get("fight_mode")
        if isinstance(fight_mode, str):
            return "on" if fight_mode.lower() in {"on", "true", "enabled"} else "off"

        return "on" if fight_mode is True else "off"

    def _get_zone_setting(self, zone_id: str, setting_id: str) -> dict[str, Any]:
        payload = self._request(f"/zones/{zone_id}/settings/{setting_id}")

        if not payload.get("success", False):
            errors = payload.get("errors") or []
            raise self._error(f"Cloudflare API request failed: {errors}")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise self._error("Cloudflare API response did not include a result object.")

        return result

    def _setting_value(self, setting: dict[str, Any], setting_id: str) -> Any:
        if setting.get("id") != setting_id:
            raise self._error(
                f"Expected Cloudflare setting '{setting_id}', got '{setting.get('id')}'."
            )

        if "value" not in setting:
            raise self._error(f"Cloudflare setting '{setting_id}' did not include a value.")

        return setting["value"]

    def _request(self, path: str) -> dict[str, Any]:
        try:
            response = self._client.get(path)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            # Deliberately not chained: httpx puts the full request URL in its own message,
            # which would reintroduce the account ID into any traceback or CI log.
            raise self._error(
                f"Cloudflare API returned HTTP {exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
                error_codes=self._error_codes_from_body(exc.response.text),
            ) from None
        except httpx.RequestError as exc:
            raise self._error(f"Cloudflare API request failed: {exc}") from None
        except ValueError as exc:
            raise self._error("Cloudflare API response was not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise self._error("Cloudflare API response was not a JSON object.")

        return cast(dict[str, Any], payload)

    def _assert_zone_read_permission(self) -> dict[str, Any]:
        try:
            return self._request(self._zones_path(1))
        except CloudflareAPIError as exc:
            if TOKEN_REVOKED_CODE in exc.error_codes:
                message = (
                    f"Unable to list zones. Cloudflare error {TOKEN_REVOKED_CODE} means the "
                    "token is expired, revoked, or deleted, or its IP allowlist blocked this "
                    "request. GitHub-hosted runners have no stable egress IP, so an IP-filtered "
                    "token fails here."
                )
            elif TOKEN_INVALID_CODE in exc.error_codes:
                message = (
                    f"Unable to list zones. Cloudflare error {TOKEN_INVALID_CODE} means the "
                    "token is invalid or the verify endpoint does not match the token type."
                )
            else:
                message = "Unable to list zones. Confirm the token includes Zone:Read permissions."

            raise self._error(
                message,
                status_code=exc.status_code,
                error_codes=exc.error_codes,
            ) from exc

    def _list_zones(self) -> list[dict[str, Any]]:
        first_payload = self._assert_zone_read_permission()
        zones = self._zones_from_payload(first_payload)
        result_info = first_payload.get("result_info")
        total_pages = self._total_pages(result_info)

        for page in range(2, total_pages + 1):
            payload = self._request(self._zones_path(page))
            zones.extend(self._zones_from_payload(payload))

        return zones

    def _redact(self, text: str) -> str:
        """Replace the account ID with a placeholder so it cannot leak through error text."""
        for value in (self.account_id, quote(self.account_id, safe="")):
            if value:
                text = text.replace(value, REDACTED_ACCOUNT_ID)

        return text

    def _error(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_codes: tuple[int, ...] = (),
    ) -> CloudflareAPIError:
        return CloudflareAPIError(
            self._redact(message),
            status_code=status_code,
            error_codes=error_codes,
        )

    @staticmethod
    def _error_codes(errors: Any) -> tuple[int, ...]:
        if not isinstance(errors, list):
            return ()

        return tuple(
            error["code"]
            for error in errors
            if isinstance(error, dict) and isinstance(error.get("code"), int)
        )

    @classmethod
    def _error_codes_from_body(cls, body: str) -> tuple[int, ...]:
        try:
            payload = json.loads(body)
        except ValueError:
            return ()

        if not isinstance(payload, dict):
            return ()

        return cls._error_codes(payload.get("errors"))

    @property
    def _account_path(self) -> str:
        return f"/accounts/{quote(self.account_id, safe='')}"

    def _zones_path(self, page: int) -> str:
        account_id = quote(self.account_id, safe="")
        return f"/zones?account.id={account_id}&page={page}&per_page=50"

    def _zones_from_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not payload.get("success", False):
            errors = payload.get("errors") or []
            raise self._error(f"Cloudflare zone list request failed: {errors}")

        result = payload.get("result")
        if not isinstance(result, list):
            raise self._error("Cloudflare zone list response did not include a result list.")

        zones: list[dict[str, Any]] = []
        for zone in result:
            if not isinstance(zone, dict):
                raise self._error("Cloudflare zone list included a malformed zone object.")

            if not isinstance(zone.get("name"), str) or not isinstance(zone.get("id"), str):
                raise self._error("Cloudflare zone list included a zone without name or id.")

            zones.append(cast(dict[str, Any], zone))

        return zones

    @staticmethod
    def _total_pages(result_info: Any) -> int:
        if not isinstance(result_info, dict):
            return 1

        total_pages = result_info.get("total_pages")
        if not isinstance(total_pages, int) or total_pages < 1:
            return 1

        return total_pages

    @staticmethod
    def _zones_to_hcl(zones: list[dict[str, Any]]) -> str:
        lines = ["domains = {"]
        for zone in sorted(zones, key=lambda item: cast(str, item["name"])):
            lines.extend(
                [
                    f'  "{zone["name"]}" = {{',
                    f'    zone_id = "{zone["id"]}"',
                    "  }",
                    "",
                ]
            )

        if len(lines) > 1:
            lines.pop()

        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def _write_security_audit_csv(
        rows: list[dict[str, Any]],
        report_dir: Path,
        headers: tuple[str, ...],
    ) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{timestamp}_security_compliance_report.csv"
        latest_report_path = report_dir / LATEST_SECURITY_REPORT

        with report_path.open("w", encoding="utf-8", newline="") as report_file:
            writer = csv.DictWriter(report_file, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        with latest_report_path.open("w", encoding="utf-8", newline="") as report_file:
            writer = csv.DictWriter(report_file, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        return report_path

    @staticmethod
    def _print_security_audit_report(
        total_zones: int,
        findings: list[dict[str, Any]],
        report_path: Path,
        expected: dict[str, str],
        *,
        show_identities: bool = True,
    ) -> None:
        print("Cloudflare Security Posture Audit")
        print(f"Domains audited: {total_zones}")
        print(f"Domains deviating from standards: {len(findings)}")
        print(f"CSV report: {report_path}")

        if not findings:
            print("All audited domains meet the configured standards.")
            return

        if not show_identities:
            deviation_counts: dict[str, int] = {}
            for finding in findings:
                for key in cast(dict[str, Any], finding["deviations"]):
                    deviation_counts[key] = deviation_counts.get(key, 0) + 1
            print("")
            for key in sorted(deviation_counts):
                print(f"{key}: {deviation_counts[key]} domain(s) expected {expected[key]}")
            print(
                "Domain identities are omitted from this output. Run the audit locally for details."
            )
            return

        print("")
        header = " | ".join(["Domain", *expected, "Deviations"])
        print(header)
        print("-" * len(header))

        for finding in findings:
            settings = cast(dict[str, Any], finding["settings"])
            deviations = cast(dict[str, Any], finding["deviations"])
            deviation_summary = ", ".join(
                f"{key}={value} expected {expected[key]}" for key, value in deviations.items()
            )
            values = [str(settings.get(key, "")) for key in expected]
            print(" | ".join([str(finding["domain"]), *values, deviation_summary]))


class CloudflareAPIError(RuntimeError):
    """Raised when Cloudflare returns an unsuccessful or malformed response.

    Messages raised by :class:`CloudflareAuditor` are redacted: the account ID is replaced
    with ``REDACTED_ACCOUNT_ID`` so it never reaches a traceback, log, or CI transcript.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_codes: tuple[int, ...] = (),
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_codes = tuple(error_codes)
