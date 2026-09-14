from pathlib import Path
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
    mock_cloudflare_token_verify.assert_called_once_with("/accounts/test-account-id/tokens/verify")


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

    with pytest.raises(CloudflareAPIError) as excinfo:
        auditor.verify_connection()

    message = str(excinfo.value)
    # The old message blamed CLOUDFLARE_ACCOUNT_ID, which sent readers down the wrong path.
    assert "CLOUDFLARE_ACCOUNT_ID" not in message
    assert "test-account-id" not in message
    assert "error 1000" in message


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
        CloudflareAuditor("scoped-test-token", "test-account-id")._setting_value(
            {"id": "tls_1_3", "value": "on"}, "ssl"
        )


def test_setting_value_rejects_missing_value():
    with pytest.raises(CloudflareAPIError, match="did not include a value"):
        CloudflareAuditor("scoped-test-token", "test-account-id")._setting_value(
            {"id": "ssl"}, "ssl"
        )


def test_request_returns_json_object(respx_mock):
    route = respx_mock.get("https://api.example.test/accounts/test-account-id/tokens/verify").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"status": "active"}})
    )
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )

    payload = auditor._request("/accounts/test-account-id/tokens/verify")

    assert payload == {"success": True, "result": {"status": "active"}}
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer scoped-test-token"
    assert request.headers["Content-Type"] == "application/json"
    assert auditor._client.timeout == httpx.Timeout(30)


def test_default_base_url_keeps_client_v4_prefix(respx_mock):
    zones = respx_mock.get("https://api.cloudflare.com/client/v4/zones").mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    verify = respx_mock.get("https://api.cloudflare.com/client/v4/user/tokens/verify").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"status": "active"}})
    )
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")

    auditor._request(auditor._zones_path(1))
    auditor._request("/user/tokens/verify")

    assert zones.call_count == 1
    assert verify.call_count == 1
    assert str(zones.calls.last.request.url).startswith(
        "https://api.cloudflare.com/client/v4/zones?"
    )


@pytest.mark.parametrize("status_code", [403, 404])
def test_request_reports_http_error(mocker, status_code):
    response = httpx.Response(
        status_code,
        json={"success": False, "errors": [{"message": "Request failed"}]},
        request=httpx.Request("GET", "https://api.example.test/failure"),
    )
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )
    mocker.patch.object(auditor._client, "get", return_value=response)

    with pytest.raises(CloudflareAPIError, match=f"HTTP {status_code}"):
        auditor._request("/failure")


def test_request_reports_network_error(mocker):
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )
    mocker.patch.object(
        auditor._client,
        "get",
        side_effect=httpx.RequestError("connection failed"),
    )

    with pytest.raises(CloudflareAPIError, match="connection failed"):
        auditor._request("/failure")


def test_request_reports_malformed_json(mocker):
    response = httpx.Response(
        200,
        content=b"{not-json",
        request=httpx.Request("GET", "https://api.example.test/bad-json"),
    )
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )
    mocker.patch.object(auditor._client, "get", return_value=response)

    with pytest.raises(CloudflareAPIError, match="not valid JSON"):
        auditor._request("/bad-json")


def test_request_rejects_non_object_json(mocker):
    response = httpx.Response(
        200,
        json=["not", "an", "object"],
        request=httpx.Request("GET", "https://api.example.test/list-json"),
    )
    auditor = CloudflareAuditor(
        api_token="scoped-test-token",
        account_id="test-account-id",
        base_url="https://api.example.test",
    )
    mocker.patch.object(auditor._client, "get", return_value=response)

    with pytest.raises(CloudflareAPIError, match="not a JSON object"):
        auditor._request("/list-json")


def test_list_all_zones_prints_terraform_hcl(mocker, capsys):
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")
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


@pytest.mark.parametrize(
    ("error_code", "expected_message", "unexpected_message"),
    [
        (
            9109,
            "expired, revoked, or deleted",
            "Confirm the token includes Zone:Read permissions",
        ),
        (
            1000,
            "token is invalid or the verify endpoint does not match the token type",
            "Confirm the token includes Zone:Read permissions",
        ),
        (None, "Confirm the token includes Zone:Read permissions", "expired, revoked, or deleted"),
    ],
)
def test_list_all_zones_explains_zone_access_failure(
    mocker, error_code, expected_message, unexpected_message
):
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")
    errors = [] if error_code is None else [{"code": error_code, "message": "request rejected"}]
    response = httpx.Response(
        403,
        json={"success": False, "errors": errors},
        request=httpx.Request("GET", "https://api.example.test/zones"),
    )
    mocker.patch.object(auditor._client, "get", return_value=response)

    with pytest.raises(CloudflareAPIError) as excinfo:
        auditor.list_all_zones()

    assert expected_message in str(excinfo.value)
    assert unexpected_message not in str(excinfo.value)
    assert excinfo.value.status_code == 403
    assert excinfo.value.error_codes == (() if error_code is None else (error_code,))


