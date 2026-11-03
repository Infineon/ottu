"""Device query tests."""

import pytest
from ottu.device import Device, DeviceAccessSerial, DeviceInput, DeviceQuery, query

PORTS = [
    type("Port", (), {"device": "/dev/ttyUSB0", "serial_number": "abc123"})(),
    type("Port", (), {"device": "/dev/ttyUSB1", "serial_number": "def456"})(),
]


@pytest.fixture(autouse=True)
def connected_ports(monkeypatch):
    monkeypatch.setattr("ottu.device.comports", lambda: PORTS)


def make_device(name, uid, features=(), address=""):
    return Device(
        name=name,
        features=list(features),
        access=DeviceAccessSerial(address=address, uid=uid),
    )


@pytest.fixture
def devices():
    return [
        make_device("uno", "abc123", ["wifi", {"family": "xmc"}]),
        make_device("nano", "def456", ["ble"]),
        make_device("uno", "aaa111"),
    ]


def test_query_alias_is_select():
    assert query == DeviceQuery.select


def test_find_rejects_non_positive_limit(devices):
    with pytest.raises(ValueError, match="limit must be positive"):
        DeviceQuery.find(devices, limit=0)


def test_find_stops_after_limit(devices):
    assert DeviceQuery.find(devices, check_connected=False, limit=1) == [devices[0]]


def test_find_rejects_string_filters(devices):
    with pytest.raises(TypeError, match="DeviceInput values"):
        DeviceQuery.find(devices, "uno")


def test_find_matches_device_input_identity(devices):
    assert DeviceQuery.find(
        devices, [DeviceInput(identifier="uno")], check_connected=False
    ) == [devices[0], devices[2]]
    assert DeviceQuery.find(
        devices, [DeviceInput(identifier="abc123")], check_connected=False
    ) == [devices[0]]
    assert DeviceQuery.find(
        devices, [DeviceInput(identifier="/dev/ttyUSB1")], check_connected=False
    ) == [devices[1]]


def test_find_combines_fields_and_identifier(devices):
    device_input = DeviceInput(identifier="uno", features=["wifi"])

    assert DeviceQuery.find(devices, [device_input], check_connected=False) == [
        devices[0]
    ]


def test_find_returns_no_matches_when_identity_conflicts_with_fields(devices):
    device_input = DeviceInput(identifier="uno", name="nano")

    assert DeviceQuery.find(devices, [device_input], check_connected=False) == []


def test_find_matches_any_input_in_device_order(devices):
    filters = [DeviceInput(name="uno"), DeviceInput(identifier="nano")]

    assert DeviceQuery.find(devices, filters, check_connected=False) == devices


def test_find_rejects_mapping_filters(devices):
    with pytest.raises(TypeError, match="Device queries require DeviceInput values"):
        DeviceQuery.find(devices, {"name": "nano"})


def test_query_returns_values_for_connected_devices(devices):
    assert query(devices, "uid") == ["abc123", "def456"]
    assert query(devices, "address") == ["/dev/ttyUSB0", "/dev/ttyUSB1"]


def test_query_filters_by_device_input(devices):
    assert query(devices, "uid", [DeviceInput(name="uno")]) == ["abc123"]


def test_query_requires_all_fields_in_one_input(devices):
    device_input = DeviceInput(name="uno", uid="def456")

    assert query(devices, "uid", [device_input]) == []


def test_query_matches_any_input(devices):
    filters = [DeviceInput(name="uno"), DeviceInput(name="nano")]

    assert query(devices, "name", filters) == ["uno", "nano"]


def test_query_filters_by_known_address(devices):
    assert query(devices, "uid", [DeviceInput(address="/dev/ttyUSB1")]) == ["def456"]


def test_query_filters_by_feature_containment(devices):
    assert query(devices, "uid", [DeviceInput(features=["wifi"])]) == ["abc123"]
    assert query(devices, "uid", [DeviceInput(features=[{"family": "xmc"}])]) == [
        "abc123"
    ]
    assert query(devices, "uid", [DeviceInput(features=[{"family": "other"}])]) == []


def test_query_matches_dict_feature_by_subset(devices):
    assert query(devices, "uid", [DeviceInput(features=[{"family": "xmc"}])]) == [
        "abc123"
    ]
    assert query(devices, "uid", [DeviceInput(features=[{}])]) == ["abc123"]
    assert query(devices, "uid", [DeviceInput(features=[{"missing": "xmc"}])]) == []


def test_query_does_not_match_dict_feature_against_scalar(devices):
    assert query(devices, "uid", [DeviceInput(features=["xmc"])]) == []


def test_query_requires_every_listed_feature(devices):
    assert query(
        devices, "uid", [DeviceInput(features=["wifi", {"family": "xmc"}])]
    ) == ["abc123"]
    assert query(devices, "uid", [DeviceInput(features=["wifi", "ble"])]) == []


def test_query_returns_features_per_device(devices):
    assert query(devices, "features", [DeviceInput(name="nano")]) == [["ble"]]


def test_query_skips_devices_without_a_value():
    nameless = Device(access=DeviceAccessSerial(address="", uid="abc123"))

    assert query([nameless], "name") == []
    assert query([nameless], "uid") == ["abc123"]


def test_query_skips_devices_without_access():
    assert query([Device(name="virtual")], "name") == []


def test_query_skips_unplugged_address_only_devices():
    unplugged = Device(
        name="uno",
        access=DeviceAccessSerial(address="/dev/ttyUSB9"),
    )

    assert query([unplugged], "name") == []


def test_query_skips_mismatched_address_and_uid():
    mismatched = Device(
        name="uno",
        access=DeviceAccessSerial(address="/dev/ttyUSB0", uid="def456"),
    )

    assert query([mismatched], "name") == []


def test_query_without_connection_check_uses_definitions(monkeypatch, devices):
    def fail():
        raise AssertionError("hardware must not be queried")

    monkeypatch.setattr("ottu.device.comports", fail)
    virtual = Device(name="virtual", features=["wifi"])

    assert query([*devices, virtual], "name", check_connected=False) == [
        "uno",
        "nano",
        "uno",
        "virtual",
    ]
    assert query(
        [*devices, virtual],
        "name",
        [DeviceInput(features=["wifi"])],
        check_connected=False,
    ) == ["uno", "virtual"]


def test_query_without_connection_check_resolves_known_address(devices):
    assert query(devices, "address", check_connected=False) == [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
    ]
    assert query(devices, "uid", check_connected=False) == [
        "abc123",
        "def456",
        "aaa111",
    ]


def test_query_rejects_unknown_key(devices):
    with pytest.raises(ValueError, match="Unsupported device key"):
        query(devices, "bogus")
