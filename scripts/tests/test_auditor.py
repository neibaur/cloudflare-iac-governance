from unittest.mock import ANY, call

import httpx
import pytest

from scripts.cloudflare_client import CloudflareAPIError, CloudflareAuditor


def test_auditor_requires_account_id():
    with pytest.raises(ValueError, match="account ID"):
        CloudflareAuditor(api_token="scoped-test-token", account_id="")


def test_verify_connection_returns_token_status(mock_cloudflare_token_verify):
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")

    verification = auditor.verify_connection()

    assert verification == {
        "id": "token-id",
        "status": "active",
    }
    mock_cloudflare_token_verify.assert_called_once_with(
        "/accounts/test-account-id/tokens/verify"
    )


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
    auditor = CloudflareAuditor(api_token="bad-token", account_id="test-account-id")

    with pytest.raises(CloudflareAPIError, match="CLOUDFLARE_ACCOUNT_ID"):
        auditor.verify_connection()


def test_get_zone_security_settings_parses_successful_response(
    mock_cloudflare,
    cloudflare_fixture_data,
):
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")

    settings = auditor.get_zone_security_settings(cloudflare_fixture_data.zone_id)

    assert settings == {
        "ssl": "full",
        "security_level": "medium",
        "always_use_https": "on",
        "bot_fight_mode": "on",
    }
    assert mock_cloudflare.call_count == 4
    mock_cloudflare.assert_any_call(f"/zones/{cloudflare_fixture_data.zone_id}/settings/ssl")
    mock_cloudflare.assert_any_call(
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/security_level"
    )
    mock_cloudflare.assert_any_call(
        f"/zones/{cloudflare_fixture_data.zone_id}/settings/always_use_https"
    )
    mock_cloudflare.assert_any_call(f"/zones/{cloudflare_fixture_data.zone_id}/bot_management")


def test_get_zone_security_settings_requires_zone_id():
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")

    with pytest.raises(ValueError, match="zone_id is required"):
        auditor.get_zone_security_settings("")


def test_get_zone_security_settings_reads_bot_management(mocker, cloudflare_fixture_data):
    def request(path):
        if path.endswith("/bot_management"):
            return {
                "success": True,
                "result": {"fight_mode": True, "enable_js": True},
            }

        setting_id = path.rsplit("/", maxsplit=1)[-1]
        return {
            "success": True,
            "result": {
                "id": setting_id,
                "value": {
                    "ssl": "full",
                    "security_level": "medium",
                    "always_use_https": "on",
                }[setting_id],
            },
        }

    mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        side_effect=request,
    )
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")

    settings = auditor.get_zone_security_settings(cloudflare_fixture_data.zone_id)

    assert settings["bot_fight_mode"] == "on"


@pytest.mark.parametrize("result", [None, {}])
def test_get_bot_fight_mode_treats_empty_response_as_off(mocker, result):
    mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        return_value={"success": True, "result": result},
    )
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")

    assert auditor._get_bot_fight_mode("zone-id") == "off"


def test_get_zone_setting_reports_cloudflare_error(mocker, cloudflare_fixture_data):
    mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        return_value={
            "success": False,
            "errors": [{"code": 1001, "message": "Zone not found"}],
        },
    )
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")

    with pytest.raises(CloudflareAPIError, match="Zone not found"):
        auditor._get_zone_setting(cloudflare_fixture_data.zone_id, "ssl")


def test_get_zone_setting_rejects_missing_result(mocker, cloudflare_fixture_data):
    mocker.patch(
        "scripts.cloudflare_client.CloudflareAuditor._request",
        return_value={"success": True, "result": None},
    )
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")

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
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )

    payload = auditor._request("/accounts/test-account-id/tokens/verify")

    assert payload == {"success": True, "result": {"status": "active"}}
    http_get.assert_called_once_with(
        "https://api.example.test/accounts/test-account-id/tokens/verify",
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
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )

    with pytest.raises(CloudflareAPIError, match=f"HTTP {status_code}"):
        auditor._request("/failure")


def test_request_reports_network_error(mocker):
    mocker.patch(
        "scripts.cloudflare_client.httpx.get",
        side_effect=httpx.RequestError("connection failed"),
    )
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )

    with pytest.raises(CloudflareAPIError, match="connection failed"):
        auditor._request("/failure")


def test_request_reports_malformed_json(mocker):
    response = httpx.Response(
        200,
        content=b"{not-json",
        request=httpx.Request("GET", "https://api.example.test/bad-json"),
    )
    mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )

    with pytest.raises(CloudflareAPIError, match="not valid JSON"):
        auditor._request("/bad-json")


