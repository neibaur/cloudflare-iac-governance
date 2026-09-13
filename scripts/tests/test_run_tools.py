from datetime import UTC, datetime
from pathlib import Path

import pytest

import run_tools


def test_read_cloudflare_env_loads_token_and_account_id(monkeypatch, mocker):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    mocker.patch.object(
        run_tools,
        "load_dotenv",
        side_effect=lambda _path: (
            monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "env-token"),
            monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "env-account-id"),
        ),
    )

    token, account_id = run_tools.read_cloudflare_env(Path(".env"))

    assert token == "env-token"
    assert account_id == "env-account-id"


def test_read_cloudflare_env_requires_token(monkeypatch, mocker):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    mocker.patch.object(
        run_tools,
        "load_dotenv",
        side_effect=lambda _path: monkeypatch.setenv(
            "CLOUDFLARE_ACCOUNT_ID",
            "env-account-id",
        ),
    )

    with pytest.raises(RuntimeError, match="CLOUDFLARE_API_TOKEN"):
        run_tools.read_cloudflare_env(Path(".env"))


@pytest.mark.parametrize(
    ("expires_on", "expected"),
    [
        ("2026-09-12T12:00:00Z", "ERROR"),
        ("2026-09-20T12:00:00Z", "WARNING"),
        ("2026-10-20T12:00:00Z", ""),
        (None, ""),
    ],
)
def test_token_expiry_messages(expires_on, expected, capsys):
    verification = {} if expires_on is None else {"expires_on": expires_on}

    run_tools.warn_if_token_expires_soon(
        verification,
        now=datetime(2026, 9, 13, 12, tzinfo=UTC),
    )

    stderr = capsys.readouterr().err
    if expected:
        assert stderr.startswith(expected)
    else:
        assert stderr == ""


@pytest.mark.parametrize("action", ["verify", "list", "audit"])
def test_main_checks_expiry_and_closes_client(mocker, action):
    args = mocker.Mock(
        verify=action == "verify",
        list=action == "list",
        audit=action == "audit",
        redact_identities=True,
    )
    mocker.patch.object(run_tools, "parse_args", return_value=args)
    mocker.patch.object(run_tools, "read_cloudflare_env", return_value=("token", "account"))
    auditor_type = mocker.patch.object(run_tools, "CloudflareAuditor")
    auditor = auditor_type.return_value.__enter__.return_value
    verification = {"status": "active", "expires_on": "2099-01-01T00:00:00Z"}
    auditor.verify_connection.return_value = verification
    warning = mocker.patch.object(run_tools, "warn_if_token_expires_soon")

    assert run_tools.main() == 0

    warning.assert_called_once_with(verification)
    auditor_type.return_value.__exit__.assert_called_once()
    if action == "list":
        auditor.list_all_zones.assert_called_once_with()
    else:
        auditor.list_all_zones.assert_not_called()
    if action == "audit":
        auditor.audit_security_posture.assert_called_once_with(
            run_tools.REPORT_DIR, show_identities=False
        )
    else:
        auditor.audit_security_posture.assert_not_called()
