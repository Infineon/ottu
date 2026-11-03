"""Tests for the ``ottu run`` command."""

from dataclasses import replace
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from ottu.cli import cli
from ottu.cli.parse import (
    parse_device_input,
    parse_suite_count,
    parse_suite_device_input,
    parse_suite_input,
    parse_test_path_input,
)
from ottu.device import Device, DeviceInput
from ottu.output import TestOutputOpts, TestOutputParser
from ottu.plan import Plan
from ottu.suite import (
    RoleCount,
    Suite,
    SuiteBuilder,
    SuiteDeviceInput,
    SuiteInput,
    SuiteInputValidator,
    SuiteReplicated,
    SuiteRole,
    SuiteRoleInputValidator,
)
from ottu.test_path import TestPathContext, TestPathInput


@pytest.fixture(autouse=True)
def fake_devices_are_connected(monkeypatch):
    """Treat devices without hardware access as connected; check real ones."""
    is_connected = Device.is_connected
    monkeypatch.setattr(
        Device,
        "is_connected",
        lambda self: self.access is None or is_connected(self),
    )


@pytest.fixture(autouse=True)
def no_idle_wait(monkeypatch):
    """Stop reading device output at once when a fake device stays silent."""
    create = TestOutputParser.create

    def create_without_idle_wait(test_path, opts=None, **kwargs):
        opts = opts if opts is not None else TestOutputOpts()
        return create(test_path, replace(opts, idle_timeout=0), **kwargs)

    monkeypatch.setattr(
        TestOutputParser, "create", staticmethod(create_without_idle_wait)
    )


@pytest.fixture
def project(tmp_path):
    """Create a project tree with a .ottu marker at its root."""
    (tmp_path / ".ottu").write_text(
        """version: 1
test_dirs: [tests]
test_include_patterns: ["**/*"]
test_exclude_patterns: []
backend: debug
""",
        encoding="utf-8",
    )
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    return tmp_path, nested


def test_run_without_project_marker_requires_device(tmp_path):
    result = CliRunner().invoke(cli, ["--working-dir", str(tmp_path), "run"])
    assert result.exit_code == 1
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "At least one device is required."


def test_run_without_tests_requires_device(project):
    root, _ = project
    result = CliRunner().invoke(cli, ["--working-dir", str(root), "run"])
    assert result.exit_code == 1
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "At least one device is required."


def test_run_discovers_default_test_directory(project):
    root, _ = project
    test_file = root / "tests" / "nested" / "check.py"
    test_file.parent.mkdir(parents=True)
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        ["--working-dir", str(root), "run", "--device", "board-1"],
    )
    assert result.exit_code == 0
    assert "check.py" in result.output
    assert "PASS" in result.output


def test_run_lists_devices_before_indexed_test_results(project):
    root, _ = project
    test_file = root / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "name=board-1",
            "check.py",
        ],
    )

    assert result.exit_code == 0
    assert result.output.index("> device [1]") < result.output.index("[1] check.py")
    test_result_line = next(
        line for line in result.output.splitlines() if "[1] check.py" in line
    )
    assert "PASS" in test_result_line
    assert "board-1" not in test_result_line


def test_run_discovery_uses_project_directory_and_pattern(project):
    root, _ = project
    custom_dir = root / "fixtures"
    custom_dir.mkdir()
    python_test = custom_dir / "check.py"
    cpp_test = custom_dir / "check.cpp"
    python_test.touch()
    cpp_test.touch()
    (root / ".ottu").write_text(
        """version: 1
test_dirs: [fixtures]
test_include_patterns: ["**/*.py"]
test_exclude_patterns: []
backend: debug
""",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli,
        ["--working-dir", str(root), "run", "--device", "board-1"],
    )
    assert result.exit_code == 0
    assert "check.py" in result.output
    assert "check.cpp" not in result.output


def test_run_uses_project_pattern_for_discovery(project):
    root, _ = project
    application_file = root / "app.py"
    test_file = root / "tests" / "check.py"
    test_file.parent.mkdir()
    application_file.touch()
    test_file.touch()
    (root / ".ottu").write_text(
        """version: 1
test_dirs: [tests]
test_include_patterns: ["**/*.py"]
test_exclude_patterns: []
backend: debug
""",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli, ["--working-dir", str(root), "run", "--device", "board-1"]
    )
    assert result.exit_code == 0
    assert "check.py" in result.output
    assert "app.py" not in result.output


def test_run_resolves_working_directory_test(project):
    root, _ = project
    test_file = root / "check.py"
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            "check.py",
        ],
    )
    assert result.exit_code == 0
    assert "check.py" in result.output


def test_run_writes_captured_output_to_results_directory(project, monkeypatch):
    from ottu.output import TestOutput, TestOutputParser, TestResult

    root, _ = project
    test_file = root / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()
    monkeypatch.setattr(
        "ottu.device.Device.connect",
        lambda self: type("Connection", (), {"close": lambda self: None})(),
    )
    monkeypatch.setattr(
        TestOutputParser,
        "parse",
        lambda self, connection: TestOutput(
            ("unity failure detail\n",), TestResult.FAIL
        ),
    )

    result = CliRunner().invoke(
        cli,
        ["--working-dir", str(root), "run", "--device", "board-1", "check.py"],
    )

    assert result.exit_code == 0
    assert (root / "tests" / "results" / "check.py.out").read_text(
        encoding="utf-8"
    ) == "unity failure detail\n"


def test_run_resolves_default_tests_directory_test(project):
    root, _ = project
    test_file = root / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        ["--working-dir", str(root), "run", "--device", "board-1", "check.py"],
    )
    assert result.exit_code == 0
    assert "check.py" in result.output


def test_run_resolves_absolute_test_path(project):
    root, _ = project
    test_file = root / "check.py"
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            str(test_file),
        ],
    )
    assert result.exit_code == 0
    assert "check.py" in result.output


