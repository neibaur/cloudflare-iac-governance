from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class CloudflareFixtureData:
    zone_id: str = "023e105f4ecef8ad9ca31a8372d0c353"
    zone_name: str = "example.com"

    @property
    def zone(self) -> dict[str, object]:
        return {
            "id": self.zone_id,
            "name": self.zone_name,
            "status": "active",
            "paused": False,
        }

    @property
    def zone_settings(self) -> list[dict[str, object]]:
        return [
            {"id": "always_use_https", "value": "on", "modified_on": None},
            {"id": "automatic_https_rewrites", "value": "on", "modified_on": None},
            {"id": "ssl", "value": "full", "modified_on": None},
            {"id": "tls_1_3", "value": "on", "modified_on": None},
        ]


@pytest.fixture
def cloudflare_fixture_data() -> CloudflareFixtureData:
    return CloudflareFixtureData()


@pytest.fixture(autouse=True)
def ignore_test_runner_proxies(monkeypatch):
    """Keep construction of mocked HTTP clients independent of host proxy settings."""
    for variable in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def mock_cloudflare(mocker, cloudflare_fixture_data):
    """Patch CloudflareAuditor API calls with successful zone setting responses."""
    responses = {
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/ssl": {
            "success": True,
            "errors": [],
            "messages": [],
            "result": {"id": "ssl", "value": "full"},
        },
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/security_level": {
            "success": True,
            "errors": [],
            "messages": [],
            "result": {"id": "security_level", "value": "medium"},
        },
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/always_use_https": {
            "success": True,
            "errors": [],
            "messages": [],
            "result": {"id": "always_use_https", "value": "on"},
        },
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/min_tls_version": {
            "success": True,
            "errors": [],
            "messages": [],
            "result": {"id": "min_tls_version", "value": "1.2"},
        },
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/browser_check": {
            "success": True,
            "errors": [],
            "messages": [],
            "result": {"id": "browser_check", "value": "on"},
        },
        f"/zones/{cloudflare_fixture_data.zone_id}/bot_management": {
            "success": True,
            "errors": [],
            "messages": [],
            "result": {"fight_mode": True, "enable_js": True},
        },
    }

    return mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        side_effect=lambda path: responses[path],
    )


@pytest.fixture
def mock_cloudflare_token_verify(mocker):
    """Patch CloudflareAuditor token verification with a successful response."""
    return mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        return_value={
            "success": True,
            "errors": [],
            "messages": [],
            "result": {
                "id": "token-id",
                "status": "active",
            },
        },
    )
