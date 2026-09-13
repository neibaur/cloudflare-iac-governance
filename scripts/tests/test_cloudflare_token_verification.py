"""Token verification tests for CloudflareAuditor.

Every test mocks the HTTP layer. Nothing here may reach the live Cloudflare API, and no
real account ID, zone ID, domain, or token secret may appear in this file.
"""

from __future__ import annotations

import traceback

import httpx
import pytest

from scripts.cloudflare_client import (
    REDACTED_ACCOUNT_ID,
    USER_TOKEN_VERIFY_PATH,
    CloudflareAPIError,
    CloudflareAuditor,
)

PLACEHOLDER_ACCOUNT_ID = "placeholder-account-id"
PLACEHOLDER_TOKEN = "placeholder-token-secret"
ACCOUNT_VERIFY_PATH = f"/accounts/{PLACEHOLDER_ACCOUNT_ID}/tokens/verify"
BASE_URL = "https://api.example.test"


def make_auditor() -> CloudflareAuditor:
    return CloudflareAuditor(
        api_token=PLACEHOLDER_TOKEN,
        account_id=PLACEHOLDER_ACCOUNT_ID,
        base_url=BASE_URL,
    )


def verify_payload(status: str = "active", **extra: object) -> dict[str, object]:
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {"id": "token-id", "status": status, **extra},
    }


def failure_payload(code: int, message: str) -> dict[str, object]:
    return {
        "success": False,
        "errors": [{"code": code, "message": message}],
        "messages": [],
        "result": None,
    }


def http_error(status_code: int, code: int, message: str, path: str) -> CloudflareAPIError:
    """Build the error CloudflareAuditor._request raises for an HTTP failure."""
    response = httpx.Response(
        status_code,
        json={"success": False, "errors": [{"code": code, "message": message}]},
        request=httpx.Request("GET", f"{BASE_URL}{path}"),
    )
    auditor = make_auditor()
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return auditor._error(
            f"Cloudflare API returned HTTP {exc.response.status_code}: {exc.response.text}",
            status_code=exc.response.status_code,
            error_codes=(code,),
        )
    raise AssertionError("expected an HTTP error")


def test_account_token_verifies_without_touching_the_user_endpoint(mocker):
    request = mocker.patch.object(
        CloudflareAuditor,
        "_request",
        return_value=verify_payload(),
    )

    result = make_auditor().verify_connection()

    assert result == {"id": "token-id", "status": "active"}
    request.assert_called_once_with(ACCOUNT_VERIFY_PATH)


def test_user_token_falls_back_to_the_user_verify_endpoint(mocker):
    """A User API Token gets HTTP 401 / code 1000 on the account endpoint but is valid."""
    request = mocker.patch.object(
        CloudflareAuditor,
        "_request",
        side_effect=[
            http_error(401, 1000, "Invalid API Token", ACCOUNT_VERIFY_PATH),
            verify_payload(expires_on="2099-01-01T23:59:59Z"),
        ],
    )

    result = make_auditor().verify_connection()

    assert result["status"] == "active"
    assert [call.args[0] for call in request.call_args_list] == [
        ACCOUNT_VERIFY_PATH,
        USER_TOKEN_VERIFY_PATH,
    ]


def test_user_token_falls_back_when_the_account_endpoint_returns_success_false(mocker):
    """Cloudflare sometimes reports the same rejection as HTTP 200 with success: false."""
    request = mocker.patch.object(
        CloudflareAuditor,
        "_request",
        side_effect=[
            failure_payload(1000, "Invalid API Token"),
            verify_payload(),
        ],
    )

    assert make_auditor().verify_connection()["status"] == "active"
    assert request.call_count == 2


def test_both_endpoints_failing_raises_naming_both_attempts(mocker):
    mocker.patch.object(
        CloudflareAuditor,
        "_request",
        side_effect=[
            http_error(401, 1000, "Invalid API Token", ACCOUNT_VERIFY_PATH),
            http_error(401, 1000, "Invalid API Token", USER_TOKEN_VERIFY_PATH),
        ],
    )

    with pytest.raises(CloudflareAPIError) as excinfo:
        make_auditor().verify_connection()

    message = str(excinfo.value)
    assert "Account token endpoint" in message
    assert "User token endpoint" in message
    assert USER_TOKEN_VERIFY_PATH in message
    assert "/tokens/verify" in message


def test_expired_status_is_passed_through_not_treated_as_failure(mocker):
    """The expiry contract in docs/cloudflare-api-token-runbook.md: callers read `status`."""
    mocker.patch.object(
        CloudflareAuditor,
        "_request",
        return_value=verify_payload(status="expired", expires_on="2099-01-01T23:59:59Z"),
    )

    result = make_auditor().verify_connection()

    assert result["status"] == "expired"
    assert result["expires_on"] == "2099-01-01T23:59:59Z"


def test_expired_status_is_passed_through_from_the_user_endpoint(mocker):
    mocker.patch.object(
        CloudflareAuditor,
        "_request",
        side_effect=[
            http_error(401, 1000, "Invalid API Token", ACCOUNT_VERIFY_PATH),
            verify_payload(status="disabled"),
        ],
    )

    assert make_auditor().verify_connection()["status"] == "disabled"


def test_non_auth_failure_is_not_retried_and_is_not_swallowed(mocker):
    request = mocker.patch.object(
        CloudflareAuditor,
        "_request",
        side_effect=CloudflareAPIError("Cloudflare API request failed: connection refused"),
    )

    with pytest.raises(CloudflareAPIError, match="connection refused"):
        make_auditor().verify_connection()

    request.assert_called_once_with(ACCOUNT_VERIFY_PATH)