def test_run_expands_test_glob(project):
    root, _ = project
    tests_dir = root / "tests"
    tests_dir.mkdir()
    first = tests_dir / "first.py"
    second = tests_dir / "second.py"
    first.touch()
    second.touch()
    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            "tests/*.py",
        ],
    )
    assert result.exit_code == 0
    assert "first.py" in result.output
    assert "second.py" in result.output


def test_run_rejects_missing_test_path(project):
    root, _ = project
    result = CliRunner().invoke(
        cli,
        ["--working-dir", str(root), "run", "missing.py"],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "Test path 'missing.py' does not exist."


def test_run_excludes_valid_test_input(project):
    """Run validates exclusions and removes matching resolved tests."""
    root, _ = project
    included = root / "tests" / "included.py"
    excluded = root / "tests" / "excluded.py"
    included.parent.mkdir()
    included.touch()
    excluded.touch()

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            "--exclude",
            "excluded.py",
        ],
    )

    assert result.exit_code == 0
    assert "included.py" in result.output
    assert "excluded.py" not in result.output


def test_run_accepts_multiple_exclusions(project):
    """Run validates and applies every repeated exclude option."""
    root, _ = project
    tests_dir = root / "tests"
    tests_dir.mkdir()
    included = tests_dir / "included.py"
    excluded_first = tests_dir / "excluded_first.py"
    excluded_second = tests_dir / "excluded_second.py"
    included.touch()
    excluded_first.touch()
    excluded_second.touch()

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            "--exclude",
            "excluded_first.py",
            "--exclude",
            "excluded_second.py",
        ],
    )

    assert result.exit_code == 0
    assert "included.py" in result.output
    assert "excluded_first.py" not in result.output
    assert "excluded_second.py" not in result.output


def test_run_accepts_one_standard_count(project):
    """Run accepts a single non-repeated count option."""
    root, _ = project
    test_file = root / "check.py"
    test_file.touch()

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            "--device",
            "board-2",
            "--device",
            "board-3",
            "--count",
            "3",
            "check.py",
        ],
    )

    assert result.exit_code == 0


def test_run_accepts_jobs_option(project):
    """Run accepts a positive concurrent job limit."""
    root, _ = project
    test_file = root / "check.py"
    test_file.touch()

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            "--device",
            "board-2",
            "--jobs",
            "2",
            "check.py",
        ],
    )

    assert result.exit_code == 0
    assert "check.py" in result.output


def test_run_rejects_non_positive_jobs(project):
    """Run rejects a job limit below one."""
    root, _ = project

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--jobs",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid value for" in result.output
    assert "--jobs" in result.output
    assert "x>=1" in result.output


def test_run_accepts_comma_separated_role_counts(project, monkeypatch):
    """Run accepts multiple role counts through one count option."""
    root, _ = project
    server_test = root / "server.py"
    client_test = root / "client.py"
    server_test.touch()
    client_test.touch()
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected", lambda self: True
    )
    monkeypatch.setattr("ottu.device.DeviceAccessSerial.acquire", lambda self: self)
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.connect",
        lambda self, config: type(
            "Connection",
            (),
            {
                "readline": lambda self: b"",
                "close": lambda self: None,
            },
        )(),
    )
    (root / "devs.yaml").write_text(
        "version: 1\n"
        "devices:\n"
        "  - name: server\n"
        "    uid: abcdef01\n"
        "    features: []\n"
        "  - name: server\n"
        "    uid: abcdef02\n"
        "    features: []\n"
        "  - name: client\n"
        "    uid: abcdef03\n"
        "    features: []\n"
        "  - name: client\n"
        "    uid: abcdef04\n"
        "    features: []\n"
        "  - name: client\n"
        "    uid: abcdef05\n"
        "    features: []\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "role=server,name=server",
            "--device",
            "role=client,name=client",
            "--dev-list",
            str(root / "devs.yaml"),
            "--count",
            "server=2,client=3",
            "server=server.py",
            "client=client.py",
        ],
    )

    assert result.exit_code == 0


def test_run_accepts_repeated_devices(project, monkeypatch):
    """Run accepts repeated device selectors in either supported form."""
    root, _ = project
    test_file = root / "check.py"
    test_file.touch()
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.connect",
        lambda self, device: type(
            "Connection",
            (),
            {
                "readline": lambda self: b"",
                "close": lambda self: None,
            },
        )(),
    )

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            "--device",
            "address=/dev/ttyUSB0",
            "check.py",
        ],
    )

    assert result.exit_code == 0


def test_run_accepts_a_device_list(project, monkeypatch):
    """Run accepts a device list file path."""
    root, _ = project
    (root / "check.py").touch()
    (root / "devs.yaml").write_text(
        "version: 1\n"
        "devices:\n"
        "  - name: board-1\n"
        "    uid: abcdef01\n"
        "    features: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected", lambda self: True
    )
    monkeypatch.setattr("ottu.device.DeviceAccessSerial.acquire", lambda self: self)
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.connect",
        lambda self, config: type(
            "Connection",
            (),
            {
                "readline": lambda self: b"",
                "close": lambda self: None,
            },
        )(),
    )

    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--device",
            "board-1",
            "--dev-list",
            str(root / "devs.yaml"),
            "check.py",
        ],
    )

    assert result.exit_code == 0


def test_run_rejects_missing_exclusion(project):
    """Run fails when an exclusion cannot be resolved."""
    root, _ = project
    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--exclude",
            "missing.py",
        ],
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "Test path 'missing.py' does not exist."


@pytest.fixture
def plan_file(project):
    """Create two test files and a plan with one suite for each."""
    root, _ = project
    (root / "a.py").touch()
    (root / "b.py").touch()
    path = root / "plan.yml"
    path.write_text(
        "version: 1\n"
        "suites:\n"
        "  - name: first\n"
        "    tests: a.py\n"
        "  - name: second\n"
        "    tests: b.py\n",
        encoding="utf-8",
    )
    return root, path


