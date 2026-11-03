"""Tests for device list loading and validation."""

import pytest
from ottu.device.device import DeviceDefinition, DeviceList
from pydantic import ValidationError


def test_device_list_validates_yaml_values():
    device_list = DeviceList.model_validate(
        {
            "version": 1,
            "devices": [
                {
                    "name": "board-1",
                    "uid": "abc123",
                    "features": [
                        "scalar",
                        {"family": "xmc", "revision": "3", "optional": None},
                    ],
                    "address": "/dev/ttyUSB0",
                }
            ],
        }
    )

    assert device_list.devices == [
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


def test_device_definition_features_default_to_empty_list():
    device = DeviceDefinition.model_validate({"name": "board-1", "uid": "abc123"})

    assert device.features == []


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
        ({"version": 1, "devices": [{"name": "board"}]}, "missing"),
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


@pytest.mark.parametrize("version", [2, "1"])
def test_device_list_rejects_unsupported_version(version):
    with pytest.raises(ValidationError):
        DeviceList.model_validate({"version": version, "devices": []})
