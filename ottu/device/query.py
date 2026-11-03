"""Query connected devices by definition key."""

from collections.abc import Sequence
from typing import Any

from .device import Device, DeviceInput


class DeviceQuery:
    """Select device values from the devices that are connected."""

    @staticmethod
    def find(
        devices: Sequence[Device],
        device_filters: Sequence[DeviceInput] = (),
        *,
        limit: int | None = None,
        check_connected: bool = True,
    ) -> list[Device]:
        """Return devices matching one or more typed device inputs.

        Fields within an input are combined, and multiple inputs are
        alternatives. A bare identifier matches by name, UID, or address.
        Results retain device-list order and are limited when requested.
        """
        if limit is not None and limit < 1:
            raise ValueError("Device query limit must be positive.")

        if any(
            not isinstance(device_input, DeviceInput) for device_input in device_filters
        ):
            raise TypeError("Device queries require DeviceInput values.")

        matches: list[Device] = []
        for device in devices:
            if check_connected and not device.is_connected():
                continue
            if not DeviceQuery._matches(device, device_filters, check_connected):
                continue
            matches.append(device)
            if limit is not None and len(matches) == limit:
                break
        return matches

    @staticmethod
    def select(
        devices: Sequence[Device],
        key: str,
        filters: Sequence[DeviceInput] = (),
        *,
        check_connected: bool = True,
    ) -> list[Any]:
        """Return non-null values for ``key`` from matching devices."""
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
    def _matches(
        device: Device,
        filters: Sequence[DeviceInput],
        check_connected: bool = False,
    ) -> bool:
        """Return whether a device matches at least one input."""
        if not filters:
            return True
        return any(
            DeviceQuery._matches_input(device, device_input, check_connected)
            for device_input in filters
        )

    @staticmethod
    def _matches_input(
        device: Device, device_input: DeviceInput, check_connected: bool
    ) -> bool:
        """Return whether a device satisfies one typed input."""
        if device_input.identifier is not None and not any(
            DeviceQuery._value_matches(
                identity_value,
                device_input.identifier,
            )
            for identity_filter in device.identity_filters()
            for identity_value in identity_filter.values()
        ):
            return False

        values = device_input.model_dump(exclude={"identifier"}, exclude_none=True)
        return all(
            DeviceQuery._value_matches(
                DeviceQuery._get_value(device, key, check_connected), expected
            )
            for key, expected in values.items()
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
