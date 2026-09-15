"""Device parameter parsing for backend execution."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Protocol, cast

import serial

SerialFactory = Callable[..., Any]


class DeviceConnection(Protocol):
    """Connection interface consumed by device output readers."""

    def readline(self) -> bytes:
        """Read one line from the connected device."""

    def close(self) -> None:
        """Close the device connection."""


class DeviceAccess(Protocol):
    """Factory interface for opening device connections."""

    def connect(self, device: Mapping[str, str]) -> DeviceConnection:
        """Open a connection to a device."""


class SerialDeviceAccess:
    """Open serial connections for devices."""

    def __init__(
        self,
        *,
        serial_factory: SerialFactory = serial.Serial,
        baudrate: int = 115200,
        timeout: float = 1.0,
    ) -> None:
        self._serial_factory = serial_factory
        self._baudrate = baudrate
        self._timeout = timeout

    def connect(self, device: Mapping[str, str]) -> DeviceConnection:
        """Open a serial connection to a device."""
        port = device.get("port")
        if not port:
            raise ValueError("A serial port is required to read test output.")
        return cast(
            DeviceConnection,
            self._serial_factory(
                port=port,
                baudrate=self._baudrate,
                timeout=self._timeout,
            ),
        )


@dataclass(frozen=True)
class Device(Mapping[str, str]):
    """Resolved device parameters supplied to a backend."""

    parameters: dict[str, str]
    access: DeviceAccess = field(default_factory=SerialDeviceAccess, repr=False)

    @classmethod
    def from_string(
        cls,
        device: str,
        *,
        access: DeviceAccess | None = None,
    ) -> "Device":
        """Parse a device name or comma-separated ``key=value`` parameters."""
        access = access or SerialDeviceAccess()
        if "=" not in device:
            if cls._is_port(device):
                return cls({"port": device, "device": device}, access)
            return cls({"name": device, "device": device}, access)

        parameters: dict[str, str] = {}
        for item in device.split(","):
            key, separator, value = item.partition("=")
            key = key.strip()
            value = value.strip()
            if not separator or not key or not value:
                raise ValueError("Device parameters must use key=value format.")
            if key in parameters:
                raise ValueError(
                    f"Device parameter '{key}' was provided more than once."
                )
            parameters[key] = value

        if "name" in parameters:
            parameters.setdefault("device", parameters["name"])
        elif "port" in parameters:
            parameters.setdefault("device", parameters["port"])
        return cls(parameters, access)

    @staticmethod
    def _is_port(value: str) -> bool:
        """Return whether a bare value has a supported serial port format."""
        return any(
            fnmatchcase(value, pattern)
            for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*", "COM*")
        )

    def __getitem__(self, key: str) -> str:
        return self.parameters[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.parameters)

    def __len__(self) -> int:
        return len(self.parameters)

    def connect(self) -> DeviceConnection | None:
        """Open the device connection when this device has one."""
        if "port" not in self:
            return None
        return self.access.connect(self)
