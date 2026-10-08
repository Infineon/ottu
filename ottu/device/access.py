"""Device access contracts and connection types."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

ConnectionConfig = Mapping[str, Any]


class DeviceConnection(Protocol):
    """Connection interface consumed by device output readers."""

    def readline(self) -> bytes:
        """Read one line from the connected device."""

    def close(self) -> None:
        """Close the device connection."""


@dataclass
class DeviceAccess(ABC):
    """Base class for transport-specific device access."""

    address: str
    uid: str | None = None

    def __post_init__(self) -> None:
        self._validate()

    def get_address(self) -> str:
        return self.address

    def get_uid(self) -> str | None:
        return self.uid

    @classmethod
    def from_value(cls, value: str) -> "DeviceAccess | None":
        """Create the access type matching an input value."""
        for access_type in cls.__subclasses__():
            access = access_type._from_value(value)
            if access is not None:
                return access
        return None

    @abstractmethod
    def acquire(self) -> "DeviceAccess":
        """Resolve and validate hardware-backed access."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether the described hardware is currently present."""

    @abstractmethod
    def connect(self, config: ConnectionConfig) -> DeviceConnection:
        """Open a connection using transport-specific configuration."""

    @classmethod
    @abstractmethod
    def _from_value(cls, value: str) -> "DeviceAccess | None":
        """Resolve an input value for this access type."""

    @abstractmethod
    def _validate(self) -> None:
        """Validate the access object's address and optional UID."""