def test_list_all_zones_explains_ip_filtering_on_github_runners(mocker):
    auditor = CloudflareAuditor(api_token="scoped-test-token", account_id="test-account-id")
    response = httpx.Response(
        403,
        json={"success": False, "errors": [{"code": 9109, "message": "request rejected"}]},
        request=httpx.Request("GET", "https://api.example.test/zones"),
    )
    mocker.patch.object(auditor._client, "get", return_value=response)

    with pytest.raises(CloudflareAPIError) as excinfo:
        auditor.list_all_zones()

    assert "IP allowlist" in str(excinfo.value)
    assert "GitHub-hosted runners have no stable egress IP" in str(excinfo.value)


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
    progress_lines = [line for line in output.splitlines() if line.startswith("[")]
    assert progress_lines == ["[1/2] checking zone...", "[2/2] checking zone..."]
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
                "is_compliant": 1,
            },
            {
                "domain_name": "weak.example",
                "zone_id": "weak-zone",
                "ssl_mode": "flexible",
                "always_use_https": "off",
                "security_level": "low",
                "bot_fight_mode": "off",
                "is_compliant": 0,
            },
        ],
        ANY,
    )


def test_fixture_audit_reuses_one_client_and_keeps_six_requests(mocker):
    client_type = mocker.patch("scripts.cloudflare_client.httpx.Client")
    client = client_type.return_value

    def response(payload):
        value = mocker.Mock()
        value.raise_for_status.return_value = None
        value.json.return_value = payload
        return value

    client.get.side_effect = [
        response({"success": True, "result": {"status": "active"}}),
        response(
            {
                "success": True,
                "result": [{"name": "fixture.example", "id": "fixture-zone"}],
            }
        ),
        response({"success": True, "result": {"id": "ssl", "value": "full"}}),
        response({"success": True, "result": {"id": "security_level", "value": "medium"}}),
        response({"success": True, "result": {"id": "always_use_https", "value": "on"}}),
        response({"success": True, "result": {"fight_mode": True}}),
    ]
    auditor = CloudflareAuditor("fixture-token", "fixture-account")
    mocker.patch.object(auditor, "_write_security_audit_csv", return_value="fixture.csv")

    auditor.verify_connection()
    auditor.audit_security_posture()

    client_type.assert_called_once()
    assert client.get.call_count == 6


@pytest.mark.parametrize(
    "operation",
    [
        lambda auditor: auditor._get_zone_setting("fixture-zone", "ssl"),
        lambda auditor: auditor._get_bot_fight_mode("fixture-zone"),
        lambda auditor: auditor._zones_from_payload(
            {"success": False, "errors": ["fixture-account"]}
        ),
        lambda auditor: auditor._setting_value({"id": "fixture-account", "value": "on"}, "ssl"),
    ],
)
def test_payload_validation_paths_redact_account_id(mocker, operation):
    auditor = CloudflareAuditor("fixture-token", "fixture-account")
    mocker.patch.object(
        auditor,
        "_request",
        return_value={"success": False, "errors": ["fixture-account"]},
    )

    with pytest.raises(CloudflareAPIError) as excinfo:
        operation(auditor)

    assert "fixture-account" not in str(excinfo.value)


def test_context_manager_closes_reusable_client(mocker):
    client_type = mocker.patch("scripts.cloudflare_client.httpx.Client")

    with CloudflareAuditor("fixture-token", "fixture-account"):
        pass

    client_type.return_value.close.assert_called_once_with()


def test_zones_from_payload_rejects_failed_response():
    auditor = CloudflareAuditor("placeholder-token", "placeholder-account")
    with pytest.raises(CloudflareAPIError, match="zone list request failed"):
        auditor._zones_from_payload({"success": False, "errors": ["forbidden"]})


def test_zones_from_payload_rejects_malformed_zone():
    auditor = CloudflareAuditor("placeholder-token", "placeholder-account")
    with pytest.raises(CloudflareAPIError, match="without name or id"):
        auditor._zones_from_payload({"success": True, "result": [{"name": "example"}]})


def test_redacted_audit_report_prints_counts_without_identities(capsys):
    findings = [
        {
            "domain": "weak.example",
            "zone_id": "zone-weak",
            "settings": {},
            "deviations": {"ssl": "flexible", "bot_fight_mode": "off"},
        },
        {
            "domain": "other.example",
            "zone_id": "zone-other",
            "settings": {},
            "deviations": {"ssl": "off"},
        },
    ]

    CloudflareAuditor._print_security_audit_report(
        3, findings, Path("report.csv"), show_identities=False
    )

    output = capsys.readouterr().out
    assert "Domains deviating from standards: 2" in output
    assert "ssl: 2 domain(s) expected full" in output
    assert "bot_fight_mode: 1 domain(s) expected on" in output
    for identity in ("weak.example", "other.example", "zone-weak", "zone-other"):
        assert identity not in output
