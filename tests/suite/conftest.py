import pytest
from ottu.device import Device


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected", lambda self: True
    )


@pytest.fixture
def fake_devices_connected(monkeypatch):
    """Treat devices without hardware access as connected; check real ones."""
    is_connected = Device.is_connected
    monkeypatch.setattr(
        Device,
        "is_connected",
        lambda self: self.access is None or is_connected(self),
    )