def run_plan(root, path, *args):
    return CliRunner().invoke(
        cli,
        ["--working-dir", str(root), "run", "--plan", str(path), *args],
    )


def test_run_plan_runs_every_suite(plan_file):
    root, path = plan_file

    result = run_plan(root, path, "--device", "board-1")

    assert result.exit_code == 0
    assert "suite : first" in result.output
    assert "suite : second" in result.output
    assert "a.py" in result.output
    assert "b.py" in result.output
    assert result.output.count("passed") == 2


def test_run_plan_selects_suites_by_name(plan_file):
    root, path = plan_file

    result = run_plan(root, path, "--device", "board-1", "second")

    assert result.exit_code == 0
    assert "b.py" in result.output
    assert "a.py" not in result.output


def test_run_plan_excludes_suites_by_name(plan_file):
    root, path = plan_file

    result = run_plan(root, path, "--device", "board-1", "--exclude", "second")

    assert result.exit_code == 0
    assert "a.py" in result.output
    assert "b.py" not in result.output


def test_run_plan_rejects_unknown_suite_name(plan_file):
    root, path = plan_file

    result = run_plan(root, path, "--device", "board-1", "missing")

    assert result.exit_code == 1
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "No suite in the plan matches 'missing'."


def test_run_plan_command_count_overrides_the_plan(plan_file):
    root, path = plan_file

    one_device = run_plan(root, path, "--device", "board-1", "--count", "2")
    two_devices = run_plan(
        root, path, "--device", "board-1", "--device", "board-2", "--count", "2"
    )

    assert one_device.exit_code == 1
    assert "needs 2 devices" in str(one_device.exception)
    assert two_devices.exit_code == 0


def test_run_plan_gives_the_jobs_to_the_suites(plan_file):
    root, path = plan_file

    result = run_plan(
        root, path, "--device", "board-1", "--device", "board-2", "--jobs", "2"
    )

    assert result.exit_code == 0


def test_run_plan_rejects_jobs_for_role_suites(project):
    root, _ = project
    (root / "a.py").touch()
    plan = root / "plan.yml"
    plan.write_text(
        "version: 1\nsuites:\n  - tests:\n      - role: server\n        test: a.py\n",
        encoding="utf-8",
    )

    result = run_plan(root, plan, "--device", "board-1", "--jobs", "2")

    assert result.exit_code == 1
    assert isinstance(result.exception, ValueError)
    assert "Jobs are not supported for role-based tests" in str(result.exception)


def test_run_plan_rejects_missing_plan_file(project):
    root, _ = project

    result = run_plan(root, root / "missing.yml", "--device", "board-1")

    assert result.exit_code == 2
    assert "missing.yml" in result.output


def test_run_plan_uses_requires_when_no_device_is_given(project):
    root, _ = project
    (root / "a.py").touch()
    plan = root / "plan.yml"
    plan.write_text(
        "version: 1\nsuites:\n  - tests: a.py\n    requires:\n"
        "      device: [{name: board-1}]\n",
        encoding="utf-8",
    )

    result = run_plan(root, plan)

    assert result.exit_code == 0
    assert "PASS" in result.output


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3", 3),
        (" 2 ", 2),
        ("server=2", (RoleCount(role="server", count=2),)),
        (
            "server=1,client=3",
            (
                RoleCount(role="server", count=1),
                RoleCount(role="client", count=3),
            ),
        ),
    ],
)
def test_parse_suite_count(value, expected):
    assert parse_suite_count(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "0", "-1", "two", "1.5", "server=0", "server=x", "3,server=2", "a=1,a=2"],
)
def test_parse_suite_count_rejects_invalid_values(value):
    with pytest.raises(click.BadParameter):
        parse_suite_count(value)


@pytest.mark.parametrize(
    "values",
    [
        {"role": "server", "count": 0},
        {"role": "server", "count": -1},
        {"role": "server", "count": "2"},
        {"role": "", "count": 1},
        {"count": 2},
    ],
)
def test_role_count_rejects_invalid_values(values):
    with pytest.raises(ValueError):
        RoleCount(**values)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("board-1", DeviceInput(identifier="board-1")),
        ("/dev/ttyUSB0", DeviceInput(identifier="/dev/ttyUSB0")),
        ("name=board-1", DeviceInput(name="board-1")),
        ("address=/dev/ttyUSB0", DeviceInput(address="/dev/ttyUSB0")),
    ],
)
def test_parse_device_input(value, expected):
    assert parse_device_input(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "  ",
        "name=",
        "=board-1",
        "color=red",
        "name=a,name=b",
        "board-1,name=a",
        "role=server",
    ],
)
def test_parse_device_input_rejects_invalid_values(value):
    with pytest.raises(click.BadParameter):
        parse_device_input(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('features=["wifi", "ble"]', DeviceInput(features=["wifi", "ble"])),
        (
            'role=server,features=["wifi","ble"],name=uno',
            SuiteDeviceInput(
                role="server",
                device=DeviceInput(features=["wifi", "ble"], name="uno"),
            ),
        ),
        (
            'features=[{"type": "uart", "baud": 9600}]',
            DeviceInput(features=[{"type": "uart", "baud": 9600}]),
        ),
        ('name=a,features=["x,y"]', DeviceInput(name="a", features=["x,y"])),
    ],
)
def test_parse_device_input_decodes_json_values(value, expected):
    if "role=" in value:
        assert parse_suite_device_input(value) == expected
    else:
        assert parse_device_input(value) == expected


@pytest.mark.parametrize("value", ["features=[wifi]", 'features=["wifi"', "name=[1"])
def test_parse_device_input_rejects_invalid_json(value):
    with pytest.raises(click.BadParameter):
        parse_device_input(value)


