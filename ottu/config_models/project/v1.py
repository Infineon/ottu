"""Pydantic model for version 1 of the ``.ottu`` project file."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DotOttu(BaseModel):
    """Validated contents of version 1 of a ``.ottu`` file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    test_dirs: list[str] = Field(default_factory=lambda: ["test", "tests"])
    test_include_patterns: list[str] = Field(default_factory=lambda: ["**/*"])
    test_exclude_patterns: list[str] = Field(default_factory=list)
    backend: str = Field(min_length=1)


__all__ = ["DotOttu"]
