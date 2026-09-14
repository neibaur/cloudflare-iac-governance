"""Verify an ADR 0001 phase 3 import plan without displaying zone identities.

Given a saved plan file, runs `terraform -chdir=terraform show -json` on it and checks that every
inventory zone imports exactly its policy zone settings and its bot management, each bound to its
own zone ID, and that the plan changes nothing else. Only counts and a result line are printed.

Running `terraform show` itself, rather than reading a PowerShell pipe, keeps Windows PowerShell 5.1
from re-encoding the JSON, and never writes the plan's identities to disk.

    python -m scripts.check_import_plan <saved plan file>
"""

from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from scripts.security_standard import (
    BOT_MANAGEMENT_RESOURCE,
    ZONE_SETTING_RESOURCE,
    SecurityControl,
    load_security_standard,
)

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ZONE_MODULE = "module.cloudflare_zone_config"


class ImportPlanError(ValueError):
    """Raised when the input is not a usable Terraform JSON plan."""


@dataclass(frozen=True)
class ImportPlanReport:
    zones: int
    expected_imports: int
    found_imports: int
    missing_imports: int
    unexpected_imports: int
    wrong_ids: int
    other_changes: int
    errored: bool
    imports_enabled: bool

    @property
    def passed(self) -> bool:
        return (
            not self.errored
            and self.imports_enabled
            and self.zones > 0
            and self.found_imports == self.expected_imports
            and self.missing_imports == 0
            and self.unexpected_imports == 0
            and self.wrong_ids == 0
            and self.other_changes == 0
        )


def expected_imports(
    domains: dict[str, str], controls: tuple[SecurityControl, ...]
) -> dict[str, str]:
    """Return the import ID expected at each resource address, keyed by address."""
    setting_ids = [
        control.setting_id
        for control in controls
        if control.resource == ZONE_SETTING_RESOURCE and control.setting_id is not None
    ]
    manages_bot = any(control.resource == BOT_MANAGEMENT_RESOURCE for control in controls)
    expected: dict[str, str] = {}
    for domain, zone_id in domains.items():
        module = f'{ZONE_MODULE}["{domain}"]'
        for setting_id in setting_ids:
            expected[f'{module}.{ZONE_SETTING_RESOURCE}.this["{setting_id}"]'] = (
                f"{zone_id}/{setting_id}"
            )
        if manages_bot:
            expected[f"{module}.{BOT_MANAGEMENT_RESOURCE}.this"] = zone_id
    return expected


def _variable_value(plan: dict[str, Any], name: str) -> Any:
    variables = plan.get("variables")
    if not isinstance(variables, dict) or not isinstance(variables.get(name), dict):
        raise ImportPlanError(f"The plan does not record the {name} variable.")
    return variables[name].get("value")


def _inventory(plan: dict[str, Any]) -> dict[str, str]:
    domains = _variable_value(plan, "domains")
    if not isinstance(domains, dict):
        raise ImportPlanError("The plan's domains variable is not a map.")
    inventory: dict[str, str] = {}
    for domain, entry in domains.items():
        zone_id = entry.get("zone_id") if isinstance(entry, dict) else None
        if not isinstance(zone_id, str) or not zone_id:
            raise ImportPlanError("A domains entry in the plan has no zone_id.")
        inventory[str(domain)] = zone_id
    return inventory


def check_import_plan(
    plan: dict[str, Any], controls: tuple[SecurityControl, ...]
) -> ImportPlanReport:
    """Compare a Terraform JSON plan's imports and changes against the inventory and policy."""
    inventory = _inventory(plan)
    expected = expected_imports(inventory, controls)

    changes = plan.get("resource_changes", [])
    if not isinstance(changes, list):
        raise ImportPlanError("The plan's resource_changes is not a list.")

    found: dict[str, Any] = {}
    other_changes = 0
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("change"), dict):
            raise ImportPlanError("The plan contains a malformed resource change.")
        details = change["change"]
        importing = details.get("importing")
        if isinstance(importing, dict):
            found[str(change.get("address"))] = importing.get("id")
        # An import that also updates, or any create, delete, or replace, is a change.
        if details.get("actions") != ["no-op"]:
            other_changes += 1

    return ImportPlanReport(
        zones=len(inventory),
        expected_imports=len(expected),
        found_imports=len(found),
        missing_imports=len(expected.keys() - found.keys()),
        unexpected_imports=len(found.keys() - expected.keys()),
        wrong_ids=sum(
            1
            for address, import_id in found.items()
            if address in expected and import_id != expected[address]
        ),
        other_changes=other_changes,
        errored=plan.get("errored") is True,
        imports_enabled=_variable_value(plan, "import_existing_zones") is True,
    )


def format_report(report: ImportPlanReport) -> list[str]:
    return [
        f"Inventory zones:          {report.zones}",
        f"Expected imports:         {report.expected_imports}",
        f"Imports in plan:          {report.found_imports}",
        f"Missing imports:          {report.missing_imports}",
        f"Unexpected imports:       {report.unexpected_imports}",
        f"Imports with a wrong ID:  {report.wrong_ids}",
        f"Other resource changes:   {report.other_changes}",
        f"Plan errored:             {'yes' if report.errored else 'no'}",
        f"import_existing_zones:    {'true' if report.imports_enabled else 'false'}",
        "RESULT: PASS" if report.passed else "RESULT: FAIL",
    ]


def read_plan_json(plan_file: Path) -> str:
    """Return `terraform show -json` output for a saved plan, without echoing Terraform's output."""
    if not plan_file.is_file():
        raise ImportPlanError("The plan file does not exist.")
    result = subprocess.run(  # nosec B603 B607
        [
            "terraform",
            f"-chdir={REPOSITORY_ROOT / 'terraform'}",
            "show",
            "-json",
            str(plan_file.resolve()),
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ImportPlanError(f"terraform show failed with exit code {result.returncode}.")
    return result.stdout.decode("utf-8")


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) > 1:
            raise ImportPlanError("Usage: python -m scripts.check_import_plan <saved plan file>")
        text = (
            read_plan_json(Path(args[0]))
            if args
            else (sys.stdin if stdin is None else stdin).read()
        )
        plan = json.loads(text)
    except ImportPlanError as exc:
        print(str(exc))
        print("RESULT: FAIL")
        return 1
    except json.JSONDecodeError:
        # Never echo the input: it contains zone identities.
        print("The plan output is not valid JSON.")
        print("RESULT: FAIL")
        return 1
    try:
        if not isinstance(plan, dict):
            raise ImportPlanError("Input is not a Terraform JSON plan.")
        report = check_import_plan(plan, load_security_standard())
    except ImportPlanError as exc:
        print(str(exc))
        print("RESULT: FAIL")
        return 1

    for line in format_report(report):
        print(line)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