def test_device_input_values_default_to_none():
    device_input = DeviceInput()

    assert device_input.identifier is None
    assert device_input.name is None
    assert device_input.uid is None
    assert device_input.address is None
    assert device_input.features == []


@pytest.mark.parametrize(
    "values", [{"name": ""}, {"color": "red"}, {"features": "wifi"}]
)
def test_device_input_rejects_invalid_values(values):
    with pytest.raises(ValueError):
        DeviceInput(**values)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("tests", TestPathInput(test_selector="tests")),
        ("a,b.py", TestPathInput(test_selector="a,b.py")),
        ("server=server.py", TestPathInput(role="server", test_selector="server.py")),
        (
            " server = tests/a=b.py ",
            TestPathInput(role="server", test_selector="tests/a=b.py"),
        ),
    ],
)
def test_parse_test_path_input(value, expected):
    assert parse_test_path_input(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "  ", "=a.py", "server=", "a=x.py,b=y.py", "server=a.py,b.py"],
)
def test_parse_test_path_input_rejects_invalid_values(value):
    with pytest.raises(click.BadParameter):
        parse_test_path_input(value)


def test_test_path_input_role_defaults_to_none():
    assert TestPathInput(test_selector="a.py").role is None


@pytest.mark.parametrize(
    "values", [{"role": "", "test_selector": "a.py"}, {"test_selector": ""}]
)
def test_test_path_input_rejects_empty_strings(values):
    with pytest.raises(ValueError):
        TestPathInput(**values)


def build(tests, context, exclude_tests=(), count=None, devices=(), **arguments):
    """Parse the command arguments, then build the suite of their input."""
    suite_input = parse_suite_input(tests, exclude_tests, count, devices)
    return SuiteBuilder.build(context, suite_input, **arguments)


def suite_device_input(role=None, **values):
    """Create a suite device selector from its role and device fields."""
    return SuiteDeviceInput(role=role, device=DeviceInput(**values))


def test_parse_suite_input_converts_the_arguments_into_typed_inputs():
    inputs = parse_suite_input(
        ["server=server.py", "a.py"],
        ["skip.py"],
        "server=2",
        ["role=server,name=a", "board-1"],
    )

    assert inputs == SuiteInput(
        test_inputs=(
            TestPathInput(role="server", test_selector="server.py"),
            TestPathInput(test_selector="a.py"),
        ),
        exclude_test_inputs=(TestPathInput(test_selector="skip.py"),),
        count_input=(RoleCount(role="server", count=2),),
        device_inputs=(
            suite_device_input("server", name="a"),
            suite_device_input(identifier="board-1"),
        ),
    )


def test_parse_suite_input_without_arguments_is_empty():
    assert parse_suite_input() == SuiteInput()
    assert parse_suite_input([], [], None, []) == SuiteInput()


@pytest.mark.parametrize(
    "arguments",
    [
        {"tests": ["server="]},
        {"exclude_tests": ["a="]},
        {"count": "two"},
        {"devices": ["color=red"]},
    ],
)
def test_parse_suite_input_rejects_invalid_arguments(arguments):
    with pytest.raises(click.BadParameter):
        parse_suite_input(**arguments)


def test_build_suite_takes_typed_inputs(tmp_path):
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    suite = SuiteBuilder.build(
        TestPathContext(working_dir=tmp_path),
        SuiteInput(
            test_inputs=(
                TestPathInput(role="server", test_selector="server.py"),
                TestPathInput(role="client", test_selector="client.py"),
            ),
            count_input=(RoleCount(role="server", count=1),),
            device_inputs=(
                suite_device_input("server", name="a"),
                suite_device_input("client", name="b"),
            ),
        ),
    )

    assert {
        role: [device.name for device in pool]
        for role, pool in suite.device_pool.items()
    } == {"server": ["a"], "client": ["b"]}


def test_build_suite_takes_typed_exclusions(tmp_path):
    for name in ("a.py", "b.py"):
        (tmp_path / name).touch()

    suite = SuiteBuilder.build(
        TestPathContext(working_dir=tmp_path),
        SuiteInput(
            test_inputs=(TestPathInput(test_selector="*.py"),),
            exclude_test_inputs=(TestPathInput(test_selector="b.py"),),
            device_inputs=(suite_device_input(name="a"),),
        ),
    )

    assert [test.test_path.file_name for test in suite.tests] == ["a.py"]


def test_build_suite_accepts_valid_test_arguments(tmp_path):
    (tmp_path / "server.py").touch()
    context = TestPathContext(working_dir=tmp_path)

    for tests in (["server.py", "*.py"], ["server=server.py"], []):
        assert isinstance(build(tests, context, devices=["board-1"]), Suite)


def test_build_suite_rejects_an_invalid_test_argument(tmp_path):
    with pytest.raises(click.BadParameter):
        build(["server="], TestPathContext(working_dir=tmp_path))


def test_build_suite_rejects_role_qualified_excludes_before_resolving_tests(tmp_path):
    with pytest.raises(
        ValueError, match="Excluded test inputs cannot be role-qualified"
    ):
        build(
            ["missing.py"],
            TestPathContext(working_dir=tmp_path),
            exclude_tests=["server=skip.py"],
        )


