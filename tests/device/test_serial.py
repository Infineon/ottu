"""Serial device access tests."""

import pytest
from ottu.device import DeviceAccess, DeviceAccessSerial


class FakeSerial:
    def __init__(self, lines):
        self.lines = iter(lines)

    def readline(self):
        return next(self.lines, b"")

    def close(self):
        pass


def test_serial_device_access_connects_to_serial_port(monkeypatch):
    connection = FakeSerial([])
    calls = []

    def serial_constructor(**kwargs):
        calls.append(kwargs)
        return connection

    monkeypatch.setattr("ottu.device.serial.Serial", serial_constructor)
    result = DeviceAccessSerial(address="/dev/ttyUSB0").connect({})

    assert result is connection
    assert calls == [{"port": "/dev/ttyUSB0", "baudrate": 115200, "timeout": 1.0}]


def test_serial_device_access_uses_connection_configuration(monkeypatch):
    calls = []

    def serial_constructor(**kwargs):
        calls.append(kwargs)
        return FakeSerial([])

    monkeypatch.setattr("ottu.device.serial.Serial", serial_constructor)
    DeviceAccessSerial(address="/dev/ttyUSB0").connect(
        {"address": "/dev/ttyUSB1", "baudrate": 57600, "timeout": 2.5}
    )

    assert calls == [{"port": "/dev/ttyUSB0", "baudrate": 57600, "timeout": 2.5}]


def test_device_access_serial_getters(monkeypatch):
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
    access = DeviceAccessSerial(address="/dev/ttyUSB0", uid="abc123")

    assert access.get_address() == "/dev/ttyUSB0"
    assert access.get_uid() == "abc123"


def test_device_access_factory_resolves_serial_port():
    access = DeviceAccess.from_value("/dev/ttyUSB0")

    assert access == DeviceAccessSerial(address="/dev/ttyUSB0")


def test_device_access_factory_resolves_serial_uid(monkeypatch):
    ports = [
        type("Port", (), {"device": "/dev/ttyUSB0", "serial_number": "123123AFDFE"})(),
    ]
    monkeypatch.setattr("ottu.device.comports", lambda: ports)

    access = DeviceAccess.from_value("123123AFDFE")

    assert access == DeviceAccessSerial(address="", uid="123123AFDFE")
    assert access.acquire() == DeviceAccessSerial(
        address="/dev/ttyUSB0", uid="123123AFDFE"
    )


def test_device_access_serial_creates_access_from_uid(monkeypatch):
    ports = [
        type("Port", (), {"device": "/dev/ttyUSB0", "serial_number": "abc123"})(),
        type("Port", (), {"device": "/dev/ttyUSB1", "serial_number": "def456"})(),
    ]
    monkeypatch.setattr("ottu.device.comports", lambda: ports)

    access = DeviceAccessSerial.from_uid("def456")

    assert access is not None
    assert access.get_address() == "/dev/ttyUSB1"
    assert access.get_uid() == "def456"
    assert DeviceAccessSerial.from_uid("missing") is None


def test_device_access_serial_requires_address_or_uid():
    with pytest.raises(ValueError, match="address or UID is required"):
        DeviceAccessSerial(address="").acquire()


def test_device_access_serial_reports_missing_uid(monkeypatch):
    monkeypatch.setattr("ottu.device.comports", lambda: [])

    with pytest.raises(LookupError, match="was not found"):
        DeviceAccessSerial(address="", uid="abc123").acquire()


def test_device_access_serial_acquires_address_without_uid():
    access = DeviceAccessSerial(address="/dev/ttyUSB0")

    assert access.acquire() is access


def test_device_access_serial_acquires_matching_address_and_uid(monkeypatch):
    ports = [
        type("Port", (), {"device": "/dev/ttyUSB0", "serial_number": "abc123"})(),
    ]
    monkeypatch.setattr("ottu.device.comports", lambda: ports)
    access = DeviceAccessSerial(address="/dev/ttyUSB0", uid="abc123")

    assert access.acquire() is access


def test_device_access_serial_scans_and_filters_ports(monkeypatch):
    ports = [
        type(
            "Port",
            (),
            {"device": "/dev/ttyUSB0", "serial_number": "abc123", "vid": 1},
        )(),
        type(
            "Port",
            (),
            {"device": "/dev/ttyUSB1", "serial_number": "def456", "vid": 2},
        )(),
    ]
    monkeypatch.setattr("ottu.device.comports", lambda: ports)

    all_access = DeviceAccessSerial.scan()
    filtered_access = DeviceAccessSerial.scan("vid", 2)

    assert [access.get_address() for access in all_access] == [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
    ]
    assert [access.get_uid() for access in filtered_access] == ["def456"]


def test_serial_access_requires_a_serial_port():
    with pytest.raises(ValueError, match="serial address is required"):
        DeviceAccessSerial(address="").connect({"name": "board"})


def test_serial_access_rejects_unsupported_address():
    with pytest.raises(ValueError, match="Unsupported serial address"):
        DeviceAccessSerial(address="not-a-serial-port")


def test_serial_access_rejects_invalid_uid():
    with pytest.raises(ValueError, match="Invalid serial UID"):
        DeviceAccessSerial(address="/dev/ttyUSB0", uid="not-hex")


def test_serial_access_rejects_address_uid_mismatch(monkeypatch):
    ports = [
        type("Port", (), {"device": "/dev/ttyUSB0", "serial_number": "abc123"})(),
    ]
    monkeypatch.setattr("ottu.device.comports", lambda: ports)

    with pytest.raises(ValueError, match="does not match UID"):
        DeviceAccessSerial(address="/dev/ttyUSB0", uid="def456").acquire()


@pytest.mark.parametrize(
    ("address", "uid", "expected"),
    [
        ("/dev/ttyUSB0", None, True),
        ("/dev/ttyUSB9", None, False),
        ("", "abc123", True),
        ("", "def456", False),
        ("/dev/ttyUSB0", "abc123", True),
        ("/dev/ttyUSB0", "def456", False),
        ("", None, False),
    ],
)
def test_device_access_serial_is_connected(monkeypatch, address, uid, expected):
    ports = [
        type("Port", (), {"device": "/dev/ttyUSB0", "serial_number": "abc123"})(),
    ]
    monkeypatch.setattr("ottu.device.comports", lambda: ports)

    assert DeviceAccessSerial(address=address, uid=uid).is_connected() is expected
