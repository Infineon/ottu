"""Query connected devices by definition key."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .device import Device

DeviceFilter = Mapping[str, Any] | str


class DeviceQuery:
    """Select device values from the devices that are connected."""

    @staticmethod
    def find(
        devices: Sequence[Device],
        device_filter: DeviceFilter | Sequence[DeviceFilter] | None = None,
        *,
        limit: int | None = None,
        check_connected: bool = True,
    ) -> list[Device]:
        """Return connected devices matching a device query or filter sequence.

        A bare string matches a device name, UID, or address. Key-value
        strings and mappings define filters; a sequence matches when any
        filter matches. Multiple keys within one filter must all match. No
        filters match every device. Results retain device-list order and are
        limited when requested.

        Examples:
            ``find(devices, "uno")`` matches a device by name.
            ``find(devices, {"uid": "abc123"})`` matches a device by UID.
            ``find(devices, {"name": "uno", "uid": "abc123"})`` requires
            both fields to match.
            ``find(devices, [{"name": "uno"}, {"name": "nano"}])``
            matches either name.
            ``find(devices, "name=uno,uid=abc123")`` parses multiple fields
            from one string.
            ``find(devices, {"features": ["wifi", "ble"]}, limit=1)``
            matches required features and limits the result count.
        """
        if limit is not None and limit < 1:
            raise ValueError("Device query limit must be positive.")

        parsed = DeviceQuery.parse(device_filter)
        for device_filter_values in parsed:
            for filter_key in device_filter_values:
                Device.validate_key(filter_key)

        matches: list[Device] = []
        for device in devices:
            if check_connected:
                if not device.is_connected():
                    continue
            if not DeviceQuery._matches(device, parsed, check_connected):
                continue
            matches.append(device)
            if limit is not None and len(matches) == limit:
                break
        return matches

    @staticmethod
    def parse(
        device_filter: DeviceFilter | Sequence[DeviceFilter] | None,
    ) -> list[Mapping[str, Any]]:
        """Return the filter mappings that a device query stands for.

        A bare string stands for the identity filters of a device (name, UID
        or address), key-value strings are parsed, and mappings are kept. The
        result lists alternatives: a device matches when any one of them
        matches, and no filters match every device. Keys are not validated,
        so callers may carry extra keys such as a role.

        Examples:
            ``parse("name=uno,uid=abc123")`` returns
            ``[{"name": "uno", "uid": "abc123"}]``.
            ``parse("uno")`` returns one filter for each identity key.
        """
        if device_filter is None:
            filters: tuple[DeviceFilter, ...] = ()
        elif isinstance(device_filter, str) and "=" not in device_filter:
            filters = Device.from_string(device_filter).identity_filters()
        elif isinstance(device_filter, Sequence) and not isinstance(
            device_filter, (str, bytes)
        ):
            filters = tuple(device_filter)
        else:
            filters = (device_filter,)
        return [DeviceQuery._parse_filter(value) for value in filters]

    @staticmethod
    def combine(
        first: Mapping[str, Any], second: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """Require two filters to match together, or return ``None``.

        A key set by both filters must have the same value; otherwise no
        device could satisfy both and there is no combined filter.

        Examples:
            ``combine({"name": "uno"}, {"uid": "abc"})`` returns
            ``{"name": "uno", "uid": "abc"}``.
            ``combine({"name": "uno"}, {"name": "nano"})`` returns ``None``.
        """
        if any(key in first and first[key] != value for key, value in second.items()):
            return None
        return {**first, **second}

    @staticmethod
    def select(
        devices: Sequence[Device],
        key: str,
        filters: Sequence[DeviceFilter] = (),
        *,
        check_connected: bool = True,
    ) -> list[Any]:
        """Return non-null values for ``key`` from devices matching filters.

        Matching, connectivity checks, and filter validation are delegated to
        ``find``. Devices without a value for ``key`` are omitted.

        Examples:
            ``select(devices, "uid", [{"name": "uno"}])`` returns UIDs
            for matching devices.
            ``select(devices, "address")`` returns addresses for all
            connected devices.
        """
        Device.validate_key(key)
        return [
            device_value
            for device in DeviceQuery.find(
                devices,
                filters,
                check_connected=check_connected,
            )
            if (device_value := DeviceQuery._get_value(device, key, check_connected))
            is not None
        ]

    @staticmethod
    def _parse_filter(device_filter: DeviceFilter) -> Mapping[str, Any]:
        """Convert one filter string into a validated mapping shape."""
        if not isinstance(device_filter, str):
            return device_filter
        values: dict[str, Any] = {}
        for part in DeviceQuery._split_filter_parts(device_filter):
            key, separator, value = part.partition("=")
            key = key.strip()
            value = value.strip()
            if not separator or not key or not value:
                raise ValueError("Filters must use key=value format.")
            if key in values:
                raise ValueError(f"Filter '{key}' was provided more than once.")
            if value.startswith(("{", "[")):
                try:
                    values[key] = json.loads(value)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Filter '{key}' has invalid JSON value."
                    ) from error
            else:
                values[key] = value
        return values

    @staticmethod
    def _split_filter_parts(device_filter: str) -> list[str]:
        """Split comma-separated filters outside JSON and quoted values.

        Examples:
            >>> DeviceQuery._split_filter_parts("name=uno,uid=abc123")
            ['name=uno', 'uid=abc123']
            >>> DeviceQuery._split_filter_parts(
            ...     'features=["wifi", "ble"],name=uno'
            ... )
            ['features=["wifi", "ble"]', 'name=uno']
        """
        parts: list[str] = []
        start = 0
        depth = 0
        quote: str | None = None
        escaped = False
        for index, character in enumerate(device_filter):
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
                parts.append(device_filter[start:index])
                start = index + 1
        parts.append(device_filter[start:])
        return parts

    @staticmethod
    def _matches(
        device: Device,
        filters: Sequence[Mapping[str, Any]],
        check_connected: bool = False,
    ) -> bool:
        """Return whether a device matches at least one filter mapping."""
        if not filters:
            return True
        return any(
            all(
                DeviceQuery._value_matches(
                    DeviceQuery._get_value(device, key, check_connected), expected
                )
                for key, expected in device_filter.items()
            )
            for device_filter in filters
        )

    @staticmethod
    def _get_value(device: Device, key: str, check_connected: bool) -> Any:
        """Return a device value used for filter or selection matching."""
        return device.get(key)

    @staticmethod
    def _value_matches(actual: Any, expected: Any) -> bool:
        """Compare scalar values or require every expected list item."""
        if not isinstance(actual, list):
            return bool(actual == expected)
        required = expected if isinstance(expected, list) else [expected]
        return all(
            any(DeviceQuery._item_matches(item, wanted) for item in actual)
            for wanted in required
        )

    @staticmethod
    def _item_matches(item: Any, wanted: Any) -> bool:
        """Compare one list item, including partial dictionary matching."""
        if isinstance(item, dict) and isinstance(wanted, dict):
            return all(
                key in item and item[key] == value for key, value in wanted.items()
            )
        return bool(item == wanted)


query = DeviceQuery.select
