"""Generic device access tests."""

from ottu.device import DeviceAccess


def test_device_access_factory_rejects_unknown_value():
    assert DeviceAccess.from_value("192.168.1.10") is None
