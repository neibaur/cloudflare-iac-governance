from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class CloudflareAuditor:
    """Read-only Cloudflare audit client using a scoped API token."""

    def __init__(self, api_token: str, base_url: str = "https://api.cloudflare.com/client/v4"):
        if not api_token:
            raise ValueError("A scoped Cloudflare API token is required.")

        self.api_token = api_token
        self.base_url = base_url.rstrip("/")

    def verify_connection(self) -> dict[str, Any]:
        payload = self._request("/user/tokens/verify")

        if not payload.get("success", False):
            errors = payload.get("errors") or []
            raise CloudflareAPIError(f"Cloudflare token verification failed: {errors}")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise CloudflareAPIError(
                "Cloudflare token verification did not include a result object."
            )

        return result

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
            raise CloudflareAPIError(
                f"Cloudflare setting '{setting_id}' did not include a value."
            )

        return setting["value"]

    def _request(self, path: str) -> dict[str, Any]:
        http_request = request.Request(
            f"{self.base_url}{path}",
            method="GET",
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with request.urlopen(http_request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise CloudflareAPIError(f"Cloudflare API returned HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise CloudflareAPIError(f"Cloudflare API request failed: {exc.reason}") from exc


class CloudflareAPIError(RuntimeError):
    """Raised when Cloudflare returns an unsuccessful or malformed response."""
