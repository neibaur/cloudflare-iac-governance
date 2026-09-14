from __future__ import annotations

import json
from typing import cast

import pytest

from scripts.cloudflare_client import (
    CSV_COLUMN_BY_CONTROL,
    SECURITY_CSV_HEADERS,
    CloudflareAuditor,
)
from scripts.security_standard import (
    DEFAULT_STANDARD_PATH,
    SecurityStandardError,
    load_security_standard,
)


def valid_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "controls": [valid_control()],
    }


def valid_control() -> dict[str, object]:
    return {
        "key": "ssl",
        "resource": "cloudflare_zone_setting",
        "setting_id": "ssl",
        "expected": "full",
        "auto_correct": False,
    }


def test_real_standard_loads_the_six_controls_in_order():
    controls = load_security_standard()

    assert [control.key for control in controls] == [
        "ssl",
        "security_level",
        "always_use_https",
        "min_tls_version",
        "browser_check",
        "bot_fight_mode",
    ]


@pytest.mark.parametrize(
    "document",
    [
        "not-an-object",
        {"schema_version": 1},
        {"schema_version": 2, "controls": []},
        {"schema_version": True, "controls": []},
        {"schema_version": 1, "controls": {}},
        {"schema_version": 1, "controls": []},
        {"schema_version": 1, "controls": ["not-an-object"]},
        {
            "schema_version": 1,
            "controls": [{"key": "ssl", "resource": "cloudflare_zone_setting"}],
        },
        {
            "schema_version": 1,
            "controls": [
                {
                    "key": "",
                    "resource": "cloudflare_zone_setting",
                    "setting_id": "ssl",
                    "expected": "full",
                    "auto_correct": False,
                }
            ],
        },
        {
            "schema_version": 1,
            "controls": [
                {
                    "key": "ssl",
                    "resource": "cloudflare_zone_setting",
                    "setting_id": "ssl",
                    "expected": "",
                    "auto_correct": False,
                }
            ],
        },
        {
            "schema_version": 1,
            "controls": [
                {
                    "key": "ssl",
                    "resource": "cloudflare_zone_setting",
                    "setting_id": "ssl",
                    "expected": "full",
                    "auto_correct": "false",
                }
            ],
        },
        {
            "schema_version": 1,
            "controls": [
                {
                    "key": "ssl",
                    "resource": "unsupported",
                    "setting_id": "ssl",
                    "expected": "full",
                    "auto_correct": False,
                }
            ],
        },
        {
            "schema_version": 1,
            "controls": [
                {
                    "key": "ssl",
                    "resource": "cloudflare_zone_setting",
                    "setting_id": None,
                    "expected": "full",
                    "auto_correct": False,
                }
            ],
        },
        {
            "schema_version": 1,
            "controls": [
                {
                    "key": "bot_fight_mode",
                    "resource": "cloudflare_bot_management",
                    "setting_id": "bot_fight_mode",
                    "expected": "on",
                    "auto_correct": False,
                }
            ],
        },
        {
            "schema_version": 1,
            "controls": [
                valid_control(),
                valid_control(),
            ],
        },
    ],
)
def test_load_security_standard_rejects_invalid_documents(tmp_path, document):
    path = tmp_path / "standard.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SecurityStandardError):
        load_security_standard(path)


def test_load_security_standard_rejects_missing_and_invalid_json(tmp_path):
    with pytest.raises(SecurityStandardError):
        load_security_standard(tmp_path / "missing.json")

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(SecurityStandardError):
        load_security_standard(invalid_json)


def test_default_auditor_matches_policy_and_csv_columns():
    with DEFAULT_STANDARD_PATH.open(encoding="utf-8") as standard_file:
        document = json.load(standard_file)

    auditor = CloudflareAuditor("placeholder-token", "placeholder-account")
    policy_controls = cast(list[dict[str, str]], document["controls"])
    assert [control.key for control in auditor.controls] == [
        control["key"] for control in policy_controls
    ]
    assert auditor.expected_values == {
        control["key"]: control["expected"] for control in policy_controls
    }
    assert all(
        CSV_COLUMN_BY_CONTROL.get(control.key, control.key) in SECURITY_CSV_HEADERS
        for control in auditor.controls
    )
