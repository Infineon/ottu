"""Tests for parsing argument and option strings."""

import click
import pytest
from ottu.cli.parse import parse_device_input, parse_mapping, parse_test_path_input


def test_parse_mapping_splits_json_pairs_outside_escaped_quoted_values():
    value = r'features=["a\"b,c"],name=board'

    assert parse_mapping(value, json_values=True) == {
        "features": ['a"b,c'],
        "name": "board",
    }


def test_parse_test_path_input_reports_model_errors_as_bad_parameters(monkeypatch):
    monkeypatch.setattr("ottu.cli.parse.parse_mapping", lambda value: {"": "a.py"})

    with pytest.raises(click.BadParameter):
        parse_test_path_input("ignored")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("tests/a.py", {None: "tests/a.py"}),
        ("a,b.py", {None: "a,b.py"}),
        (" tests ", {None: "tests"}),
        ("server=server.py", {"server": "server.py"}),
        ("role=server,name=board-1", {"role": "server", "name": "board-1"}),
        (" role = server , name = a=b ", {"role": "server", "name": "a=b"}),
    ],
)
def test_parse_mapping_builds_a_mapping(value, expected):
    assert parse_mapping(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "  ", "=a.py", "server=", "a=1,b", "a=1,,b=2", "a=1,a=2"],
)
def test_parse_mapping_rejects_malformed_values(value):
    with pytest.raises(click.BadParameter):
        parse_mapping(value)


def test_parse_mapping_keeps_json_values_as_text_by_default():
    assert parse_mapping("name=[a") == {"name": "[a"}
    with pytest.raises(click.BadParameter):
        parse_mapping('features=["a","b"]')


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('features=["wifi", "ble"]', {"features": ["wifi", "ble"]}),
        (
            'role=server,features=["wifi","ble"],name=uno',
            {"role": "server", "features": ["wifi", "ble"], "name": "uno"},
        ),
        (
            'config={"baud": 9600, "ports": [1, 2]}',
            {"config": {"baud": 9600, "ports": [1, 2]}},
        ),
        ('name=a,features=["x,y"]', {"name": "a", "features": ["x,y"]}),
    ],
)
def test_parse_mapping_decodes_json_values(value, expected):
    assert parse_mapping(value, json_values=True) == expected


@pytest.mark.parametrize("value", ["features=[wifi]", 'features=["wifi"', "name=[1"])
def test_parse_mapping_rejects_invalid_json(value):
    with pytest.raises(click.BadParameter):
        parse_mapping(value, json_values=True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("features=wifi", ["wifi"]),
        ('features={"family":"xmc"}', [{"family": "xmc"}]),
        ('features=["wifi","ble"]', ["wifi", "ble"]),
    ],
)
def test_parse_device_input_accepts_one_or_more_features(value, expected):
    assert parse_device_input(value).features == expected


@pytest.mark.parametrize(
    "value",
    ["name=", "name=one,name=two", "name=board,timeout=2"],
)
def test_parse_device_input_rejects_invalid_device_values(value):
    with pytest.raises(click.BadParameter):
        parse_device_input(value)