def test_build_suite_rejects_an_unknown_test(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        build(["missing.py"], TestPathContext(working_dir=tmp_path))


def test_build_suite_accepts_valid_exclude_tests(tmp_path):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    context = TestPathContext(working_dir=tmp_path)

    assert isinstance(
        build(["*.py"], context, exclude_tests=["b.py"], devices=["board-1"]),
        Suite,
    )


def test_build_suite_rejects_an_invalid_exclude_test(tmp_path):
    with pytest.raises(click.BadParameter):
        build([], TestPathContext(working_dir=tmp_path), exclude_tests=["a="])


def test_build_suite_rejects_an_unknown_exclude_test(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        build([], TestPathContext(working_dir=tmp_path), exclude_tests=["missing.py"])


@pytest.mark.parametrize("count", [None, "2"])
def test_build_suite_accepts_a_valid_count(tmp_path, count):
    context = TestPathContext(working_dir=tmp_path)

    devices = ["board-1"] if count is None else ["board-1", "board-2"]
    assert isinstance(build([], context, count=count, devices=devices), Suite)


@pytest.mark.parametrize("count", ["0", "two", "server=", "3,server=2"])
def test_build_suite_rejects_an_invalid_count(tmp_path, count):
    with pytest.raises(click.BadParameter):
        build([], TestPathContext(working_dir=tmp_path), count=count)


@pytest.mark.parametrize(
    "devices",
    [["board-1"], ["name=a"]],
)
def test_build_suite_accepts_valid_devices(tmp_path, devices):
    context = TestPathContext(working_dir=tmp_path)

    assert isinstance(build([], context, devices=devices), Suite)


def test_build_suite_rejects_non_identity_filter_without_a_device_list(tmp_path):
    with pytest.raises(ValueError, match="device identity is required"):
        build(
            [],
            TestPathContext(working_dir=tmp_path),
            devices=['features=["wifi","ble"]'],
        )


def test_build_suite_requires_a_device(tmp_path):
    with pytest.raises(ValueError, match="At least one device is required"):
        build([], TestPathContext(working_dir=tmp_path))


@pytest.mark.parametrize("devices", [[""], ["color=red"], ["name=a", "name="]])
def test_build_suite_rejects_an_invalid_device(tmp_path, devices):
    with pytest.raises(click.BadParameter):
        build([], TestPathContext(working_dir=tmp_path), devices=devices)


def selector(test_selector, role=None):
    return TestPathInput(role=role, test_selector=test_selector)


def role_suite(tmp_path, **overrides):
    """Validate a valid two-role suite, with some of its inputs replaced."""
    jobs = overrides.pop("jobs", 1)
    values = {
        "test_inputs": (
            selector("server.py", "server"),
            selector("client.py", "client"),
        ),
    }
    values.update(overrides)
    suite_input = SuiteInput(
        test_inputs=tuple(values["test_inputs"]),
        exclude_test_inputs=tuple(values.get("exclude_test_inputs", ())),
        count_input=values.get("count_input"),
        device_inputs=tuple(values.get("device_inputs", ())),
    )
    for test_input in suite_input.test_inputs:
        test_path = Path(test_input.test_selector)
        if not test_path.is_absolute():
            test_path = tmp_path / test_path
        if not test_path.exists():
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.touch()
    SuiteRoleInputValidator.validate(
        TestPathContext(working_dir=tmp_path), suite_input, jobs
    )


def test_validator_accepts_a_standard_suite():
    SuiteInputValidator.validate(
        TestPathContext(),
        SuiteInput(
            test_inputs=(selector("a.py"), selector("*.py")),
            exclude_test_inputs=(selector("b.py"),),
            count_input=2,
            device_inputs=(
                suite_device_input(name="a"),
                suite_device_input(name="b"),
            ),
        ),
        jobs=2,
    )


def test_validator_accepts_a_suite_without_inputs():
    SuiteInputValidator.validate(TestPathContext(), SuiteInput())


def test_validator_rejects_role_qualified_excludes():
    with pytest.raises(
        ValueError, match="Excluded test inputs cannot be role-qualified"
    ):
        SuiteInputValidator.validate(
            TestPathContext(),
            SuiteInput(exclude_test_inputs=(selector("skip.py", "server"),)),
        )


@pytest.mark.parametrize(
    ("count", "device_inputs", "message"),
    [
        ((RoleCount(role="server", count=2),), [], "Count for role 'server'"),
        (None, [suite_device_input("server")], "Device for role 'server'"),
    ],
)
def test_validator_rejects_roles_without_role_tests(count, device_inputs, message):
    with pytest.raises(ValueError, match=message):
        SuiteInputValidator.validate(
            TestPathContext(),
            SuiteInput(
                test_inputs=(selector("a.py"),),
                count_input=count,
                device_inputs=tuple(device_inputs),
            ),
        )


def test_validator_detects_the_role_mode():
    role_input = SuiteInput(test_inputs=(selector("a.py", "server"),))
    standard_input = SuiteInput(test_inputs=(selector("a.py"),))

    assert role_input.is_role_mode()
    assert role_input.validator() is SuiteRoleInputValidator
    assert not standard_input.is_role_mode()
    assert standard_input.validator() is SuiteInputValidator
    assert SuiteInput().validator() is SuiteInputValidator


def test_validator_accepts_a_role_suite(tmp_path):
    role_suite(tmp_path)
    role_suite(
        tmp_path,
        count_input=2,
        device_inputs=[suite_device_input(name="board")],
    )
    role_suite(
        tmp_path,
        count_input=(
            RoleCount(role="server", count=2),
            RoleCount(role="client", count=1),
        ),
        device_inputs=[
            suite_device_input("client", name="a"),
            suite_device_input("server", name="b"),
        ],
    )


def test_validator_rejects_mixed_role_and_plain_tests(tmp_path):
    with pytest.raises(ValueError, match="cannot be mixed"):
        role_suite(
            tmp_path,
            test_inputs=[selector("server.py", "server"), selector("client.py")],
        )


def test_validator_rejects_a_repeated_role(tmp_path):
    with pytest.raises(ValueError, match="Role 'server' was provided more than once"):
        role_suite(
            tmp_path,
            test_inputs=[selector("a.py", "server"), selector("b.py", "server")],
        )


def test_validator_rejects_a_pattern_for_a_role(tmp_path):
    with pytest.raises(ValueError, match="not a pattern"):
        role_suite(
            tmp_path,
            test_inputs=[selector("*.py", "server")],
        )


def test_validator_rejects_a_directory_selector_for_a_role(tmp_path):
    test_dir = tmp_path / "suite"
    test_dir.mkdir()
    (test_dir / "server.py").touch()

    with pytest.raises(ValueError, match="exactly one test file"):
        role_suite(tmp_path, test_inputs=[selector("suite", "server")])


def test_validator_rejects_a_missing_file_for_a_role(tmp_path):
    with pytest.raises(ValueError, match="exactly one test file"):
        SuiteRoleInputValidator.validate(
            TestPathContext(working_dir=tmp_path),
            SuiteInput(test_inputs=(selector("missing.py", "server"),)),
        )


def test_validator_rejects_exclusions_for_role_tests(tmp_path):
    with pytest.raises(ValueError, match="Exclusions are not supported"):
        role_suite(tmp_path, exclude_test_inputs=[selector("skip.py")])


def test_validator_rejects_jobs_for_role_tests(tmp_path):
    with pytest.raises(ValueError, match="Jobs are not supported"):
        role_suite(tmp_path, jobs=2)


@pytest.mark.parametrize(
    ("count", "message"),
    [
        ((RoleCount(role="other", count=2),), "Unknown role 'other' in count"),
        (
            (RoleCount(role="server", count=2), RoleCount(role="server", count=1)),
            "provided more than once",
        ),
    ],
)
def test_validator_rejects_invalid_role_counts(tmp_path, count, message):
    with pytest.raises(ValueError, match=message):
        role_suite(tmp_path, count_input=count)


@pytest.mark.parametrize(
    ("device_inputs", "message"),
    [
        (
            [suite_device_input(name="a"), suite_device_input(name="b")],
            "need a role",
        ),
        (
            [suite_device_input("server", name="a"), suite_device_input(name="b")],
            "cannot be mixed with unqualified",
        ),
        ([suite_device_input("other", name="a")], "Unknown role 'other'"),
        (
            [
                suite_device_input("server", name="a"),
                suite_device_input("server", name="b"),
            ],
            "provided more than once",
        ),
        (
            [suite_device_input("server", name="a")],
            "Missing device input for role.*client",
        ),
    ],
)
def test_validator_rejects_invalid_role_devices(tmp_path, device_inputs, message):
    with pytest.raises(ValueError, match=message):
        role_suite(tmp_path, device_inputs=device_inputs)


def test_build_suite_accepts_a_valid_role_suite(tmp_path):
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()
    context = TestPathContext(working_dir=tmp_path)

    build(
        ["server=server.py", "client=client.py"],
        context,
        count="server=1,client=1",
        devices=["role=server,name=a", "role=client,name=b"],
    )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"exclude_tests": ["client.py"]}, "Exclusions are not supported"),
        ({"jobs": 2}, "Jobs are not supported"),
        ({"count": "other=2"}, "Unknown role 'other' in count"),
        ({"devices": ["name=a", "name=b"]}, "need a role"),
    ],
)
def test_build_suite_rejects_invalid_role_suites(tmp_path, arguments, message):
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    with pytest.raises(ValueError, match=message):
        build(
            ["server=server.py"],
            TestPathContext(working_dir=tmp_path),
            **arguments,
        )


