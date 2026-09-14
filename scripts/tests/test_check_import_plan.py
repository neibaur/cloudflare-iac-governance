from __future__ import annotations

import io
import json
import subprocess  # nosec B404
from typing import Any

import pytest

from scripts import check_import_plan
from scripts.security_standard import load_security_standard

DOMAINS = {
    "first.example": "023e105f4ecef8ad9ca31a8372d0c353",
    "second.example": "023e105f4ecef8ad9ca31a8372d0c354",
}


def clean_plan() -> dict[str, Any]:
    """A plan that imports every expected object with its own ID and changes nothing else."""
    expected = check_import_plan.expected_imports(DOMAINS, load_security_standard())
    return {
        "errored": False,
        "variables": {
            "domains": {"value": {name: {"zone_id": zone} for name, zone in DOMAINS.items()}},
            "import_existing_zones": {"value": True},
        },
        "resource_changes": [
            {"address": address, "change": {"actions": ["no-op"], "importing": {"id": import_id}}}
            for address, import_id in expected.items()
        ],
    }


def run_main(plan: object, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = check_import_plan.main([], io.StringIO(json.dumps(plan)))
    return code, capsys.readouterr().out


def test_expected_imports_cover_policy_settings_and_bot_management_per_zone():
    controls = load_security_standard()
    expected = check_import_plan.expected_imports(DOMAINS, controls)

    per_zone = sum(1 for control in controls if control.setting_id is not None) + 1
    assert len(expected) == per_zone * len(DOMAINS)
    assert (
        expected[
            'module.cloudflare_zone_config["second.example"].cloudflare_zone_setting.this["ssl"]'
        ]
        == "023e105f4ecef8ad9ca31a8372d0c354/ssl"
    )
    assert (
        expected['module.cloudflare_zone_config["first.example"].cloudflare_bot_management.this']
        == "023e105f4ecef8ad9ca31a8372d0c353"
    )


def test_clean_plan_passes_without_printing_identities(capsys):
    code, output = run_main(clean_plan(), capsys)

    assert code == 0
    assert output.splitlines()[-1] == "RESULT: PASS"
    for domain, zone_id in DOMAINS.items():
        assert domain not in output
        assert zone_id not in output


def test_import_bound_to_another_zone_fails(capsys):
    plan = clean_plan()
    first = plan["resource_changes"][0]
    first["change"]["importing"]["id"] = first["change"]["importing"]["id"].replace(
        DOMAINS["first.example"], DOMAINS["second.example"]
    )

    code, output = run_main(plan, capsys)

    assert code == 1
    assert "Imports with a wrong ID:  1" in output
    assert DOMAINS["second.example"] not in output


def test_missing_and_unexpected_imports_fail(capsys):
    plan = clean_plan()
    plan["resource_changes"][0]["address"] = (
        'module.cloudflare_zone_config["first.example"].cloudflare_zone_setting.this["other"]'
    )

    code, output = run_main(plan, capsys)

    assert code == 1
    assert "Missing imports:          1" in output
    assert "Unexpected imports:       1" in output


@pytest.mark.parametrize("actions", [["update"], ["create"], ["delete"], ["delete", "create"]])
def test_any_resource_change_fails(capsys, actions):
    plan = clean_plan()
    plan["resource_changes"][0]["change"]["actions"] = actions

    code, output = run_main(plan, capsys)

    assert code == 1
    assert "Other resource changes:   1" in output


def test_errored_plan_fails(capsys):
    plan = clean_plan()
    plan["errored"] = True

    code, output = run_main(plan, capsys)

    assert code == 1
    assert "Plan errored:             yes" in output


def test_plan_with_imports_disabled_fails(capsys):
    plan = clean_plan()
    plan["variables"]["import_existing_zones"]["value"] = False

    code, _ = run_main(plan, capsys)

    assert code == 1


def test_plan_with_no_zones_fails(capsys):
    plan = clean_plan()
    plan["variables"]["domains"]["value"] = {}
    plan["resource_changes"] = []

    code, _ = run_main(plan, capsys)

    assert code == 1


def test_invalid_json_fails_without_echoing_input(capsys):
    code = check_import_plan.main([], io.StringIO('{"zone": "023e105f4ecef8ad9ca31a8372d0c353"'))
    output = capsys.readouterr().out

    assert code == 1
    assert "023e105f4ecef8ad9ca31a8372d0c353" not in output
    assert output.splitlines()[-1] == "RESULT: FAIL"


@pytest.mark.parametrize(
    "plan",
    [
        [],
        {"variables": {}},
        {"variables": {"domains": {"value": {"first.example": {}}}}},
        {
            "variables": {
                "domains": {"value": {}},
                "import_existing_zones": {"value": True},
            },
            "resource_changes": [{"address": "x"}],
        },
    ],
)
def test_malformed_plans_fail(capsys, plan):
    code, output = run_main(plan, capsys)

    assert code == 1
    assert output.splitlines()[-1] == "RESULT: FAIL"


def test_plan_file_is_read_through_terraform_show(monkeypatch, tmp_path, capsys):
    plan_file = tmp_path / "import.tfplan"
    plan_file.write_bytes(b"binary plan")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(clean_plan()).encode(), b"")

    monkeypatch.setattr(check_import_plan.subprocess, "run", fake_run)

    code = check_import_plan.main([str(plan_file)])

    assert code == 0
    assert calls[0][0] == "terraform"
    assert calls[0][2:4] == ["show", "-json"]
    assert calls[0][4] == str(plan_file.resolve())
    assert capsys.readouterr().out.splitlines()[-1] == "RESULT: PASS"


def test_failed_terraform_show_fails_without_its_output(monkeypatch, tmp_path, capsys):
    plan_file = tmp_path / "import.tfplan"
    plan_file.write_bytes(b"binary plan")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, b"", b"023e105f4ecef8ad9ca31a8372d0c353")

    monkeypatch.setattr(check_import_plan.subprocess, "run", fake_run)

    code = check_import_plan.main([str(plan_file)])
    output = capsys.readouterr().out

    assert code == 1
    assert "exit code 1" in output
    assert "023e105f4ecef8ad9ca31a8372d0c353" not in output


@pytest.mark.parametrize("argv", [["missing.tfplan"], ["one.tfplan", "two.tfplan"]])
def test_missing_plan_file_or_extra_arguments_fail(tmp_path, capsys, argv):
    code = check_import_plan.main([str(tmp_path / name) for name in argv])

    assert code == 1
    assert capsys.readouterr().out.splitlines()[-1] == "RESULT: FAIL"
