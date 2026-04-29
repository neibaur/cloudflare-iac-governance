import pytest

from scripts.cloudflare_client import CloudflareAPIError, CloudflareAuditor


def test_verify_connection_returns_token_status(mock_cloudflare_token_verify):
    auditor = CloudflareAuditor(api_token="scoped-test-token")

    verification = auditor.verify_connection()

    assert verification == {
        "id": "token-id",
        "status": "active",
    }
    mock_cloudflare_token_verify.assert_called_once_with("/user/tokens/verify")


def test_verify_connection_reports_invalid_token_helpfully(mocker):
    mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        return_value={
            "success": False,
            "errors": [{"code": 1000, "message": "Invalid API Token"}],
            "messages": [],
            "result": None,
        },
    )
    auditor = CloudflareAuditor(api_token="bad-token")

    with pytest.raises(CloudflareAPIError, match="CLOUDFLARE_API_TOKEN"):
        auditor.verify_connection()


def test_get_zone_security_settings_parses_successful_response(
    mock_cloudflare,
    cloudflare_fixture_data,
):
    auditor = CloudflareAuditor(api_token="scoped-test-token")

    settings = auditor.get_zone_security_settings(cloudflare_fixture_data.zone_id)

    assert settings == {
        "ssl": "full",
        "bot_fight_mode": "on",
    }
    assert mock_cloudflare.call_count == 2
    mock_cloudflare.assert_any_call(
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/ssl"
    )
    mock_cloudflare.assert_any_call(
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/bot_fight_mode"
    )
