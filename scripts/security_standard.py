"""Validated access to the repository's zone security standard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STANDARD_PATH = (
    Path(__file__).resolve().parent.parent / "policy" / "zone-security-standard.json"
)
_TOP_LEVEL_KEYS = {"schema_version", "controls"}
_CONTROL_KEYS = {"key", "resource", "setting_id", "expected", "auto_correct"}
ZONE_SETTING_RESOURCE = "cloudflare_zone_setting"
BOT_MANAGEMENT_RESOURCE = "cloudflare_bot_management"
_VALID_RESOURCES = {ZONE_SETTING_RESOURCE, BOT_MANAGEMENT_RESOURCE}


class SecurityStandardError(ValueError):
    """Raised when the security-standard document does not meet its contract."""


@dataclass(frozen=True)
class SecurityControl:
    key: str
    resource: str
    setting_id: str | None
    expected: str
    auto_correct: bool


def load_security_standard(path: Path = DEFAULT_STANDARD_PATH) -> tuple[SecurityControl, ...]:
    """Load and strictly validate the version-one zone security standard."""
    try:
        with path.open(encoding="utf-8") as standard_file:
            document = json.load(standard_file)
    except FileNotFoundError as exc:
        raise SecurityStandardError(f"Security standard file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SecurityStandardError(f"Security standard file is not valid JSON: {path}") from exc

    if not isinstance(document, dict) or set(document) != _TOP_LEVEL_KEYS:
        raise SecurityStandardError(
            "Security standard top level must contain schema_version and controls."
        )
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise SecurityStandardError("Security standard schema_version must be the integer 1.")

    controls = document["controls"]
    if not isinstance(controls, list) or not controls:
        raise SecurityStandardError("Security standard controls must be a non-empty list.")

    parsed_controls: list[SecurityControl] = []
    for index, control in enumerate(controls):
        if not isinstance(control, dict) or set(control) != _CONTROL_KEYS:
            raise SecurityStandardError(
                f"Security standard control at index {index} must contain exactly the required "
                "fields."
            )
        parsed_controls.append(
            SecurityControl(
                key=control["key"],
                resource=control["resource"],
                setting_id=control["setting_id"],
                expected=control["expected"],
                auto_correct=control["auto_correct"],
            )
        )

    return validate_controls(tuple(parsed_controls))


def validate_controls(controls: tuple[SecurityControl, ...]) -> tuple[SecurityControl, ...]:
    """Enforce the control contract for loaded or caller-supplied controls and return them."""
    if not isinstance(controls, tuple) or not controls:
        raise SecurityStandardError("Security controls must be a non-empty tuple.")

    control_keys: set[str] = set()
    setting_ids: set[str] = set()
    bot_management_controls = 0
    for index, control in enumerate(controls):
        label = f"Security standard control at index {index}"
        if not isinstance(control, SecurityControl):
            raise SecurityStandardError(f"{label} must be a SecurityControl.")

        key = control.key
        setting_id = control.setting_id
        if not isinstance(key, str) or not key:
            raise SecurityStandardError(f"{label} key must be a non-empty string.")
        if not isinstance(control.expected, str) or not control.expected:
            raise SecurityStandardError(f"{label} expected must be a non-empty string.")
        if type(control.auto_correct) is not bool:
            raise SecurityStandardError(f"{label} auto_correct must be a bool.")
        if not isinstance(control.resource, str) or control.resource not in _VALID_RESOURCES:
            raise SecurityStandardError(f"{label} resource is not supported.")
        if control.resource == ZONE_SETTING_RESOURCE and (
            not isinstance(setting_id, str) or not setting_id
        ):
            raise SecurityStandardError(f"{label} setting_id must be a non-empty string.")
        if control.resource == BOT_MANAGEMENT_RESOURCE and setting_id is not None:
            raise SecurityStandardError(f"{label} setting_id must be null.")
        if key in control_keys:
            raise SecurityStandardError(f"Security standard contains duplicate control key: {key}.")
        if isinstance(setting_id, str):
            if setting_id in setting_ids:
                raise SecurityStandardError(
                    f"Security standard contains duplicate setting_id: {setting_id}."
                )
            setting_ids.add(setting_id)
        if control.resource == BOT_MANAGEMENT_RESOURCE:
            bot_management_controls += 1
            if bot_management_controls > 1:
                raise SecurityStandardError(
                    "Security standard may contain at most one cloudflare_bot_management control."
                )

        control_keys.add(key)

    return controls


def expected_values(controls: tuple[SecurityControl, ...]) -> dict[str, str]:
    """Return expected values keyed in the document's control order."""
    return {control.key: control.expected for control in controls}