def test_build_suite_rejects_a_role_count_without_role_tests(tmp_path):
    (tmp_path / "a.py").touch()

    with pytest.raises(ValueError, match="needs role-qualified tests"):
        build(["a.py"], TestPathContext(working_dir=tmp_path), count="server=2")


@pytest.fixture
def created_tests(monkeypatch):
    """Record the tests that the suite builder creates."""
    tests = []
    create = SuiteBuilder._create_tests

    def record(test_paths, backend, observers):
        created = create(test_paths, backend, observers)
        tests.extend(
            (
                test.test_path.file_name,
                {
                    "options": test.options,
                    "backend": test.backend,
                    "observers": test.observers,
                },
            )
            for test in created
        )
        return created

    monkeypatch.setattr(SuiteBuilder, "_create_tests", staticmethod(record))
    return tests


def test_build_suite_creates_a_test_for_each_path_with_its_role(
    tmp_path, created_tests
):
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()
    backend = object()
    observer = object()

    build(
        ["server=server.py", "client=client.py"],
        TestPathContext(working_dir=tmp_path),
        devices=["board-1"],
        backend=backend,
        observers=[observer],
    )

    assert [(name, arguments["options"].role) for name, arguments in created_tests] == [
        ("server.py", "server"),
        ("client.py", "client"),
    ]
    assert all(arguments["backend"] is backend for _, arguments in created_tests)
    assert all(arguments["observers"] == (observer,) for _, arguments in created_tests)


def test_build_suite_creates_tests_without_role_for_plain_inputs(
    tmp_path, created_tests
):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()

    build(["*.py"], TestPathContext(working_dir=tmp_path), devices=["board-1"])

    assert [(name, arguments["options"].role) for name, arguments in created_tests] == [
        ("a.py", None),
        ("b.py", None),
    ]


def test_build_suite_removes_the_excluded_tests(tmp_path, created_tests):
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).touch()

    build(
        ["*.py"],
        TestPathContext(working_dir=tmp_path),
        exclude_tests=["b.py"],
        devices=["board-1"],
    )

    assert [name for name, _ in created_tests] == ["a.py", "c.py"]


def test_build_suite_removes_the_tests_excluded_by_the_context(tmp_path, created_tests):
    for name in ("a.py", "skip_b.py"):
        (tmp_path / name).touch()
    context = TestPathContext(working_dir=tmp_path, test_exclude_patterns=["skip_*.py"])

    build(["*.py"], context, devices=["board-1"])

    assert [name for name, _ in created_tests] == ["a.py"]


def test_build_suite_rejects_a_role_test_excluded_by_the_context(tmp_path):
    (tmp_path / "skip_server.py").touch()
    context = TestPathContext(working_dir=tmp_path, test_exclude_patterns=["skip_*.py"])

    with pytest.raises(ValueError, match="exactly one test file"):
        build(["server=skip_server.py"], context)


