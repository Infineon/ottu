"""Tests for the ``ottu device`` command group."""

import pytest
import yaml
from click.testing import CliRunner
from ottu.cli import cli

PORTS = [
    type("Port", (), {"device": "/dev/ttyUSB0", "serial_number": "abc123"})(),
    type("Port", (), {"device": "/dev/ttyUSB1", "serial_number": "def456"})(),
]

DEVICE_LIST = """\
version: 1
devices:
  - name: uno
    uid: abc123
    features: [wifi, {family: xmc}]
  - name: nano
    uid: def456
    features: [ble]
  - name: uno
    uid: aaa111
    features: []
"""


@pytest.fixture(autouse=True)
def connected_ports(monkeypatch):
    monkeypatch.setattr("ottu.device.comports", lambda: PORTS)


@pytest.fixture
def dev_list(tmp_path):
    path = tmp_path / "devs.yml"
    path.write_text(DEVICE_LIST, encoding="utf-8")
    return path


def invoke(key, *args):
    return CliRunner().invoke(cli, ["device", "query", key, *args])


def test_device_group_lists_query_subcommand():
    result = CliRunner().invoke(cli, ["device", "--help"])

    assert result.exit_code == 0
    assert "query" in result.output


def test_device_query_prints_uids_of_connected_devices(dev_list):
    result = invoke("uid", "--dev-list", str(dev_list))

    assert result.exit_code == 0
    assert result.output == "abc123\ndef456\n"


def test_device_query_all_prints_unconnected_devices(dev_list):
    result = invoke("uid", "--dev-list", str(dev_list), "--all")

    assert result.exit_code == 0
    assert result.output == "abc123\ndef456\naaa111\n"


def test_device_query_only_connected_is_the_default(dev_list):
    result = invoke("uid", "--dev-list", str(dev_list), "--only-connected")

    assert result.exit_code == 0
    assert result.output == "abc123\ndef456\n"


def test_device_query_filters_by_value(dev_list):
    result = invoke("uid", "--dev-list", str(dev_list), "--filter", "name=uno")

    assert result.exit_code == 0
    assert result.output == "abc123\n"


def test_device_query_matches_any_repeated_filter(dev_list):
    result = invoke(
        "uid", "--dev-list", str(dev_list), "-f", "name=uno", "-f", "name=nano"
    )

    assert result.exit_code == 0
    assert result.output == "abc123\ndef456\n"


def test_device_query_filters_by_feature_containment(dev_list):
    result = invoke("uid", "--dev-list", str(dev_list), "-f", "features=wifi")

    assert result.exit_code == 0
    assert result.output == "abc123\n"


def test_device_query_filters_by_dict_feature(dev_list):
    result = invoke(
        "uid", "--dev-list", str(dev_list), "-f", 'features={"family":"xmc"}'
    )

    assert result.exit_code == 0
    assert result.output == "abc123\n"


def test_device_query_rejects_invalid_json_filter(dev_list):
    result = invoke("uid", "--dev-list", str(dev_list), "-f", "features={family")

    assert result.exit_code == 2
    assert "invalid JSON" in result.output


def test_device_query_prints_requested_key(dev_list):
    result = invoke("address", "--dev-list", str(dev_list))

    assert result.exit_code == 0
    assert result.output == "/dev/ttyUSB0\n/dev/ttyUSB1\n"


def test_device_query_prints_list_values_as_json(dev_list):
    result = invoke("features", "--dev-list", str(dev_list), "-f", "name=uno")

    assert result.exit_code == 0
    assert result.output == '["wifi", {"family": "xmc"}]\n'


def test_device_query_resolves_relative_list_from_working_dir(tmp_path, dev_list):
    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(tmp_path),
            "device",
            "query",
            "uid",
            "--dev-list",
            "devs.yml",
        ],
    )

    assert result.exit_code == 0
    assert result.output == "abc123\ndef456\n"


def test_device_query_requires_dev_list():
    result = invoke("uid")

    assert result.exit_code == 2
    assert "--dev-list" in result.output


def test_device_query_requires_key(dev_list):
    result = CliRunner().invoke(cli, ["device", "query", "--dev-list", str(dev_list)])

    assert result.exit_code == 2
    assert "Missing argument 'KEY'" in result.output


def test_device_query_reports_missing_list(tmp_path):
    result = invoke("uid", "--dev-list", str(tmp_path / "missing.yml"))

    assert result.exit_code != 0
    assert isinstance(result.exception, FileNotFoundError)


def test_device_query_reports_invalid_list(tmp_path):
    path = tmp_path / "devs.yml"
    path.write_text("version: 2\ndevices: []\n", encoding="utf-8")

    result = invoke("uid", "--dev-list", str(path))

    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert "Unsupported device schema version: 2" in str(result.exception)


def test_device_query_reports_malformed_yaml(tmp_path):
    path = tmp_path / "devs.yml"
    path.write_text("version: [1\n", encoding="utf-8")

    result = invoke("uid", "--dev-list", str(path))

    assert result.exit_code != 0
    assert isinstance(result.exception, yaml.YAMLError)


@pytest.mark.parametrize("text", ["name", "name=", "=uno"])
def test_device_query_rejects_malformed_filters(dev_list, text):
    result = invoke("uid", "--dev-list", str(dev_list), "--filter", text)

    assert result.exit_code == 2
    assert "Filters must use key=value format" in result.output


@pytest.mark.parametrize(
    ("key", "args"),
    [("bogus", []), ("uid", ["--filter", "bogus=1"])],
)
def test_device_query_rejects_unknown_keys(dev_list, key, args):
    result = invoke(key, "--dev-list", str(dev_list), *args)

    assert result.exit_code == 2
    assert "Unsupported device key" in result.output
