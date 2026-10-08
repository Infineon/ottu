"""Query connected devices by definition key."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .device import Device

DeviceFilter = Mapping[str, Any] | str


class DeviceQuery:
    """Select device values from the devices that are connected."""

    @staticmethod
    def select(
        devices: Sequence[Device],
        key: str,
        filters: Sequence[DeviceFilter] = (),
        *,
        check_connected: bool = True,
    ) -> list[Any]:
        """Return ``key`` for devices matching any filter.

        Each filter is a key=value mapping that must match entirely, or a
        single ``"key=value"`` string whose value is read as JSON when it
        starts with ``{`` or ``[``; a device matches when at least one
        filter does. No filters match every device.
        List-valued keys match by containment, where a dict item matches any
        dict holding at least its pairs; other keys match by equality.
        Unless ``check_connected`` is false, only connected devices are
        considered and their hardware access is resolved first; otherwise
        values come from the definitions without touching hardware.
        """
        Device.validate_key(key)
        parsed = [DeviceQuery._parse_filter(device_filter) for device_filter in filters]
        for device_filter in parsed:
            for filter_key in device_filter:
                Device.validate_key(filter_key)

        values = []
        for device in devices:
            candidate = device
            if check_connected:
                if not device.is_connected():
                    continue
                candidate = device.acquire()
            if not DeviceQuery._matches(candidate, parsed):
                continue
            value = candidate.get(key)
            if value is not None:
                values.append(value)
        return values

    @staticmethod
    def _parse_filter(device_filter: DeviceFilter) -> Mapping[str, Any]:
        if not isinstance(device_filter, str):
            return device_filter
        name, separator, value = device_filter.partition("=")
        name = name.strip()
        value = value.strip()
        if not separator or not name or not value:
            raise ValueError("Filters must use key=value format.")
        if value.startswith(("{", "[")):
            try:
                return {name: json.loads(value)}
            except json.JSONDecodeError as error:
                raise ValueError(f"Filter '{name}' has invalid JSON value.") from error
        return {name: value}

    @staticmethod
    def _matches(device: Device, filters: Sequence[Mapping[str, Any]]) -> bool:
        if not filters:
            return True
        return any(
            all(
                DeviceQuery._value_matches(device.get(key), expected)
                for key, expected in device_filter.items()
            )
            for device_filter in filters
        )

    @staticmethod
    def _value_matches(actual: Any, expected: Any) -> bool:
        if not isinstance(actual, list):
            return bool(actual == expected)
        required = expected if isinstance(expected, list) else [expected]
        return all(
            any(DeviceQuery._item_matches(item, wanted) for item in actual)
            for wanted in required
        )

    @staticmethod
    def _item_matches(item: Any, wanted: Any) -> bool:
        if isinstance(item, dict) and isinstance(wanted, dict):
            return all(
                key in item and item[key] == value for key, value in wanted.items()
            )
        return bool(item == wanted)


query = DeviceQuery.select