def test_build_suite_keeps_role_device_inputs_and_counts(tmp_path):
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    suite = build(
        ["server=server.py", "client=client.py"],
        TestPathContext(working_dir=tmp_path),
        count="server=1",
        devices=["role=server,name=a", "role=client,name=b"],
    )

    assert {
        role: [device.name for device in devices]
        for role, devices in suite.device_pool.items()
    } == {"server": ["a"], "client": ["b"]}
    assert suite.options.count == (RoleCount(role="server", count=1),)


def test_build_suite_keeps_device_candidates_and_counts_without_roles(tmp_path):
    (tmp_path / "a.py").touch()

    suite = build(
        ["a.py"],
        TestPathContext(working_dir=tmp_path),
        count="2",
        devices=["name=a", "name=b"],
    )

    assert [device.name for device in suite.device_pool[None]] == ["a", "b"]
    assert suite.options.count == 2


def test_build_suite_rejects_insufficient_device_candidates(tmp_path):
    (tmp_path / "a.py").touch()

    with pytest.raises(ValueError, match="Suite needs 2 devices, but only 1 matched"):
        build(
            ["a.py"],
            TestPathContext(working_dir=tmp_path),
            count="2",
            devices=["name=a"],
        )


def test_build_suite_keeps_device_alternatives_without_roles(tmp_path):
    (tmp_path / "a.py").touch()

    suite = build(
        ["a.py"],
        TestPathContext(working_dir=tmp_path),
        count="2",
        devices=["name=a", "name=b"],
    )

    assert [device.name for device in suite.device_pool[None]] == ["a", "b"]
    assert suite.options.count == 2


def test_build_suite_loads_the_device_list(tmp_path):
    (tmp_path / "a.py").touch()
    (tmp_path / "devices.yaml").write_text(
        "version: 1\ndevices:\n  - name: board-1\n    uid: abc123\n", encoding="utf-8"
    )

    suite = build(
        ["a.py"],
        TestPathContext(working_dir=tmp_path),
        dev_list=tmp_path / "devices.yaml",
    )

    assert isinstance(suite, Suite)


def test_build_suite_returns_the_suite_of_the_tests_and_devices(tmp_path):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()

    suite = build(
        ["*.py"],
        TestPathContext(working_dir=tmp_path),
        count="2",
        devices=["name=a", "name=b"],
        observers=[],
    )

    assert [test.test_path.file_name for test in suite.tests] == ["a.py", "b.py"]
    assert [device.name for device in suite.device_pool[None]] == ["a", "b"]
    assert isinstance(suite, SuiteReplicated)
    assert suite.options.count == 2


def test_build_suite_builds_a_role_suite_with_a_device_for_each_role(tmp_path):
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    suite = build(
        ["server=server.py", "client=client.py"],
        TestPathContext(working_dir=tmp_path),
        devices=["role=server,name=a", "role=client,name=b"],
    )

    assert isinstance(suite, SuiteRole)
    assert {
        role: [device.name for device in pool]
        for role, pool in suite.device_pool.items()
    } == {"server": ["a"], "client": ["b"]}


def test_build_suite_reports_a_role_without_enough_devices(tmp_path):
    (tmp_path / "server.py").touch()

    with pytest.raises(
        ValueError, match="Role 'server' needs 2 devices, but only 1 matched"
    ):
        build(
            ["server=server.py"],
            TestPathContext(working_dir=tmp_path),
            count="server=2",
            devices=["role=server,name=a"],
        )


def test_build_suite_rejects_an_invalid_device_list(tmp_path):
    (tmp_path / "a.py").touch()
    (tmp_path / "devices.yaml").write_text(
        "version: 2\ndevices: []\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Input should be 1"):
        build(
            ["a.py"],
            TestPathContext(working_dir=tmp_path),
            dev_list=tmp_path / "devices.yaml",
        )


def test_build_suite_discovers_the_tests_when_none_are_given(tmp_path):
    (tmp_path / "tests").mkdir()
    for name in ("a.py", "b.py"):
        (tmp_path / "tests" / name).touch()
    (tmp_path / "outside.py").touch()

    suite = build([], TestPathContext(working_dir=tmp_path), devices=["board-1"])

    assert [test.test_path.file_name for test in suite.tests] == ["a.py", "b.py"]
    assert [test.options.role for test in suite.tests] == [None, None]


def test_build_suite_excludes_from_the_discovered_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / "tests" / name).touch()
    context = TestPathContext(working_dir=tmp_path)

    suite = build([], context, exclude_tests=["tests/b.py"], devices=["board-1"])

    assert [test.test_path.file_name for test in suite.tests] == ["a.py", "c.py"]


def test_build_suite_excludes_discovered_tests_by_the_context_patterns(tmp_path):
    (tmp_path / "tests").mkdir()
    for name in ("a.py", "skip_b.py"):
        (tmp_path / "tests" / name).touch()
    context = TestPathContext(working_dir=tmp_path, test_exclude_patterns=["skip_*.py"])

    suite = build([], context, devices=["board-1"])

    assert [test.test_path.file_name for test in suite.tests] == ["a.py"]


def test_build_suite_does_not_discover_when_tests_are_given(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.py").touch()
    (tmp_path / "tests" / "b.py").touch()

    suite = build(["a.py"], TestPathContext(working_dir=tmp_path), devices=["board-1"])

    assert [test.test_path.file_name for test in suite.tests] == ["a.py"]


def write_plan(tmp_path, text):
    path = tmp_path / "plan.yml"
    path.write_text(text, encoding="utf-8")
    return path


def suite_names(suites):
    return [suite.name for suite in suites]


def test_build_suites_builds_a_suite_for_each_suite_of_the_plan(tmp_path):
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).touch()
    plan = write_plan(
        tmp_path,
        "version: 1\n"
        "suites:\n"
        "  - name: first\n    tests: a.py\n"
        "  - name: second\n    tests: b.py\n"
        "  - tests: c.py\n",
    )

    suites = Plan.from_file(plan).build_suites(
        TestPathContext(working_dir=tmp_path),
        device_inputs=[suite_device_input(name="board-1")],
    )

    assert suite_names(suites) == ["first", "second", "Suite 3"]
    assert [[test.test_path.file_name for test in suite.tests] for suite in suites] == [
        ["a.py"],
        ["b.py"],
        ["c.py"],
    ]


