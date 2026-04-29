from __future__ import annotations

from dataclasses import dataclass
import sys
import types

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

    @property
    def dns_records(self) -> list[dict[str, object]]:
        return [
            {
                "id": "record-1",
                "zone_id": self.zone_id,
                "name": self.zone_name,
                "type": "A",
                "content": "192.0.2.1",
                "proxied": True,
            }
        ]


@pytest.fixture
def cloudflare_fixture_data() -> CloudflareFixtureData:
    return CloudflareFixtureData()


@pytest.fixture
def mock_cloudflare_api(mocker, cloudflare_fixture_data):
    """Mock a Cloudflare client object without reaching the real API."""
    client = mocker.Mock(name="cloudflare_client")

    client.zones.list.return_value = [cloudflare_fixture_data.zone]
    client.zones.get.return_value = cloudflare_fixture_data.zone
    client.zones.settings.get.return_value = cloudflare_fixture_data.zone_settings
    client.zones.settings.edit.return_value = {"success": True}
    client.dns.records.list.return_value = cloudflare_fixture_data.dns_records

    return client


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
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/bot_fight_mode": {
            "success": True,
            "errors": [],
            "messages": [],
            "result": {"id": "bot_fight_mode", "value": "on"},
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


@pytest.fixture
def mock_cloudflare_http(mocker, cloudflare_fixture_data):
    """Mock requests-based Cloudflare API calls used by audit scripts."""
    if "requests" not in sys.modules:
        fake_requests = types.ModuleType("requests")
        fake_requests.request = mocker.Mock(name="requests.request")

        class Session:
            def request(self, *args, **kwargs):
                raise NotImplementedError

        fake_requests.Session = Session
        sys.modules["requests"] = fake_requests

    response = mocker.Mock(name="cloudflare_response")
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {
            "zones": [cloudflare_fixture_data.zone],
            "settings": cloudflare_fixture_data.zone_settings,
            "dns_records": cloudflare_fixture_data.dns_records,
        },
    }

    mocker.patch("requests.request", return_value=response)
    mocker.patch("requests.Session.request", return_value=response, create=True)

    return response
