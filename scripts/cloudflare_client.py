from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

import httpx


class CloudflareAuditor:
    """Read-only Cloudflare audit client using a scoped API token."""

    def __init__(
        self,
        api_token: str,
        account_id: str,
        base_url: str = "https://api.cloudflare.com/client/v4",
    ):
        if not api_token:
            raise ValueError("A scoped Cloudflare API token is required.")
        if not account_id:
            raise ValueError("A Cloudflare account ID is required.")

        self.api_token = api_token
        self.account_id = account_id
        self.base_url = base_url.rstrip("/")

    def verify_connection(self) -> dict[str, Any]:
        try:
            payload = self._request(f"{self._account_path}/tokens/verify")
        except CloudflareAPIError as exc:
            raise CloudflareAPIError(
                "Unable to verify the Cloudflare API token. Confirm "
                "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are set locally and "
                "the token is valid for the account."
            ) from exc

        if not payload.get("success", False):
            errors = payload.get("errors") or []
            raise CloudflareAPIError(
                "Unable to verify the Cloudflare API token. Confirm "
                "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are set locally and "
                "the token is valid for the account. "
                f"Cloudflare returned: {errors}"
            )

        result = payload.get("result")
        if not isinstance(result, dict):
            raise CloudflareAPIError(
                "Cloudflare token verification did not include a result object."
            )

        return result

    def list_all_zones(self) -> str:
        first_payload = self._assert_zone_read_permission()
        zones = self._zones_from_payload(first_payload)
        result_info = first_payload.get("result_info")
        total_pages = self._total_pages(result_info)

        for page in range(2, total_pages + 1):
            payload = self._request(self._zones_path(page))
            zones.extend(self._zones_from_payload(payload))

        hcl = self._zones_to_hcl(zones)
        print(hcl)
        return hcl

    def get_zone_security_settings(self, zone_id: str) -> dict[str, Any]:
        if not zone_id:
            raise ValueError("zone_id is required.")

        ssl_setting = self._get_zone_setting(zone_id, "ssl")
        bot_fight_mode_setting = self._get_zone_setting(zone_id, "bot_fight_mode")

        return {
            "ssl": self._setting_value(ssl_setting, "ssl"),
            "bot_fight_mode": self._setting_value(
                bot_fight_mode_setting,
                "bot_fight_mode",
            ),
        }

    def _get_zone_setting(self, zone_id: str, setting_id: str) -> dict[str, Any]:
        payload = self._request(f"/zones/{zone_id}/settings/{setting_id}")

        if not payload.get("success", False):
            errors = payload.get("errors") or []
            raise CloudflareAPIError(f"Cloudflare API request failed: {errors}")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise CloudflareAPIError("Cloudflare API response did not include a result object.")

        return result

    @staticmethod
    def _setting_value(setting: dict[str, Any], setting_id: str) -> Any:
        if setting.get("id") != setting_id:
            raise CloudflareAPIError(
                f"Expected Cloudflare setting '{setting_id}', got '{setting.get('id')}'."
            )

        if "value" not in setting:
            raise CloudflareAPIError(f"Cloudflare setting '{setting_id}' did not include a value.")

        return setting["value"]

    def _request(self, path: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise CloudflareAPIError(
                f"Cloudflare API returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise CloudflareAPIError(f"Cloudflare API request failed: {exc}") from exc
        except ValueError as exc:
            raise CloudflareAPIError("Cloudflare API response was not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise CloudflareAPIError("Cloudflare API response was not a JSON object.")

        return cast(dict[str, Any], payload)

    def _assert_zone_read_permission(self) -> dict[str, Any]:
        verification = self.verify_connection()
        if self._verification_includes_zone_read(verification):
            return self._request(self._zones_path(1))

        try:
            return self._request(self._zones_path(1))
        except CloudflareAPIError as exc:
            raise CloudflareAPIError(
                "Unable to list zones. Confirm the token includes Zone:Read permissions."
            ) from exc

    @property
    def _account_path(self) -> str:
        return f"/accounts/{quote(self.account_id, safe='')}"

    def _zones_path(self, page: int) -> str:
        account_id = quote(self.account_id, safe="")
        return f"/zones?account.id={account_id}&page={page}&per_page=50"

    @classmethod
    def _verification_includes_zone_read(cls, value: Any) -> bool:
        if isinstance(value, dict):
            return any(cls._verification_includes_zone_read(item) for item in value.values())

        if isinstance(value, list):
            return any(cls._verification_includes_zone_read(item) for item in value)

        if isinstance(value, str):
            normalized = value.lower().replace(" ", "").replace("_", "").replace("-", "")
            return "zoneread" in normalized or "zone.read" in value.lower()

        return False

    @staticmethod
    def _zones_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not payload.get("success", False):
            errors = payload.get("errors") or []
            raise CloudflareAPIError(f"Cloudflare zone list request failed: {errors}")

        result = payload.get("result")
        if not isinstance(result, list):
            raise CloudflareAPIError("Cloudflare zone list response did not include a result list.")

        zones: list[dict[str, Any]] = []
        for zone in result:
            if not isinstance(zone, dict):
                raise CloudflareAPIError("Cloudflare zone list included a malformed zone object.")

            if not isinstance(zone.get("name"), str) or not isinstance(zone.get("id"), str):
                raise CloudflareAPIError("Cloudflare zone list included a zone without name or id.")

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


class CloudflareAPIError(RuntimeError):
    """Raised when Cloudflare returns an unsuccessful or malformed response."""
