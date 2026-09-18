"""Public project configuration loader."""

from pathlib import Path
from typing import Any

import yaml

from ottu.config_models.project.v1 import DotOttu


class ProjectConfig:
    """Load the versioned project configuration model."""

    @classmethod
    def default(cls) -> DotOttu:
        """Return the configuration used when no project file exists."""
        return DotOttu(version=1, backend="debug")

    @classmethod
    def from_file(cls, path: str | Path) -> DotOttu:
        """Load and validate a ``.ottu`` file."""
        with Path(path).open(encoding="utf-8") as config_file:
            values: dict[str, Any] = yaml.safe_load(config_file)

        version = values.get("version")
        if type(version) is not int:
            raise ValueError(f"Unsupported .ottu schema version: {version}")
        models: dict[int, type[DotOttu]] = {1: DotOttu}
        try:
            model = models[version]
        except KeyError as error:
            raise ValueError(f"Unsupported .ottu schema version: {version}") from error
        return model.model_validate(values)

    @classmethod
    def from_project_root(cls, project_root: str | Path | None) -> DotOttu:
        """Load the project configuration or return the default model."""
        if project_root is not None:
            ottu_file = Path(project_root) / ".ottu"
            if ottu_file.is_file():
                return cls.from_file(ottu_file)
        return cls.default()


__all__ = ["ProjectConfig"]
