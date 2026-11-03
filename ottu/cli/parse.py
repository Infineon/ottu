"""Parse argument and option strings into values."""

import json
from collections.abc import Sequence
from typing import Any

import click
from pydantic import ValidationError

from ottu.device import DeviceInput
from ottu.suite import RoleCount, SuiteCount, SuiteDeviceInput, SuiteInput
from ottu.test_path import TestPathInput


def parse_mapping(value: str, *, json_values: bool = False) -> dict[str | None, Any]:
    """Convert an argument or option string into a mapping.

    With ``json_values``, commas inside JSON brackets or quotes do not split
    pairs, and values beginning with ``{`` or ``[`` are decoded as JSON.
    """
    try:
        if not value.strip():
            raise ValueError("Value must not be empty.")
        if "=" not in value:
            return {None: value.strip()}

        items = _split_pairs(value) if json_values else value.split(",")
        mapping: dict[str | None, Any] = {}
        for item in items:
            key, separator, item_value = item.partition("=")
            key = key.strip()
            item_value = item_value.strip()
            if not separator or not key or not item_value:
                raise ValueError(
                    f"'{item.strip()}' in '{value}' must use key=value format."
                )
            if key in mapping:
                raise ValueError(f"Key '{key}' was provided more than once.")
            mapping[key] = (
                _decode_json(key, item_value)
                if json_values and item_value.startswith(("{", "["))
                else item_value
            )
        return mapping
    except ValueError as error:
        raise click.BadParameter(str(error)) from None


def _decode_json(key: str, value: str) -> Any:
    """Decode a JSON object or list value."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise click.BadParameter(f"Key '{key}' has an invalid JSON value.") from None


def _split_pairs(value: str) -> list[str]:
    """Split at commas outside JSON brackets and quoted values."""
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in ('"', "'"):
            quote = character
        elif character in "[{":
            depth += 1
        elif character in "]}":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def parse_test_path_input(value: str) -> TestPathInput:
    """Convert a tests argument value into a validated test path input.

    The value is either ``test_selector`` or ``role=test_selector``.
    """
    mapping = parse_mapping(value)
    if len(mapping) != 1:
        raise click.BadParameter(
            f"'{value}' must hold a single test selector, optionally "
            "qualified as role=test_selector."
        )
    ((role, test_selector),) = mapping.items()
    try:
        return TestPathInput(role=role, test_selector=test_selector)
    except ValidationError as error:
        raise click.BadParameter(str(error)) from None


def parse_suite_count(value: str) -> SuiteCount:
    """Convert a count option value into a suite-wide or role count.

    The value is a count, ``role=count``, or comma-separated ``role=count``
    pairs.
    """
    values = parse_mapping(value)
    if None in values:
        raw_count = values[None]
        try:
            count = int(raw_count)
            if count < 1:
                raise ValueError
            return count
        except ValueError:
            raise click.BadParameter(
                f"Count '{raw_count}' must be a positive integer."
            ) from None

    role_counts = []
    for role, raw_count in values.items():
        try:
            count = int(raw_count)
            assert role is not None  # a None key was handled above
            role_counts.append(RoleCount(role=role, count=count))
        except (ValueError, ValidationError):
            raise click.BadParameter(
                f"Count '{raw_count}' must be a positive integer."
            ) from None
    return tuple(role_counts)


def parse_device_input(value: str) -> DeviceInput:
    """Convert a device option value into a validated device input.

    A single feature value becomes a one-item list; JSON arrays and objects
    can also represent feature values.
    """
    mapping = parse_mapping(value, json_values=True)
    values = _device_values(mapping)
    try:
        return DeviceInput(**values)
    except ValidationError as error:
        raise click.BadParameter(str(error)) from None


def parse_suite_device_input(value: str) -> SuiteDeviceInput:
    """Convert a suite device option into a role and device selector."""
    mapping = parse_mapping(value, json_values=True)
    role = mapping.pop("role", None)
    values = _device_values(mapping)
    try:
        return SuiteDeviceInput(role=role, device=DeviceInput(**values))
    except ValidationError as error:
        raise click.BadParameter(str(error)) from None


def _device_values(mapping: dict[str | None, Any]) -> dict[str, Any]:
    """Normalize an identifier or feature value for a device model."""
    if None in mapping:
        values = {"identifier": mapping[None]}
    else:
        values = {key: value for key, value in mapping.items() if key is not None}
    if "features" in values and not isinstance(values["features"], list):
        values["features"] = [values["features"]]
    return values


def parse_suite_input(
    tests: Sequence[str] = (),
    exclude_tests: Sequence[str] = (),
    count: str | None = None,
    devices: Sequence[str] = (),
) -> SuiteInput:
    """Convert the arguments and options of the command into a suite input."""
    return SuiteInput(
        test_inputs=tuple(parse_test_path_input(test) for test in tests),
        exclude_test_inputs=tuple(
            parse_test_path_input(test) for test in exclude_tests
        ),
        count_input=parse_suite_count(count) if count else None,
        device_inputs=tuple(parse_suite_device_input(device) for device in devices),
    )
