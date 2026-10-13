"""Generic device access tests."""

from ottu.device import DeviceAccess, DeviceAccessSerial


def test_device_access_factory_rejects_unknown_value():
    assert DeviceAccess.from_value("192.168.1.10") is None


def test_device_access_get_address_returns_none_without_address():
    access = DeviceAccessSerial(address="", uid="abc123")

    assert DeviceAccess.get_address(access) is None
