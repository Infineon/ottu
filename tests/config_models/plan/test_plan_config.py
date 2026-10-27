"""Tests for test plan loading and validation."""

import pytest
from ottu.config_models.plan.plan import Plan, PlanConfig, RoleTest
from pydantic import ValidationError


def suite(**values):
    """Validate a plan holding one suite and return that suite."""
    return Plan.model_validate({"version": 1, "suites": [values]}).suites[0]


def test_plan_config_loads_yaml(tmp_path):
    path = tmp_path / "plan.yml"
    path.write_text(
        """version: 1
suites:
  - name: smoke
    tests: [tests/test_a.py, tests/test_b.py]
    exclude: tests/test_b.py
    count: 2
    requires:
      device:
        - role: server
          address: /dev/ttyUSB0
        - features: [wifi]
  - name: roles
    tests:
      - role: server
        test: tests/test_server.py
      - role: client
        test: tests/test_client.py
        count: 4
""",
        encoding="utf-8",
    )

    plan = PlanConfig.from_file(path)

    smoke, roles = plan.suites
    assert plan.version == 1
    assert smoke.name == "smoke"
    assert smoke.tests == ["tests/test_a.py", "tests/test_b.py"]
    assert smoke.exclude == ["tests/test_b.py"]
    assert smoke.count == 2
    assert smoke.requires.device == [
        {"role": "server", "address": "/dev/ttyUSB0"},
        {"features": ["wifi"]},
    ]
    assert roles.tests == [
        RoleTest(role="server", test="tests/test_server.py"),
        RoleTest(role="client", test="tests/test_client.py", count=4),
    ]


def test_plan_config_rejects_unsupported_version(tmp_path):
    path = tmp_path / "plan.yml"
    path.write_text("version: 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported plan schema version: 2"):
        PlanConfig.from_file(path)


def test_plan_config_rejects_non_integer_version(tmp_path):
    path = tmp_path / "plan.yml"
    path.write_text("version: '1'\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported plan schema version: 1"):
        PlanConfig.from_file(path)


def test_plan_config_rejects_missing_version(tmp_path):
    path = tmp_path / "plan.yml"
    path.write_text("suites: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported plan schema version: None"):
        PlanConfig.from_file(path)


@pytest.mark.parametrize(
    ("mapping", "error_type"),
    [
        ({}, "missing"),
        ({"version": 9}, "literal_error"),
        ({"version": 1, "unexpected": True}, "extra_forbidden"),
        ({"version": 1, "suites": [{"unexpected": True}]}, "extra_forbidden"),
        ([], "model_type"),
    ],
)
def test_plan_rejects_invalid_mapping(mapping, error_type):
    with pytest.raises(ValidationError) as error:
        Plan.model_validate(mapping)

    assert any(item["type"] == error_type for item in error.value.errors())


def test_plan_defaults_to_no_suites():
    assert Plan.model_validate({"version": 1}).suites == []


def test_suite_defaults():
    result = suite()

    assert result.name is None
    assert result.tests == []
    assert result.exclude == []
    assert result.count is None
    assert result.requires.device == []


@pytest.mark.parametrize("field", ["tests", "exclude"])
def test_suite_accepts_single_string_as_list(field):
    assert getattr(suite(**{field: "a.py"}), field) == ["a.py"]


@pytest.mark.parametrize("field", ["tests", "exclude"])
def test_suite_keeps_string_list(field):
    assert getattr(suite(**{field: ["a.py", "b.py"]}), field) == ["a.py", "b.py"]


@pytest.mark.parametrize("field", ["tests", "exclude"])
def test_suite_rejects_non_string_entries(field):
    with pytest.raises(ValidationError, match=field):
        suite(**{field: ["a.py", 3]})


@pytest.mark.parametrize("count", [0, -1])
def test_suite_rejects_non_positive_count(count):
    with pytest.raises(ValidationError, match="count"):
        suite(count=count)


def test_suite_rejects_non_integer_count():
    with pytest.raises(ValidationError, match="count"):
        suite(count="2")


def test_requires_device_accepts_list_of_mappings():
    devices = [{"role": "server"}, {"name": "uno", "features": ["wifi", 1]}]

    assert suite(requires={"device": devices}).requires.device == devices


def test_requires_device_accepts_single_mapping_as_list():
    assert suite(requires={"device": {"name": "uno"}}).requires.device == [
        {"name": "uno"}
    ]


@pytest.mark.parametrize("device", ["role=server", ["role=server"], 1])
def test_requires_device_rejects_non_mapping_entries(device):
    with pytest.raises(ValidationError, match="device"):
        suite(requires={"device": device})


def test_requires_rejects_unknown_key():
    with pytest.raises(ValidationError) as error:
        suite(requires={"exclude": []})

    assert any(item["type"] == "extra_forbidden" for item in error.value.errors())


def test_suite_accepts_role_tests_with_default_count():
    result = suite(tests=[{"role": "server", "test": "tests/test_server.py"}])

    assert result.tests == [RoleTest(role="server", test="tests/test_server.py")]
    assert result.tests[0].count == 1


def test_suite_accepts_single_role_test_mapping_as_list():
    result = suite(tests={"role": "server", "test": "tests/test_server.py"})

    assert result.tests == [RoleTest(role="server", test="tests/test_server.py")]


def test_suite_accepts_role_test_count():
    result = suite(tests=[{"role": "client", "test": "t.py", "count": 4}])

    assert result.tests[0].count == 4


@pytest.mark.parametrize(
    "role_test",
    [
        {"role": "server"},
        {"test": "t.py"},
        {"role": "", "test": "t.py"},
        {"role": "server", "test": ""},
        {"role": "server", "test": "t.py", "count": 0},
        {"role": "server", "test": "t.py", "order": 1},
    ],
)
def test_suite_rejects_invalid_role_test(role_test):
    with pytest.raises(ValidationError):
        suite(tests=[role_test])


def test_suite_rejects_mixed_role_and_plain_tests():
    with pytest.raises(ValidationError, match="cannot be mixed"):
        suite(tests=["a.py", {"role": "server", "test": "b.py"}])


def test_suite_rejects_duplicate_roles():
    with pytest.raises(ValidationError, match="unique roles"):
        suite(
            tests=[
                {"role": "server", "test": "a.py"},
                {"role": "server", "test": "b.py"},
            ]
        )


def test_suite_rejects_suite_count_with_role_tests():
    with pytest.raises(ValidationError, match="per-role 'count'"):
        suite(count=2, tests=[{"role": "server", "test": "a.py"}])


def test_suite_rejects_exclude_with_role_tests():
    with pytest.raises(ValidationError, match="'exclude' cannot be used"):
        suite(exclude="b.py", tests=[{"role": "server", "test": "a.py"}])


def test_suite_accepts_role_tests_with_matching_devices():
    result = suite(
        tests=[
            {"role": "server", "test": "a.py"},
            {"role": "client", "test": "b.py"},
        ],
        requires={"device": [{"role": "server"}, {"role": "client"}, {"role": "x"}]},
    )

    assert [test.role for test in result.tests] == ["server", "client"]


def test_suite_accepts_role_tests_without_devices():
    result = suite(tests=[{"role": "server", "test": "a.py"}])

    assert result.requires.device == []


def test_suite_rejects_role_without_matching_device():
    with pytest.raises(ValidationError, match="no matching requires.device role"):
        suite(
            tests=[
                {"role": "server", "test": "a.py"},
                {"role": "client", "test": "b.py"},
            ],
            requires={"device": [{"role": "server"}, {"name": "uno"}]},
        )
