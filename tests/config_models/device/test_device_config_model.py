"""Tests for device list loading and validation."""

import pytest
from ottu.config_models.device.device import DeviceConfig
from ottu.config_models.device.v1 import DeviceDefinition, DeviceList
from pydantic import ValidationError


def test_device_config_loads_yaml(tmp_path):
    path = tmp_path / "devices.yaml"
    path.write_text(
        "\n".join(
            (
                "version: 1",
                "devices:",
                "  - name: board-1",
                "    uid: abc123",
                "    features:",
                "      - scalar",
                "      - family: xmc",
                '        revision: "3"',
                "        optional:",
                "    address: /dev/ttyUSB0",
                "",
            )
        ),
        encoding="utf-8",
    )

    config = DeviceConfig.from_file(path)

    assert config == [
        DeviceDefinition(
            name="board-1",
            uid="abc123",
            features=[
                "scalar",
                {"family": "xmc", "revision": "3", "optional": None},
            ],
            address="/dev/ttyUSB0",
        )
    ]


def test_device_definition_address_defaults_to_none():
    device = DeviceDefinition.model_validate(
        {"name": "board-1", "uid": "abc123", "features": []}
    )

    assert device.address is None


def test_device_definition_accepts_yaml_mappings():
    device = DeviceDefinition.model_validate(
        {
            "name": "board-1",
            "uid": "abc123",
            "features": [
                "scalar",
                {"family": "xmc", "revision": "3", "optional": None},
            ],
        }
    )

    assert device.features == [
        "scalar",
        {"family": "xmc", "revision": "3", "optional": None},
    ]


@pytest.mark.parametrize(
    ("mapping", "error_type"),
    [
        ({}, "missing"),
        ({"version": 1, "devices": [{"name": "board", "uid": "id"}]}, "missing"),
        ({"version": 1, "devices": [], "unexpected": True}, "extra_forbidden"),
        (
            {
                "version": 1,
                "devices": [
                    {
                        "name": "board",
                        "uid": "id",
                        "features": [],
                        "unexpected": True,
                    }
                ],
            },
            "extra_forbidden",
        ),
    ],
)
def test_device_list_rejects_invalid_mapping(mapping, error_type):
    with pytest.raises(ValidationError) as error:
        DeviceList.model_validate(mapping)
    assert any(item["type"] == error_type for item in error.value.errors())


def test_device_config_rejects_unsupported_version(tmp_path):
    path = tmp_path / "devices.yaml"
    path.write_text("version: 2\ndevices: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported device schema version: 2"):
        DeviceConfig.from_file(path)


def test_device_config_rejects_non_integer_version(tmp_path):
    path = tmp_path / "devices.yaml"
    path.write_text("version: '1'\ndevices: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported device schema version: 1"):
        DeviceConfig.from_file(path)
