import httpx
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
    mock_cloudflare.assert_any_call(f"/zones/{cloudflare_fixture_data.zone_id}/settings/ssl")
    mock_cloudflare.assert_any_call(
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/bot_fight_mode"
    )


def test_get_zone_security_settings_requires_zone_id():
    auditor = CloudflareAuditor(api_token="scoped-test-token")

    with pytest.raises(ValueError, match="zone_id is required"):
        auditor.get_zone_security_settings("")


def test_get_zone_setting_reports_cloudflare_error(mocker, cloudflare_fixture_data):
    mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        return_value={
            "success": False,
            "errors": [{"code": 1001, "message": "Zone not found"}],
        },
    )
    auditor = CloudflareAuditor(api_token="scoped-test-token")

    with pytest.raises(CloudflareAPIError, match="Zone not found"):
        auditor._get_zone_setting(cloudflare_fixture_data.zone_id, "ssl")


def test_get_zone_setting_rejects_missing_result(mocker, cloudflare_fixture_data):
    mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        return_value={"success": True, "result": None},
    )
    auditor = CloudflareAuditor(api_token="scoped-test-token")

    with pytest.raises(CloudflareAPIError, match="result object"):
        auditor._get_zone_setting(cloudflare_fixture_data.zone_id, "ssl")


def test_setting_value_rejects_unexpected_setting_id():
    with pytest.raises(CloudflareAPIError, match="Expected Cloudflare setting"):
        CloudflareAuditor._setting_value({"id": "tls_1_3", "value": "on"}, "ssl")


def test_setting_value_rejects_missing_value():
    with pytest.raises(CloudflareAPIError, match="did not include a value"):
        CloudflareAuditor._setting_value({"id": "ssl"}, "ssl")


def test_request_returns_json_object(mocker):
    response = httpx.Response(
        200,
        json={"success": True, "result": {"status": "active"}},
        request=httpx.Request("GET", "https://api.example.test/user/tokens/verify"),
    )
    http_get = mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)
    auditor = CloudflareAuditor(api_token="scoped-test-token", base_url="https://api.example.test")

    payload = auditor._request("/user/tokens/verify")

    assert payload == {"success": True, "result": {"status": "active"}}
    http_get.assert_called_once_with(
        "https://api.example.test/user/tokens/verify",
        headers={
            "Authorization": "Bearer scoped-test-token",
            "Content-Type": "application/json",
        },
        timeout=30,
    )


@pytest.mark.parametrize("status_code", [403, 404])
def test_request_reports_http_error(mocker, status_code):
    response = httpx.Response(
        status_code,
        json={"success": False, "errors": [{"message": "Request failed"}]},
        request=httpx.Request("GET", "https://api.example.test/failure"),
    )
    mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)
    auditor = CloudflareAuditor(api_token="scoped-test-token", base_url="https://api.example.test")

    with pytest.raises(CloudflareAPIError, match=f"HTTP {status_code}"):
        auditor._request("/failure")


def test_request_reports_network_error(mocker):
    mocker.patch(
        "scripts.cloudflare_client.httpx.get",
        side_effect=httpx.RequestError("connection failed"),
    )
    auditor = CloudflareAuditor(api_token="scoped-test-token", base_url="https://api.example.test")

    with pytest.raises(CloudflareAPIError, match="connection failed"):
        auditor._request("/failure")


def test_request_reports_malformed_json(mocker):
    response = httpx.Response(
        200,
        content=b"{not-json",
        request=httpx.Request("GET", "https://api.example.test/bad-json"),
    )
    mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)
    auditor = CloudflareAuditor(api_token="scoped-test-token", base_url="https://api.example.test")

    with pytest.raises(CloudflareAPIError, match="not valid JSON"):
        auditor._request("/bad-json")


def test_request_rejects_non_object_json(mocker):
    response = httpx.Response(
        200,
        json=["not", "an", "object"],
        request=httpx.Request("GET", "https://api.example.test/list-json"),
    )
    mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)
    auditor = CloudflareAuditor(api_token="scoped-test-token", base_url="https://api.example.test")

    with pytest.raises(CloudflareAPIError, match="not a JSON object"):
        auditor._request("/list-json")
