"""Tests for project configuration loading and validation."""

import pytest
from ottu.config_models.project.config import ProjectConfig
from ottu.config_models.project.v1 import DotOttu
from pydantic import ValidationError


def test_project_config_loads_yaml(tmp_path):
    path = tmp_path / ".ottu"
    (tmp_path / "tests").mkdir()
    path.write_text(
        """version: 1

test_dirs:
    - tests
test_include_patterns:
  - "**/*.ino"
test_exclude_patterns:
  - "*.exp"
backend: arduino-cli
""",
        encoding="utf-8",
    )

    config = ProjectConfig.from_file(path)

    assert config.version == 1
    assert config.test_dirs == ["tests"]
    assert config.test_include_patterns == ["**/*.ino"]
    assert config.test_exclude_patterns == ["*.exp"]
    assert config.backend == "arduino-cli"


@pytest.mark.parametrize(
    ("mapping", "error_type"),
    [
        ({}, "missing"),
        (
            {
                "version": 9,
                "test_dirs": ["tests"],
                "test_include_patterns": ["**/*.ino"],
                "test_exclude_patterns": [],
                "backend": "arduino-cli",
            },
            "literal_error",
        ),
        (
            {"version": 1, "unexpected": True},
            "extra_forbidden",
        ),
        ([], "model_type"),
    ],
)
def test_project_config_rejects_invalid_mapping(mapping, error_type):
    with pytest.raises(ValidationError) as error:
        DotOttu.model_validate(mapping)
    assert any(item["type"] == error_type for item in error.value.errors())


def test_project_config_rejects_non_string_patterns():
    value = {
        "version": 1,
        "test_dirs": ["tests"],
        "test_include_patterns": ["**/*.ino", 3],
        "test_exclude_patterns": [],
        "backend": "arduino-cli",
    }

    with pytest.raises(ValidationError, match="test_include_patterns"):
        DotOttu.model_validate(value)


def test_project_config_defaults_test_exclude_patterns():
    config = DotOttu.model_validate(
        {
            "version": 1,
            "test_dirs": ["tests"],
            "test_include_patterns": ["**/*.ino"],
            "backend": "debug",
        }
    )

    assert config.test_exclude_patterns == []


def test_project_config_defaults_without_project_file():
    config = ProjectConfig.default()

    assert config.version == 1
    assert config.test_dirs == ["test", "tests"]
    assert config.test_include_patterns == ["**/*"]
    assert config.test_exclude_patterns == []
    assert config.backend == "debug"


def test_project_config_from_project_root_loads_existing_file(tmp_path):
    (tmp_path / ".ottu").write_text(
        "version: 1\nbackend: arduino-cli\n",
        encoding="utf-8",
    )

    config = ProjectConfig.from_project_root(tmp_path)

    assert config.backend == "arduino-cli"


def test_project_config_from_project_root_uses_default_when_file_is_missing(tmp_path):
    config = ProjectConfig.from_project_root(tmp_path)

    assert config == ProjectConfig.default()


def test_project_config_rejects_unsupported_version(tmp_path):
    path = tmp_path / ".ottu"
    path.write_text("version: 2\nbackend: debug\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported .ottu schema version: 2"):
        ProjectConfig.from_file(path)


def test_project_config_accepts_missing_test_directory(tmp_path):
    path = tmp_path / ".ottu"
    path.write_text(
        """version: 1
test_dirs: [tests]
test_include_patterns: ["**/*.ino"]
test_exclude_patterns: []
backend: arduino-cli
""",
        encoding="utf-8",
    )

    config = ProjectConfig.from_file(path)

    assert config.test_dirs == ["tests"]


def test_project_config_accepts_whitespace_exclusion(tmp_path):
    path = tmp_path / ".ottu"
    (tmp_path / "tests").mkdir()
    path.write_text(
        """version: 1
test_dirs: [tests]
test_include_patterns: ["**/*.ino"]
test_exclude_patterns: [" "]
backend: arduino-cli
""",
        encoding="utf-8",
    )

    config = ProjectConfig.from_file(path)

    assert config.test_exclude_patterns == [" "]