def test_missing_result_object_is_reported_without_a_fallback(mocker):
    request = mocker.patch.object(
        CloudflareAuditor,
        "_request",
        return_value={"success": True, "errors": [], "result": None},
    )

    with pytest.raises(CloudflareAPIError, match="did not include a result object"):
        make_auditor().verify_connection()

    request.assert_called_once_with(ACCOUNT_VERIFY_PATH)


def test_code_1000_hint_does_not_blame_the_account_id(mocker):
    mocker.patch.object(
        CloudflareAuditor,
        "_request",
        side_effect=[
            failure_payload(1000, "Invalid API Token"),
            failure_payload(1000, "Invalid API Token"),
        ],
    )

    with pytest.raises(CloudflareAPIError) as excinfo:
        make_auditor().verify_connection()

    message = str(excinfo.value)
    assert "error 1000" in message
    assert "endpoint it was sent to" in message
    assert "expired, revoked, or deleted" not in message


def test_code_9109_hint_reports_expiry_or_revocation(mocker):
    mocker.patch.object(
        CloudflareAuditor,
        "_request",
        side_effect=[
            http_error(403, 9109, "Invalid access token", ACCOUNT_VERIFY_PATH),
            http_error(403, 9109, "Invalid access token", USER_TOKEN_VERIFY_PATH),
        ],
    )

    with pytest.raises(CloudflareAPIError) as excinfo:
        make_auditor().verify_connection()

    message = str(excinfo.value)
    assert "error 9109" in message
    assert "expired, revoked, or deleted" in message


def test_unclassified_failure_still_gets_a_generic_hint(mocker):
    mocker.patch.object(
        CloudflareAuditor,
        "_request",
        side_effect=[
            CloudflareAPIError("boom", status_code=403),
            CloudflareAPIError("boom", status_code=403),
        ],
    )

    with pytest.raises(CloudflareAPIError) as excinfo:
        make_auditor().verify_connection()

    assert "CLOUDFLARE_API_TOKEN holds the token secret" in str(excinfo.value)


def test_account_id_never_appears_in_verification_failure_text(mocker):
    """The account ID must not reach an exception message, its chain, or a traceback."""
    response = httpx.Response(
        401,
        json={
            "success": False,
            "errors": [{"code": 1000, "message": "Invalid API Token"}],
            "account_id": PLACEHOLDER_ACCOUNT_ID,
        },
        request=httpx.Request("GET", f"{BASE_URL}{ACCOUNT_VERIFY_PATH}"),
    )
    mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)

    with pytest.raises(CloudflareAPIError) as excinfo:
        make_auditor().verify_connection()

    rendered = "".join(
        traceback.format_exception(type(excinfo.value), excinfo.value, excinfo.value.__traceback__)
    )
    assert PLACEHOLDER_ACCOUNT_ID not in str(excinfo.value)
    assert PLACEHOLDER_ACCOUNT_ID not in rendered
    assert REDACTED_ACCOUNT_ID in str(excinfo.value)


def test_account_id_never_appears_in_zone_request_failure_text(mocker):
    response = httpx.Response(
        403,
        json={"success": False, "errors": [{"code": 9109, "message": "Invalid access token"}]},
        request=httpx.Request(
            "GET",
            f"{BASE_URL}/zones?account.id={PLACEHOLDER_ACCOUNT_ID}&page=1&per_page=50",
        ),
    )
    mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)
    auditor = make_auditor()

    with pytest.raises(CloudflareAPIError) as excinfo:
        auditor._request(auditor._zones_path(1))

    rendered = "".join(
        traceback.format_exception(type(excinfo.value), excinfo.value, excinfo.value.__traceback__)
    )
    assert PLACEHOLDER_ACCOUNT_ID not in str(excinfo.value)
    assert PLACEHOLDER_ACCOUNT_ID not in rendered


def test_request_error_codes_are_captured_from_the_response_body(mocker):
    response = httpx.Response(
        403,
        json={"success": False, "errors": [{"code": 9109, "message": "Invalid access token"}]},
        request=httpx.Request("GET", f"{BASE_URL}/failure"),
    )
    mocker.patch("scripts.cloudflare_client.httpx.get", return_value=response)

    with pytest.raises(CloudflareAPIError) as excinfo:
        make_auditor()._request("/failure")

    assert excinfo.value.status_code == 403
    assert excinfo.value.error_codes == (9109,)


@pytest.mark.parametrize("body", ["not json at all", "[1, 2, 3]", '{"errors": "nope"}'])
def test_error_codes_from_body_tolerates_unparseable_responses(body):
    assert CloudflareAuditor._error_codes_from_body(body) == ()


def test_verify_connection_reaches_the_user_endpoint_over_http(mocker):
    """End-to-end through the HTTP layer: account endpoint 401, user endpoint 200."""
    account_response = httpx.Response(
        401,
        json={"success": False, "errors": [{"code": 1000, "message": "Invalid API Token"}]},
        request=httpx.Request("GET", f"{BASE_URL}{ACCOUNT_VERIFY_PATH}"),
    )
    user_response = httpx.Response(
        200,
        json=verify_payload(expires_on="2099-01-01T23:59:59Z"),
        request=httpx.Request("GET", f"{BASE_URL}{USER_TOKEN_VERIFY_PATH}"),
    )
    http_get = mocker.patch(
        "scripts.cloudflare_client.httpx.get",
        side_effect=[account_response, user_response],
    )

    assert make_auditor().verify_connection()["status"] == "active"
    assert [call.args[0] for call in http_get.call_args_list] == [
        f"{BASE_URL}{ACCOUNT_VERIFY_PATH}",
        f"{BASE_URL}{USER_TOKEN_VERIFY_PATH}",
    ]
