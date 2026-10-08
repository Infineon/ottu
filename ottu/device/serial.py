"""Serial device access."""

import sys
from typing import Any, cast

from serial import Serial

from .access import ConnectionConfig, DeviceAccess, DeviceConnection


def _comports() -> Any:
    return sys.modules[__package__].comports()


class DeviceAccessSerial(DeviceAccess):
    """Access a device through a serial port."""

    @classmethod
    def _from_value(cls, value: str) -> "DeviceAccessSerial | None":
        if cls._is_port(value):
            return cls(address=value)
        if cls._is_uid(value):
            return cls(address="", uid=value)
        return None

    @staticmethod
    def _is_port(value: str) -> bool:
        """Return whether a value has a supported serial port format."""
        return any(
            value.startswith(prefix) for prefix in ("/dev/ttyACM", "/dev/ttyUSB", "COM")
        )

    @staticmethod
    def _is_uid(value: str) -> bool:
        """Return whether a value is a hexadecimal device UID."""
        return bool(value) and all(
            character in "0123456789abcdefABCDEF" for character in value
        )

    @classmethod
    def from_uid(cls, uid: str) -> "DeviceAccessSerial | None":
        for port in _comports():
            if port.serial_number == uid:
                return cls(address=port.device, uid=port.serial_number)
        return None

    def _validate(self) -> None:
        if self.address and not self._is_port(self.address):
            raise ValueError(f"Unsupported serial address '{self.address}'.")
        if self.uid is not None and not self._is_uid(self.uid):
            raise ValueError(f"Invalid serial UID '{self.uid}'.")

    def acquire(self) -> "DeviceAccessSerial":
        if not self.address:
            if self.uid is None:
                raise ValueError("A serial address or UID is required.")
            access = self.from_uid(self.uid)
            if access is None:
                raise LookupError(f"Serial device UID '{self.uid}' was not found.")
            return access

        if self.uid is None:
            return self

        for port in _comports():
            if port.device == self.address and port.serial_number == self.uid:
                return self
        raise ValueError(
            f"Device address '{self.address}' does not match UID '{self.uid}'."
        )

    def is_connected(self) -> bool:
        if not self.address and self.uid is None:
            return False
        return any(
            (not self.address or port.device == self.address)
            and (self.uid is None or port.serial_number == self.uid)
            for port in _comports()
        )

    @classmethod
    def scan(
        cls,
        attr_name: str | None = None,
        attr_value: Any = None,
    ) -> list["DeviceAccessSerial"]:
        access_list = []
        for port in _comports():
            if attr_name is None:
                access_list.append(cls(address=port.device, uid=port.serial_number))
            elif getattr(port, attr_name, None) == attr_value:
                access_list.append(cls(address=port.device, uid=port.serial_number))
        return access_list

    def connect(self, config: ConnectionConfig) -> DeviceConnection:
        """Open a serial connection using the supplied configuration."""
        if not self.address:
            raise ValueError("A serial address is required to read test output.")
        return cast(
            DeviceConnection,
            Serial(
                port=self.address,
                baudrate=config.get("baudrate", 115200),
                timeout=config.get("timeout", 1.0),
            ),
        )
