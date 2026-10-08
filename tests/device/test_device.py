"""Device parameter parsing tests."""

import pytest
from ottu.device import Device, DeviceAccessSerial


def test_parse_device_parses_name():
    """Named device identity is exposed to backend placeholders."""
    assert Device.from_string("name=board-1").backend_variables() == {
        "name": "board-1",
        "device": "board-1",
    }


def test_parse_device_passes_uid_to_access(monkeypatch):
    monkeypatch.setattr(
        "ottu.device.comports",
        lambda: [
            type(
                "Port",
                (),
                {"device": "/dev/ttyUSB0", "serial_number": "abc123"},
            )()
        ],
    )
    device = Device.from_string("name=board-1,uid=abc123,address=/dev/ttyUSB0")

    assert device.access == DeviceAccessSerial(address="/dev/ttyUSB0", uid="abc123")


def test_parse_device_resolves_address_without_storing_parameters():
    """Transport address is owned by the access object, not Device.parameters."""
    device = Device.from_string("name=board-1,address=/dev/ttyUSB0")

    assert device.name == "board-1"
    assert device.access == DeviceAccessSerial(address="/dev/ttyUSB0")
    assert "parameters" not in vars(device)


def test_parse_device_rejects_address_uid_mismatch(monkeypatch):
    monkeypatch.setattr("ottu.device.comports", lambda: [])

    with pytest.raises(ValueError, match="does not match UID"):
        Device.from_string("address=/dev/ttyUSB0,uid=abc123").acquire()


def test_parse_device_parses_bare_device_as_name():
    """A bare device identifier supplies name and device aliases."""
    device = Device.from_string("board-1")

    assert device.backend_variables() == {
        "name": "board-1",
        "device": "board-1",
    }


@pytest.mark.parametrize(
    "port",
    ["/dev/ttyACM0", "/dev/ttyUSB1", "/dev/ttyACM*", "/dev/ttyUSB*", "COM3", "COM*"],
)
def test_parse_device_recognizes_bare_serial_ports(port):
    """Supported bare serial port forms are assigned to the port parameter."""
    device = Device.from_string(port)

    assert device.name is None
    assert device.access == DeviceAccessSerial(address=port)


@pytest.mark.parametrize(
    "device",
    [
        "name=",
        "=board-1",
        "name=one,name=two",
        "name=board-1,invalid",
        "name=board-1,timeout=2",
    ],
)
def test_parse_device_rejects_invalid_parameters(device):
    """Malformed and duplicate device parameters are rejected."""
    with pytest.raises(ValueError, match="(?i)(device parameter|extra inputs)"):
        Device.from_string(device)


def test_load_devices_from_file_resolves_definitions(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ottu.device.comports",
        lambda: [
            type(
                "Port",
                (),
                {
                    "device": "/dev/ttyUSB0",
                    "serial_number": "abc123",
                },
            )()
        ],
    )
    path = tmp_path / "devices.yaml"
    path.write_text(
        "\n".join(
            (
                "version: 1",
                "devices:",
                "  - name: board-1",
                "    uid: abc123",
                "    features:",
                "      - family: xmc",
                '        revision: "3"',
                "    address: /dev/ttyUSB0",
                "  - name: board-2",
                "    uid: def456",
                "    features:",
                "      - wifi",
                "",
            )
        ),
        encoding="utf-8",
    )

    devices = Device.from_file(path)

    assert [device.backend_variables() for device in devices] == [
        {
            "name": "board-1",
            "device": "board-1",
            "address": "/dev/ttyUSB0",
        },
        {"name": "board-2", "device": "board-2"},
    ]
    assert devices[0].features == [{"family": "xmc", "revision": "3"}]
    assert devices[1].features == ["wifi"]
    assert devices[0].access == DeviceAccessSerial(address="/dev/ttyUSB0", uid="abc123")
    assert devices[1].access == DeviceAccessSerial(address="", uid="def456")


def test_device_connect_passes_connection_configuration_to_access():
    configurations = []

    class FakeAccess:
        def connect(self, config):
            configurations.append(config)
            return object()

    device = Device(
        name="board-1",
        access=FakeAccess(),
    )

    assert device.connect() is not None
    assert configurations == [{}]


def test_device_get_returns_runtime_values():
    device = Device(
        name="board-1",
        features=["wifi"],
        access=DeviceAccessSerial(address="/dev/ttyUSB0", uid="abc123"),
    )

    assert device.get("name") == "board-1"
    assert device.get("features") == ["wifi"]
    assert device.get("uid") == "abc123"
    assert device.get("address") == "/dev/ttyUSB0"


def test_device_get_returns_none_without_access():
    device = Device(name="board-1")

    assert device.get("uid") is None
    assert device.get("address") is None


def test_device_get_returns_none_for_unresolved_address():
    device = Device(access=DeviceAccessSerial(address="", uid="abc123"))

    assert device.get("address") is None


def test_device_get_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unsupported device key"):
        Device().get("bogus")


def test_device_is_connected_delegates_to_access():
    class FakeAccess:
        def is_connected(self):
            return True

    assert Device(access=FakeAccess()).is_connected() is True


def test_device_without_access_is_not_connected():
    assert Device(name="board-1").is_connected() is False
