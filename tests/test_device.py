"""Device parameter parsing tests."""

import pytest
from ottu.device import Device


def test_parse_device_parses_name_and_parameters():
    """Named device parameters are returned for backend placeholders."""
    assert dict(Device.from_string("name=board-1,port=/dev/ttyUSB0")) == {
        "name": "board-1",
        "port": "/dev/ttyUSB0",
        "device": "board-1",
    }


def test_parse_device_preserves_parameter_only_device():
    """Parameter-only devices do not invent a name."""
    assert dict(Device.from_string("port=/dev/ttyUSB0,baud=9600")) == {
        "port": "/dev/ttyUSB0",
        "baud": "9600",
        "device": "/dev/ttyUSB0",
    }


def test_parse_device_parses_bare_device_as_name():
    """A bare device identifier supplies name and device aliases."""
    device = Device.from_string("board-1")

    assert dict(device) == {
        "name": "board-1",
        "device": "board-1",
    }
    assert len(device) == 2


@pytest.mark.parametrize(
    "port",
    ["/dev/ttyACM0", "/dev/ttyUSB1", "/dev/ttyACM*", "/dev/ttyUSB*", "COM3", "COM*"],
)
def test_parse_device_recognizes_bare_serial_ports(port):
    """Supported bare serial port forms are assigned to the port parameter."""
    assert dict(Device.from_string(port)) == {
        "port": port,
        "device": port,
    }


@pytest.mark.parametrize(
    "device",
    ["name=", "=board-1", "name=one,name=two", "name=board-1,invalid"],
)
def test_parse_device_rejects_invalid_parameters(device):
    """Malformed and duplicate device parameters are rejected."""
    with pytest.raises(ValueError, match="Device parameter"):
        Device.from_string(device)
