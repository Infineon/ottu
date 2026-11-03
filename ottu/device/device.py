"""Runtime device parsing and acquisition."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .access import DeviceAccess, DeviceConnection


class DeviceDefinition(BaseModel):
    """A device entry from a version 1 device list."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    uid: str
    features: list[str | int | float | bool | None | dict[str, Any]] = Field(
        default_factory=list
    )
    address: str | None = None


class DeviceList(BaseModel):
    """Validated contents of a version 1 device list."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    devices: list[DeviceDefinition]


class DeviceInput(BaseModel):
    """The values a device must have.

    Every value is optional. ``identifier`` holds a bare value, which may be a
    name, a UID or an address, as it is not known which one it is.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    identifier: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    uid: str | None = Field(default=None, min_length=1)
    features: list[str | int | float | bool | None | dict[str, Any]] = Field(
        default_factory=list
    )
    address: str | None = Field(default=None, min_length=1)


@dataclass(frozen=True)
class Device:
    """Resolved device identity supplied to a backend."""

    name: str | None = None
    features: list[str | int | float | bool | None | dict[str, Any]] = field(
        default_factory=list
    )
    access: DeviceAccess | None = field(default=None, repr=False)

    @classmethod
    def from_input(cls, device_input: DeviceInput) -> "Device":
        """Resolve a modeled device input into a runtime device."""
        name = device_input.name
        access_input = device_input.address is not None or device_input.uid is not None
        access = (
            cls._resolve_access(device_input.address, device_input.uid)
            if access_input
            else None
        )
        if device_input.identifier is not None:
            identifier_access = DeviceAccess.from_value(device_input.identifier)
            if not access_input:
                access = identifier_access
            if name is None and identifier_access is None:
                name = device_input.identifier
        return cls(
            name=name,
            features=device_input.features,
            access=access,
        )

    @staticmethod
    def _resolve_access(address: str | None, uid: str | None) -> DeviceAccess | None:
        if address is None:
            return DeviceAccess.from_value(uid) if uid is not None else None
        access = DeviceAccess.from_value(address)
        if access is None or uid is None:
            return access
        return type(access)(address=access.address, uid=uid)

    def acquire(self) -> "Device":
        """Resolve and validate this device's hardware access."""
        if self.access is None:
            return self
        return type(self)(
            name=self.name,
            features=self.features,
            access=self.access.acquire(),
        )

    def is_connected(self) -> bool:
        """Return whether this device's hardware is currently present."""
        return self.access is not None and self.access.is_connected()

    @classmethod
    def from_file(cls, devs_file: str | Path) -> list["Device"]:
        """Load device definitions and resolve them into runtime devices."""
        with Path(devs_file).open(encoding="utf-8") as config_file:
            device_list = DeviceList.model_validate(yaml.safe_load(config_file))
        return [cls.from_definition(definition) for definition in device_list.devices]

    @classmethod
    def from_definition(cls, definition: DeviceDefinition) -> "Device":
        """Resolve one declarative device definition into a runtime device."""
        return cls(
            name=definition.name,
            features=definition.features,
            access=cls._resolve_access(definition.address, definition.uid),
        )

    @staticmethod
    def validate_key(key: str) -> None:
        """Reject keys that are not device definition fields."""
        if key not in DeviceDefinition.model_fields:
            raise ValueError(f"Unsupported device key '{key}'.")

    def get(self, key: str) -> Any:
        """Return the runtime value of a device definition key."""
        self.validate_key(key)
        if key == "uid":
            return self.access.get_uid() if self.access else None
        if key == "address":
            return (self.access.get_address() if self.access else None) or None
        return getattr(self, key)

    def identity_filters(self) -> tuple[dict[str, Any], ...]:
        """Return filters for the non-null identity values of this device."""
        return tuple(
            {key: value}
            for key in ("name", "uid", "address")
            if (value := self.get(key)) is not None
        )

    def backend_variables(self) -> dict[str, str]:
        """Return device values used to render backend command placeholders."""
        values: dict[str, str] = {}
        if self.name is not None:
            values["name"] = self.name
            values["device"] = self.name
        if self.access is not None:
            address = self.access.get_address()
            if address:
                values["address"] = address
        return values

    def connect(self) -> DeviceConnection | None:
        """Open the device connection when this device has one."""
        if self.access is None:
            return None
        return self.access.connect({})
