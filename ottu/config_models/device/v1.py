"""Pydantic models for version 1 of the device list file."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class DeviceDefinition(BaseModel):
    """A device entry from a version 1 device list."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    uid: str
    features: list[str | int | float | bool | None | dict[str, Any]]
    address: str | None = None


class DeviceList(BaseModel):
    """Validated contents of version 1 of a device list file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    devices: list[DeviceDefinition]


__all__ = ["DeviceDefinition", "DeviceList"]