def test_build_suites_keeps_the_selected_suites(tmp_path):
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).touch()
    plan = write_plan(
        tmp_path,
        "version: 1\n"
        "suites:\n"
        "  - name: smoke_a\n    tests: a.py\n"
        "  - name: smoke_b\n    tests: b.py\n"
        "  - name: slow\n    tests: c.py\n",
    )
    context = TestPathContext(working_dir=tmp_path)
    devices = [suite_device_input(name="board-1")]

    selected = Plan.from_file(plan).build_suites(
        context, tests=["smoke_*"], device_inputs=devices
    )
    excluded = Plan.from_file(plan).build_suites(
        context, exclude=["smoke_*"], device_inputs=devices
    )

    assert suite_names(selected) == ["smoke_a", "smoke_b"]
    assert suite_names(excluded) == ["slow"]


def test_build_suites_rejects_an_unknown_suite(tmp_path):
    plan = write_plan(tmp_path, "version: 1\nsuites:\n  - name: a\n    tests: a.py\n")

    with pytest.raises(ValueError, match="No suite in the plan matches 'missing'"):
        Plan.from_file(plan).build_suites(
            TestPathContext(working_dir=tmp_path),
            tests=["missing"],
            device_inputs=[suite_device_input(name="board-1")],
        )


def test_build_suites_uses_the_exclusions_and_count_of_a_suite(tmp_path):
    for name in ("a.py", "b.py"):
        (tmp_path / name).touch()
    plan = write_plan(
        tmp_path,
        "version: 1\n"
        "suites:\n"
        "  - name: all\n"
        "    tests: '*.py'\n"
        "    exclude: b.py\n"
        "    count: 2\n",
    )

    (suite,) = Plan.from_file(plan).build_suites(
        TestPathContext(working_dir=tmp_path),
        device_inputs=[
            suite_device_input(name="board-1"),
            suite_device_input(name="board-2"),
        ],
    )

    assert [test.test_path.file_name for test in suite.tests] == ["a.py"]
    assert suite.options.count == 2
    assert isinstance(suite, SuiteReplicated)


def test_build_suites_rejects_insufficient_devices_for_a_count(tmp_path):
    for name in ("a.py", "b.py"):
        (tmp_path / name).touch()
    plan = write_plan(
        tmp_path,
        "version: 1\n"
        "suites:\n"
        "  - name: all\n"
        "    tests: '*.py'\n"
        "    exclude: b.py\n"
        "    count: 2\n",
    )

    with pytest.raises(ValueError, match="Suite needs 2 devices, but only 1 matched"):
        Plan.from_file(plan).build_suites(
            TestPathContext(working_dir=tmp_path),
            device_inputs=[suite_device_input(name="board-1")],
        )


def test_build_suites_builds_a_role_suite_with_the_counts_of_its_roles(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected", lambda self: True
    )
    for name in ("server.py", "client.py"):
        (tmp_path / name).touch()
    (tmp_path / "devs.yaml").write_text(
        "version: 1\n"
        "devices:\n"
        "  - name: server\n    uid: abcdef01\n"
        "  - name: client\n    uid: abcdef02\n"
        "  - name: client\n    uid: abcdef03\n",
        encoding="utf-8",
    )
    plan = write_plan(
        tmp_path,
        "version: 1\n"
        "suites:\n"
        "  - name: roles\n"
        "    tests:\n"
        "      - role: server\n        test: server.py\n"
        "      - role: client\n        test: client.py\n        count: 2\n"
        "    requires:\n"
        "      device:\n"
        "        - role: server\n          name: server\n"
        "        - role: client\n          name: client\n",
    )

    (suite,) = Plan.from_file(plan).build_suites(
        TestPathContext(working_dir=tmp_path),
        dev_list=tmp_path / "devs.yaml",
    )

    assert suite.name == "roles"
    assert isinstance(suite, SuiteRole)
    assert {
        role: [device.name for device in pool]
        for role, pool in suite.device_pool.items()
    } == {"server": ["server"], "client": ["client", "client"]}


def test_build_suites_requires_a_device(tmp_path):
    (tmp_path / "a.py").touch()
    plan = write_plan(tmp_path, "version: 1\nsuites:\n  - name: a\n    tests: a.py\n")

    with pytest.raises(ValueError, match="At least one device is required"):
        Plan.from_file(plan).build_suites(TestPathContext(working_dir=tmp_path))


def test_build_suites_replaces_the_required_devices_with_the_command_devices(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected", lambda self: True
    )
    (tmp_path / "a.py").touch()
    (tmp_path / "devs.yaml").write_text(
        "version: 1\n"
        "devices:\n"
        "  - name: uno\n    uid: abcdef01\n    features: [wifi]\n"
        "  - name: nano\n    uid: abcdef02\n",
        encoding="utf-8",
    )
    plan = write_plan(
        tmp_path,
        "version: 1\n"
        "suites:\n"
        "  - name: a\n"
        "    tests: a.py\n"
        "    requires:\n"
        "      device:\n"
        "        - features: [wifi]\n",
    )

    (suite,) = Plan.from_file(plan).build_suites(
        TestPathContext(working_dir=tmp_path),
        device_inputs=[suite_device_input(name="nano")],
        dev_list=tmp_path / "devs.yaml",
    )

    assert [device.name for device in suite.device_pool[None]] == ["nano"]
