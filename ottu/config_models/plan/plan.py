"""Public test plan loader."""

from pathlib import Path
from typing import Any

import yaml

from ottu.config_models.plan.v1 import Plan, RoleTest, SuiteDefinition


class PlanConfig:
    """Load the versioned test plan model."""

    @classmethod
    def from_file(cls, path: str | Path) -> Plan:
        """Load and validate a test plan file."""
        with Path(path).open(encoding="utf-8") as config_file:
            values: dict[str, Any] = yaml.safe_load(config_file)

        version = values.get("version")
        if type(version) is not int:
            raise ValueError(f"Unsupported plan schema version: {version}")
        models: dict[int, type[Plan]] = {1: Plan}
        try:
            model = models[version]
        except KeyError as error:
            raise ValueError(f"Unsupported plan schema version: {version}") from error
        return model.model_validate(values)


__all__ = ["Plan", "PlanConfig", "RoleTest", "SuiteDefinition"]
