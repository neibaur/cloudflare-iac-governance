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
