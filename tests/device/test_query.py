"""Device query tests."""

import pytest
from ottu.device import Device, DeviceAccessSerial, DeviceQuery, query

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


def test_query_returns_uids_of_connected_devices(devices):
    assert query(devices, "uid") == ["abc123", "def456"]


def test_query_returns_acquired_addresses(devices):
    assert query(devices, "address") == ["/dev/ttyUSB0", "/dev/ttyUSB1"]


def test_query_filters_by_value(devices):
    assert query(devices, "uid", [{"name": "uno"}]) == ["abc123"]


def test_query_requires_all_keys_in_one_filter(devices):
    filters = [{"name": "uno", "uid": "def456"}]

    assert query(devices, "uid", filters) == []


def test_query_matches_any_filter(devices):
    filters = [{"name": "uno"}, {"name": "nano"}]

    assert query(devices, "name", filters) == ["uno", "nano"]


def test_query_accepts_key_value_string_filters(devices):
    assert query(devices, "uid", ["name=uno"]) == ["abc123"]
    assert query(devices, "name", ["name=uno", "name=nano"]) == ["uno", "nano"]


def test_query_accepts_mixed_string_and_dict_filters(devices):
    assert query(devices, "name", ["name=nano", {"uid": "abc123"}]) == [
        "uno",
        "nano",
    ]


def test_query_string_filter_strips_whitespace_and_keeps_later_equals(devices):
    assert query(devices, "uid", [" name = nano "]) == ["def456"]
    assert query(devices, "uid", ["name=uno,uid=abc123"]) == []


@pytest.mark.parametrize("text", ["name", "name=", "=uno", "", "="])
def test_query_rejects_malformed_string_filters(devices, text):
    with pytest.raises(ValueError, match="key=value format"):
        query(devices, "uid", [text])


def test_query_filters_by_acquired_address(devices):
    assert query(devices, "uid", [{"address": "/dev/ttyUSB1"}]) == ["def456"]


def test_query_filters_by_feature_containment(devices):
    assert query(devices, "uid", [{"features": "wifi"}]) == ["abc123"]
    assert query(devices, "uid", [{"features": {"family": "xmc"}}]) == ["abc123"]
    assert query(devices, "uid", [{"features": {"family": "other"}}]) == []


def test_query_matches_dict_feature_by_subset(devices):
    assert query(devices, "uid", [{"features": {"family": "xmc"}}]) == ["abc123"]
    assert query(devices, "uid", [{"features": {}}]) == ["abc123"]
    assert query(devices, "uid", [{"features": {"missing": "xmc"}}]) == []


def test_query_does_not_match_dict_feature_against_scalar(devices):
    assert query(devices, "uid", [{"features": "xmc"}]) == []


def test_query_reads_json_object_in_string_filter(devices):
    assert query(devices, "uid", ['features={"family": "xmc"}']) == ["abc123"]
    assert query(devices, "uid", ['features={"family": "other"}']) == []


def test_query_reads_json_list_in_string_filter(devices):
    assert query(devices, "uid", ['features=["wifi", {"family": "xmc"}]']) == ["abc123"]
    assert query(devices, "uid", ['features=["wifi", "ble"]']) == []


def test_query_keeps_non_json_values_as_strings(devices):
    assert query(devices, "uid", ["name=uno"]) == ["abc123"]
    assert query(devices, "uid", ["uid=123"]) == []


def test_query_rejects_invalid_json_in_string_filter(devices):
    with pytest.raises(ValueError, match="invalid JSON"):
        query(devices, "uid", ["features={family"])


def test_query_requires_every_listed_feature(devices):
    assert query(devices, "uid", [{"features": ["wifi", {"family": "xmc"}]}]) == [
        "abc123"
    ]
    assert query(devices, "uid", [{"features": ["wifi", "ble"]}]) == []


def test_query_returns_features_per_device(devices):
    assert query(devices, "features", [{"name": "nano"}]) == [["ble"]]


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
        [{"features": "wifi"}],
        check_connected=False,
    ) == ["uno", "virtual"]


def test_query_without_connection_check_keeps_unresolved_address(devices):
    assert query(devices, "address", check_connected=False) == []
    assert query(devices, "uid", check_connected=False) == [
        "abc123",
        "def456",
        "aaa111",
    ]


@pytest.mark.parametrize(
    ("key", "filters"),
    [("bogus", ()), ("uid", [{"bogus": 1}])],
)
def test_query_rejects_unknown_keys(devices, key, filters):
    with pytest.raises(ValueError, match="Unsupported device key"):
        query(devices, key, filters)
