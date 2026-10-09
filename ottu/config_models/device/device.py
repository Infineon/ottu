"""Public device list configuration loader."""

from pathlib import Path
from typing import Any

import yaml

from ottu.config_models.device.v1 import DeviceDefinition, DeviceList


class DeviceConfig:
    """Load the versioned device list model."""

    @classmethod
    def from_file(cls, path: str | Path) -> list[DeviceDefinition]:
        """Load a device list file and return its device definitions."""
        with Path(path).open(encoding="utf-8") as config_file:
            values: dict[str, Any] = yaml.safe_load(config_file)

        version = values.get("version")
        if type(version) is not int:
            raise ValueError(f"Unsupported device schema version: {version}")
        models: dict[int, type[DeviceList]] = {1: DeviceList}
        try:
            model = models[version]
        except KeyError as error:
            raise ValueError(f"Unsupported device schema version: {version}") from error
        return model.model_validate(values).devices


__all__ = ["DeviceConfig", "DeviceDefinition"]
