"""Project configuration loaded from the ``.ottu`` file."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectConfig(BaseModel):
    """Validated contents of a ``.ottu`` project file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    test_dirs: list[str] = Field(default_factory=lambda: ["test", "tests"])
    test_include_patterns: list[str] = Field(default_factory=lambda: ["**/*"])
    test_exclude_patterns: list[str] = Field(default_factory=list)
    backend: str = Field(min_length=1)

    @field_validator("version", mode="before")
    @classmethod
    def _require_supported_version(cls, value: Any) -> Any:
        """Reject any version other than the integer 1 with a clear message."""
        if type(value) is not int or value != 1:
            raise ValueError(f"Unsupported .ottu schema version: {value}")
        return value

    @classmethod
    def default(cls) -> "ProjectConfig":
        """Return the configuration used when no project file exists."""
        return cls(version=1, backend="debug")

    @classmethod
    def from_file(cls, path: str | Path) -> "ProjectConfig":
        """Load and validate a ``.ottu`` file."""
        with Path(path).open(encoding="utf-8") as config_file:
            return cls.model_validate(yaml.safe_load(config_file))

    @classmethod
    def from_project_root(cls, project_root: str | Path | None) -> "ProjectConfig":
        """Load the project configuration or return the default model."""
        if project_root is not None:
            ottu_file = Path(project_root) / ".ottu"
            if ottu_file.is_file():
                return cls.from_file(ottu_file)
        return cls.default()