def test_request_rejects_non_object_json(mocker):
    response = httpx.Response(
        200,
        json=["not", "an", "object"],
        request=httpx.Request("GET", "https://api.example.test/list-json"),
    )
    mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )

    with pytest.raises(CloudflareAPIError, match="not a JSON object"):
        auditor._request("/list-json")


def test_list_all_zones_prints_terraform_hcl(mocker, capsys):
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")
    mocker.patch.object(
        auditor,
        "verify_connection",
        return_value={
            "status": "active",
            "policies": [{"permission_groups": [{"name": "Zone Read"}]}],
        },
    )
    request = mocker.patch.object(
        auditor,
        "_request",
        side_effect=[
            {
                "success": True,
                "result": [{"name": "beta.example", "id": "zone-beta"}],
                "result_info": {"total_pages": 2},
            },
            {
                "success": True,
                "result": [{"name": "alpha.example", "id": "zone-alpha"}],
                "result_info": {"total_pages": 2},
            },
        ],
    )

    hcl = auditor.list_all_zones()

    assert hcl == "\n".join(
        [
            "domains = {",
            '  "alpha.example" = {',
            '    zone_id = "zone-alpha"',
            "  }",
            "",
            '  "beta.example" = {',
            '    zone_id = "zone-beta"',
            "  }",
            "}",
        ]
    )
    assert request.call_args_list == [
        call("/zones?account.id=test-account-id&page=1&per_page=50"),
        call("/zones?account.id=test-account-id&page=2&per_page=50"),
    ]
    assert capsys.readouterr().out == f"{hcl}\n"


def test_list_all_zones_reports_missing_zone_read(mocker):
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")
    mocker.patch.object(auditor, "verify_connection", return_value={"status": "active"})
    mocker.patch.object(
        auditor,
        "_request",
        side_effect=CloudflareAPIError("Cloudflare API returned HTTP 403: forbidden"),
    )

    with pytest.raises(CloudflareAPIError, match="Zone:Read"):
        auditor.list_all_zones()


def test_audit_security_posture_reports_deviations(mocker, capsys):
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")
    mocker.patch.object(
        auditor,
        "_list_zones",
        return_value=[
            {"name": "secure.example", "id": "secure-zone"},
            {"name": "weak.example", "id": "weak-zone"},
        ],
    )
    mocker.patch.object(
        auditor,
        "get_zone_security_settings",
        side_effect=[
            {
                "ssl": "full",
                "security_level": "medium",
                "always_use_https": "on",
                "bot_fight_mode": "on",
            },
            {
                "ssl": "flexible",
                "security_level": "low",
                "always_use_https": "off",
                "bot_fight_mode": "off",
            },
        ],
    )
    csv_writer = mocker.patch.object(
        auditor,
        "_write_security_audit_csv",
        return_value="20260430T120000Z_security_compliance_report.csv",
    )

    findings = auditor.audit_security_posture()

    assert findings == [
        {
            "domain": "weak.example",
            "zone_id": "weak-zone",
            "settings": {
                "ssl": "flexible",
                "security_level": "low",
                "always_use_https": "off",
                "bot_fight_mode": "off",
            },
            "deviations": {
                "ssl": "flexible",
                "security_level": "low",
                "always_use_https": "off",
                "bot_fight_mode": "off",
            },
        }
    ]
    output = capsys.readouterr().out
    assert "Domains audited: 2" in output
    assert "Domains deviating from standards: 1" in output
    assert "CSV report: 20260430T120000Z_security_compliance_report.csv" in output
    assert "weak.example" in output
    csv_writer.assert_called_once_with(
        [
            {
                "domain_name": "secure.example",
                "zone_id": "secure-zone",
                "ssl_mode": "full",
                "always_use_https": "on",
                "security_level": "medium",
                "bot_fight_mode": "on",
                "is_compliant": True,
            },
            {
                "domain_name": "weak.example",
                "zone_id": "weak-zone",
                "ssl_mode": "flexible",
                "always_use_https": "off",
                "security_level": "low",
                "bot_fight_mode": "off",
                "is_compliant": False,
            },
        ],
        ANY,
    )


def test_zones_from_payload_rejects_failed_response():
    with pytest.raises(CloudflareAPIError, match="zone list request failed"):
        CloudflareAuditor._zones_from_payload({"success": False, "errors": ["forbidden"]})


def test_zones_from_payload_rejects_malformed_zone():
    with pytest.raises(CloudflareAPIError, match="without name or id"):
        CloudflareAuditor._zones_from_payload({"success": True, "result": [{"name": "example"}]})
