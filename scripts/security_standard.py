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
_ZONE_SETTING_RESOURCE = "cloudflare_zone_setting"
_BOT_MANAGEMENT_RESOURCE = "cloudflare_bot_management"
_VALID_RESOURCES = {_ZONE_SETTING_RESOURCE, _BOT_MANAGEMENT_RESOURCE}


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
    control_keys: set[str] = set()
    for index, control in enumerate(controls):
        label = f"Security standard control at index {index}"
        if not isinstance(control, dict) or set(control) != _CONTROL_KEYS:
            raise SecurityStandardError(f"{label} must contain exactly the required fields.")

        key = control["key"]
        expected = control["expected"]
        resource = control["resource"]
        setting_id = control["setting_id"]
        auto_correct = control["auto_correct"]
        if not isinstance(key, str) or not key:
            raise SecurityStandardError(f"{label} key must be a non-empty string.")
        if not isinstance(expected, str) or not expected:
            raise SecurityStandardError(f"{label} expected must be a non-empty string.")
        if type(auto_correct) is not bool:
            raise SecurityStandardError(f"{label} auto_correct must be a bool.")
        if resource not in _VALID_RESOURCES:
            raise SecurityStandardError(f"{label} resource is not supported.")
        if resource == _ZONE_SETTING_RESOURCE and (
            not isinstance(setting_id, str) or not setting_id
        ):
            raise SecurityStandardError(f"{label} setting_id must be a non-empty string.")
        if resource == _BOT_MANAGEMENT_RESOURCE and setting_id is not None:
            raise SecurityStandardError(f"{label} setting_id must be null.")
        if key in control_keys:
            raise SecurityStandardError(f"Security standard contains duplicate control key: {key}.")

        control_keys.add(key)
        parsed_controls.append(
            SecurityControl(
                key=key,
                resource=resource,
                setting_id=setting_id,
                expected=expected,
                auto_correct=auto_correct,
            )
        )

    return tuple(parsed_controls)


def expected_values(controls: tuple[SecurityControl, ...]) -> dict[str, str]:
    """Return expected values keyed in the document's control order."""
    return {control.key: control.expected for control in controls}
