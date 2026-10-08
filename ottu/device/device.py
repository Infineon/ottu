"""Runtime device parsing and acquisition."""

from dataclasses import dataclass, field
from typing import Any

from ottu.config_models.device.device import DeviceConfig
from ottu.config_models.device.v1 import DeviceDefinition

from .access import DeviceAccess, DeviceConnection


@dataclass(frozen=True)
class Device:
    """Resolved device identity supplied to a backend."""

    name: str | None = None
    features: list[str | int | float | bool | None | dict[str, Any]] = field(
        default_factory=list
    )
    access: DeviceAccess | None = field(default=None, repr=False)

    @classmethod
    def from_string(cls, device: str) -> "Device":
        """Parse a device name or comma-separated ``key=value`` parameters."""
        if "=" not in device:
            return cls._from_bare_string(device)
        return cls._from_key_value_string(device)

    @classmethod
    def _from_bare_string(cls, device: str) -> "Device":
        access = DeviceAccess.from_value(device)
        if access is not None:
            return cls(access=access)
        return cls(name=device)

    @classmethod
    def _from_key_value_string(cls, device: str) -> "Device":
        values: dict[str, str] = {}
        for item in device.split(","):
            key, separator, item_value = item.partition("=")
            key = key.strip()
            item_value = item_value.strip()
            if not separator or not key or not item_value:
                raise ValueError("Device parameters must use key=value format.")
            if key in values:
                raise ValueError(f"Device parameter '{key}' was provided twice.")
            field = DeviceDefinition.model_fields.get(key)
            if field is None or key == "features":
                raise ValueError(f"Unsupported device parameter '{key}'.")
            values[key] = item_value

        return cls(
            name=values.get("name"),
            access=cls._resolve_access(values.get("address"), values.get("uid")),
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
    def from_file(cls, devs_file: str) -> list["Device"]:
        """Load device definitions and resolve them into runtime devices."""
        return [
            cls.from_definition(definition)
            for definition in DeviceConfig.from_file(devs_file)
        ]

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

    def backend_variables(self) -> dict[str, str]:
        """Return device values used to render backend command placeholders."""
        values: dict[str, str] = {}
        if self.name is not None:
            values["name"] = self.name
            values["device"] = self.name
        if self.access is not None and self.access.get_address():
            values["address"] = self.access.get_address()
        return values

    def connect(self) -> DeviceConnection | None:
        """Open the device connection when this device has one."""
        if self.access is None:
            return None
        return self.access.connect({})
