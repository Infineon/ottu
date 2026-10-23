"""Tests for suite input classification."""

import queue
from dataclasses import replace
from pathlib import Path

import pytest
from ottu.backend import Backend
from ottu.device import Device, DeviceAccessSerial, DeviceQuery
from ottu.report import TestReport, TestStatus
from ottu.suite import (
    RoleSuiteInputStrategy,
    StandardSuiteInputStrategy,
    Suite,
    SuiteInputStrategy,
    SuiteOpts,
    SuiteParallelTestReportNotifier,
    SuiteParallelTestReportObserver,
)
from ottu.test import Test, TestOpts, TestPath, TestPathContext, TestPathResolver


def make_report(name, status, job_id=None):
    path = TestPath(name, name, None, name)
    return TestReport(path, status, job_id=job_id)


def test_standard_input_strategy_matches_plain_inputs():
    """The standard strategy accepts unqualified test selectors."""
    assert StandardSuiteInputStrategy.matches(["test_a.py", "test_b.py"])


def test_suite_input_strategy_base_contract_is_not_implemented():
    """The abstract strategy contract raises before a concrete implementation."""
    with pytest.raises(NotImplementedError):
        SuiteInputStrategy.matches(["test_a.py"])
    with pytest.raises(NotImplementedError):
        SuiteInputStrategy.from_inputs(
            ["test_a.py"],
            context=TestPathContext(),
            exclude_test_selectors=(),
            count=None,
        )


def test_role_input_strategy_matches_role_inputs():
    """The role strategy claims all role input attempts."""
    assert RoleSuiteInputStrategy.matches(["server=server.py"])


def test_role_input_strategy_rejects_exclusions():
    """Role inputs reject exclusion selectors to keep parsing deterministic."""
    with pytest.raises(ValueError, match="Exclusions are not supported"):
        RoleSuiteInputStrategy.from_inputs(
            ["server=server.py"],
            context=TestPathContext(),
            exclude_test_selectors=("skip.py",),
            count=None,
        )


def test_classify_test_inputs_rejects_duplicate_roles():
    """Each role can have only one test input."""
    with pytest.raises(ValueError, match="provided more than once"):
        RoleSuiteInputStrategy.from_inputs(
            ["server=one.py", "server=two.py"],
            context=TestPathContext(),
            exclude_test_selectors=(),
            count=None,
        )


def test_classify_test_inputs_rejects_mixed_roles_and_plain_inputs():
    """Role-qualified and unqualified inputs cannot be mixed."""
    with pytest.raises(ValueError, match="cannot be mixed"):
        RoleSuiteInputStrategy.from_inputs(
            ["server=server.py", "client.py"],
            context=TestPathContext(),
            exclude_test_selectors=(),
            count=None,
        )


def test_suite_opts_rejects_extra_equals_in_role_input():
    """Role-qualified inputs must contain exactly one equals separator."""
    with pytest.raises(ValueError):
        RoleSuiteInputStrategy.from_inputs(
            ["server=server=server.py"],
            context=TestPathContext(),
            exclude_test_selectors=(),
            count=None,
        )


def test_suite_opts_rejects_malformed_role_input():
    """Role-qualified inputs require both a role and a test path."""
    with pytest.raises(ValueError, match="key=value"):
        RoleSuiteInputStrategy.from_inputs(
            ["server="],
            context=TestPathContext(),
            exclude_test_selectors=(),
            count=None,
        )


def test_assign_devices_pairs_replicas_with_distinct_devices():
    """Each replica is paired one-to-one with a distinct device when able."""
    test = Test(TestPath("check.py", "check.py", None, "check.py"))

    tests = StandardSuiteInputStrategy._assign_devices(
        [test], (Device(name="board-1"), Device(name="board-2")), 2
    )

    assert [t.device.name for t in tests if t.device] == ["board-1", "board-2"]


def test_assign_devices_rejects_insufficient_devices_for_replicas():
    """Replicas must not exceed the number of devices supplied."""
    test = Test(TestPath("check.py", "check.py", None, "check.py"))

    with pytest.raises(ValueError, match="needs 2 devices"):
        StandardSuiteInputStrategy._assign_devices([test], (Device(name="board-1"),), 2)


def test_assign_devices_rejects_missing_device_for_replica():
    """Assignment requires a device for every replica."""
    test = Test(TestPath("check.py", "check.py", None, "check.py"))

    with pytest.raises(ValueError, match="needs 1 devices"):
        StandardSuiteInputStrategy._assign_devices([test], ())


def test_assign_devices_rejects_missing_devices_for_replicas():
    """Assignment requires a distinct device for every replica."""
    test = Test(TestPath("check.py", "check.py", None, "check.py"))

    with pytest.raises(ValueError, match="needs 2 devices"):
        StandardSuiteInputStrategy._assign_devices([test], (), required_count=2)


def test_resolve_devices_returns_all_direct_devices():
    """Direct resolution returns every supplied device."""
    assert StandardSuiteInputStrategy._resolve_devices(("board-1",), None) == (
        Device.from_string("board-1"),
    )


def test_resolve_devices_returns_all_matching_list_devices_when_required_is_lower(
    tmp_path, monkeypatch
):
    """Device-list resolution returns every unique match."""
    available = [Device(name="board-1"), Device(name="board-2")]
    monkeypatch.setattr(Device, "from_file", lambda _: available)
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    assert StandardSuiteInputStrategy._resolve_devices(
        ("board",), tmp_path / "devices.yml"
    ) == tuple(available)


def test_resolve_devices_uses_all_list_devices_without_a_query(tmp_path, monkeypatch):
    """A device list without a query searches every available device."""
    available = [Device(name="board-1"), Device(name="board-2")]
    monkeypatch.setattr(Device, "from_file", lambda _: available)
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    assert StandardSuiteInputStrategy._resolve_devices(
        (), tmp_path / "devices.yml"
    ) == tuple(available)


def test_resolve_devices_returns_all_list_matches(tmp_path, monkeypatch):
    """Device-list resolution leaves count validation to assignment."""
    available = [Device(name="board-1")]
    monkeypatch.setattr(Device, "from_file", lambda _: available)
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    assert StandardSuiteInputStrategy._resolve_devices(
        ("board",), tmp_path / "devices.yml"
    ) == tuple(available)


def test_resolve_devices_returns_empty_result_for_zero_required_devices(
    tmp_path, monkeypatch
):
    """A zero-device request returns without requiring a list match."""
    monkeypatch.setattr(Device, "from_file", lambda _: [])

    assert (
        StandardSuiteInputStrategy._resolve_devices((), tmp_path / "devices.yml") == ()
    )


def test_suite_from_inputs_resolves_tests_and_sets_mode(tmp_path):
    """Suite construction resolves inputs into executable tests and options."""
    server_test = tmp_path / "server.py"
    client_test = tmp_path / "client.py"
    server_test.touch()
    client_test.touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        devices=("shared-device",),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert suite.options.jobs == 1
    assert all(isinstance(test, Test) for test in suite.tests)
    assert [test.options.role for test in suite.tests] == ["server", "client"]
    assert [test.test_path.absolute_path for test in suite.tests] == [
        server_test,
        client_test,
    ]


def test_suite_from_inputs_sets_replicated_count(tmp_path):
    """A numeric count is recorded on the suite options, not expanded yet."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    suite = Suite.from_inputs(
        ["check.py"],
        count="3",
        devices=("board-1", "board-2", "board-3"),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert len(suite.tests) == 1
    assert suite.tests[0].device is None
    assert suite.options.count == 3


def test_suite_from_inputs_assigns_each_device_once(tmp_path):
    """Suite construction leaves device assignment to the selected runner."""
    first_test = tmp_path / "first.py"
    second_test = tmp_path / "second.py"
    first_test.touch()
    second_test.touch()

    suite = Suite.from_inputs(
        ["first.py", "second.py"],
        devices=("board-1", "address=/dev/ttyUSB0"),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert len(suite.tests) == 2
    assert [test.test_path.file_name for test in suite.tests] == [
        "first.py",
        "second.py",
    ]
    assert [test.device for test in suite.tests] == [None, None]
    assert suite.resolved_devices == (
        Device.from_string("board-1"),
        Device.from_string("address=/dev/ttyUSB0"),
    )


def test_suite_from_inputs_pairs_count_with_distinct_devices(tmp_path):
    """A repeated test keeps its count and device pool unresolved."""
    (tmp_path / "check.py").touch()

    suite = Suite.from_inputs(
        ["check.py"],
        count="2",
        devices=("board-1", "board-2"),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert len(suite.tests) == 1
    assert suite.tests[0].device is None
    assert suite.resolved_devices == (
        Device.from_string("board-1"),
        Device.from_string("board-2"),
    )
    assert suite.options.count == 2


def test_suite_from_inputs_resolves_count_devices_from_device_list(
    tmp_path, monkeypatch
):
    """A device-list query resolves the pool for repeated tests."""
    (tmp_path / "check.py").touch()
    available = [Device(name="board-1"), Device(name="board-2")]
    monkeypatch.setattr(Device, "from_file", lambda _: available)
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    suite = Suite.from_inputs(
        ["check.py"],
        count="2",
        devices=("board",),
        dev_list=tmp_path / "devices.yml",
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [test.device for test in suite.tests] == [None]
    assert suite.resolved_devices == tuple(available)


def test_suite_from_inputs_rejects_insufficient_device_list_matches(
    tmp_path, monkeypatch
):
    """Construction leaves replica capacity validation to the runner."""
    (tmp_path / "check.py").touch()
    monkeypatch.setattr(Device, "from_file", lambda _: [Device(name="board-1")])
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    suite = Suite.from_inputs(
        ["check.py"],
        count="2",
        devices=("board",),
        dev_list=tmp_path / "devices.yml",
        context=TestPathContext(working_dir=tmp_path),
    )

    assert suite.resolved_devices == (Device(name="board-1"),)


def test_suite_from_inputs_rejects_missing_devices(tmp_path):
    """Suite construction requires a device when no list is supplied."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    with pytest.raises(ValueError, match="At least one device is required"):
        Suite.from_inputs(["check.py"], context=TestPathContext(working_dir=tmp_path))


def test_role_suite_from_inputs_broadcasts_one_unqualified_device(tmp_path):
    """One unqualified device query is assigned to every role."""
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        devices=("board-1",),
        context=TestPathContext(working_dir=tmp_path),
    )

    group = suite.tests
    assert [test.device for test in group] == [
        Device.from_string("board-1"),
        Device.from_string("board-1"),
    ]


def test_role_suite_from_inputs_routes_role_qualified_devices(tmp_path):
    """Role-qualified device queries are assigned to their matching roles."""
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        devices=(
            "role=server,address=/dev/ttyUSB0",
            "role=client,address=/dev/ttyUSB1",
        ),
        context=TestPathContext(working_dir=tmp_path),
    )

    group = suite.tests
    assert [test.device for test in group] == [
        Device.from_string("address=/dev/ttyUSB0"),
        Device.from_string("address=/dev/ttyUSB1"),
    ]


def test_role_suite_from_inputs_matches_live_addresses_from_uid_list(
    tmp_path, monkeypatch
):
    """Role address queries resolve UID-only devices by their live ports."""
    (tmp_path / "uni.py").touch()
    (tmp_path / "world.py").touch()
    available = [
        Device(
            name="uni-board",
            access=DeviceAccessSerial(address="", uid="abc123"),
        ),
        Device(
            name="world-board",
            access=DeviceAccessSerial(address="", uid="def456"),
        ),
    ]
    ports = [
        type("Port", (), {"device": "/dev/ttyACM1", "serial_number": "abc123"})(),
        type("Port", (), {"device": "/dev/ttyACM0", "serial_number": "def456"})(),
    ]
    monkeypatch.setattr("ottu.device.comports", lambda: ports)
    monkeypatch.setattr(Device, "from_file", lambda _: available)

    suite = Suite.from_inputs(
        ["uni=uni.py", "world=world.py"],
        devices=(
            "role=uni,address=/dev/ttyACM1",
            "role=world,address=/dev/ttyACM0",
        ),
        dev_list=tmp_path / "devices.yaml",
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [test.device for test in suite.tests] == available


def test_role_suite_from_inputs_reserves_devices_between_roles(tmp_path, monkeypatch):
    """A device assigned to one role is unavailable to later roles."""
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()
    available = [Device(name="board-1"), Device(name="board-2")]
    monkeypatch.setattr(Device, "from_file", lambda _: available)
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        devices=("board",),
        dev_list=tmp_path / "devices.yml",
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [test.device for test in suite.tests] == available


def test_role_suite_from_inputs_rejects_insufficient_list_devices(
    tmp_path, monkeypatch
):
    """Role counts must be satisfied by distinct devices from a device list."""
    (tmp_path / "server.py").touch()
    available = [Device(name="board-1")]
    monkeypatch.setattr(Device, "from_file", lambda _: available)
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    with pytest.raises(ValueError, match="needs 2 devices"):
        Suite.from_inputs(
            ["server=server.py"],
            count="2",
            devices=("board",),
            dev_list=tmp_path / "devices.yml",
            context=TestPathContext(working_dir=tmp_path),
        )


def test_role_suite_from_inputs_rejects_missing_role_device(tmp_path):
    """Each role requires a direct device when no device list is supplied."""
    (tmp_path / "server.py").touch()

    with pytest.raises(ValueError, match="Role 'server' requires a device"):
        Suite.from_inputs(
            ["server=server.py"], context=TestPathContext(working_dir=tmp_path)
        )


def test_role_suite_from_inputs_rejects_missing_role_device_from_list(
    tmp_path, monkeypatch
):
    """A role with a device list still requires a role-specific query."""
    (tmp_path / "server.py").touch()
    monkeypatch.setattr(Device, "from_file", lambda _: [Device(name="board-1")])

    with pytest.raises(ValueError, match="needs 1 connected devices"):
        Suite.from_inputs(
            ["server=server.py"],
            dev_list=tmp_path / "devices.yml",
            context=TestPathContext(working_dir=tmp_path),
        )


def test_role_suite_from_inputs_rejects_insufficient_direct_role_devices(tmp_path):
    """Direct role inputs must provide enough devices for the role count."""
    (tmp_path / "server.py").touch()

    with pytest.raises(ValueError, match="needs 2 devices"):
        Suite.from_inputs(
            ["server=server.py"],
            devices=("board-1",),
            count="2",
            context=TestPathContext(working_dir=tmp_path),
        )


@pytest.mark.parametrize(
    "devices, message",
    [
        (("role=server,address=/dev/ttyUSB0",), "Missing device query"),
        (
            ("role=server,address=/dev/ttyUSB0", "role=server,address=/dev/ttyUSB1"),
            "more than once",
        ),
        (
            ("role=other,address=/dev/ttyUSB0", "role=client,address=/dev/ttyUSB1"),
            "Unknown role",
        ),
        (("role=server,address=/dev/ttyUSB0", "board-1"), "cannot be mixed"),
    ],
)
def test_role_suite_from_inputs_validates_role_qualified_devices(
    tmp_path, devices, message
):
    """Role-qualified devices must cover the role inputs exactly once."""
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    with pytest.raises(ValueError, match=message):
        Suite.from_inputs(
            ["server=server.py", "client=client.py"],
            devices=devices,
            context=TestPathContext(working_dir=tmp_path),
        )


def test_parse_role_devices_rejects_query_matching_multiple_roles(monkeypatch):
    """Role-device parsing rejects an ambiguous role match."""
    monkeypatch.setattr(
        RoleSuiteInputStrategy,
        "_device_roles",
        classmethod(lambda cls, device, roles: ("server", "client")),
    )

    with pytest.raises(ValueError, match="more than one role"):
        RoleSuiteInputStrategy._parse_role_devices(
            ("role=server,address=/dev/ttyUSB0",),
            ("server", "client"),
        )


def test_parse_role_devices_returns_empty_mapping_without_devices():
    """Role-device parsing leaves roles unresolved when no devices are supplied."""
    assert RoleSuiteInputStrategy._parse_role_devices((), ("server",)) == {}


def test_suite_from_inputs_sets_jobs(tmp_path):
    """Suite construction preserves the requested job limit."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    suite = Suite.from_inputs(
        ["check.py"],
        jobs=2,
        devices=("board-1", "board-2"),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert suite.options.jobs == 2


@pytest.mark.parametrize("jobs", [0, -1, True, "2"])
def test_suite_opts_rejects_invalid_jobs(jobs):
    """Suite jobs must be a positive integer rather than a coercible value."""
    with pytest.raises(ValueError, match="positive integer"):
        SuiteOpts(jobs=jobs)


def test_suite_opts_validate_jobs_accepts_positive_integer():
    """The jobs validator accepts a positive integer."""
    SuiteOpts._validate_jobs(1)


@pytest.mark.parametrize("jobs", [0, -1, True, "2"])
def test_suite_opts_validate_jobs_rejects_invalid_value(jobs):
    """The jobs validator rejects non-positive and non-integer values."""
    with pytest.raises(ValueError, match="positive integer"):
        SuiteOpts._validate_jobs(jobs)


def test_role_suite_from_inputs_rejects_jobs(tmp_path):
    """Role-based suite inputs reject explicit job parallelism."""
    test_file = tmp_path / "server.py"
    test_file.touch()

    with pytest.raises(ValueError, match="Jobs are not supported"):
        Suite.from_inputs(
            ["server=server.py"],
            jobs=2,
            context=TestPathContext(working_dir=tmp_path),
        )


def test_suite_from_inputs_raises_when_no_strategy_matches(monkeypatch):
    """The dispatcher fails loudly if every strategy rejects the raw inputs."""
    monkeypatch.setattr(
        RoleSuiteInputStrategy,
        "matches",
        classmethod(lambda cls, _: False),
    )
    monkeypatch.setattr(
        StandardSuiteInputStrategy,
        "matches",
        classmethod(lambda cls, _: False),
    )

    with pytest.raises(ValueError, match="No suite input strategy supports"):
        Suite.from_inputs([])


def test_suite_from_inputs_sets_role_counts(tmp_path, monkeypatch):
    """Role counts expand into that many tests in the shared role group."""
    server_test = tmp_path / "server.py"
    client_test = tmp_path / "client.py"
    server_test.touch()
    client_test.touch()
    available = [Device(name=f"board-{index}") for index in range(5)]
    monkeypatch.setattr(Device, "from_file", lambda _: available)
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        count="server=1,client=4",
        devices=("board",),
        dev_list=tmp_path / "devices.yml",
        context=TestPathContext(working_dir=tmp_path),
    )

    group = suite.tests
    assert [test.options.role for test in group] == [
        "server",
        "client",
        "client",
        "client",
        "client",
    ]


def test_suite_from_inputs_applies_integer_count_to_all_roles(tmp_path, monkeypatch):
    """A single integer count applies to every role."""
    server_test = tmp_path / "server.py"
    client_test = tmp_path / "client.py"
    server_test.touch()
    client_test.touch()
    available = [Device(name=f"board-{index}") for index in range(10)]
    monkeypatch.setattr(Device, "from_file", lambda _: available)
    monkeypatch.setattr(DeviceQuery, "find", lambda devices, query: list(devices))

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        count="5",
        devices=("board",),
        dev_list=tmp_path / "devices.yml",
        context=TestPathContext(working_dir=tmp_path),
    )

    group = suite.tests
    assert [test.options.role for test in group] == ["server"] * 5 + ["client"] * 5


@pytest.mark.parametrize("count", ["1,2", "server=2", "bad", "0"])
def test_suite_rejects_invalid_non_roled_counts(tmp_path, count):
    """Non-role inputs reject multiple or role-qualified counts."""
    (tmp_path / "check.py").touch()

    with pytest.raises(ValueError):
        Suite.from_inputs(
            ["check.py"],
            count=count,
            context=TestPathContext(working_dir=tmp_path),
        )


@pytest.mark.parametrize(
    "count, message",
    [
        ("server", "positive integer"),
        ("other=2", "Unknown role"),
        ("server=bad", "positive integer"),
        ("server=0", "positive integer"),
        ("server=1,server=2", "more than once"),
        ("1,server=2", "cannot mix"),
        ("1,2", "key=value"),
        ("server=2=3", "key=value"),
    ],
)
def test_suite_rejects_invalid_role_counts(tmp_path, count, message):
    """Role counts must identify each role once with a positive integer."""
    (tmp_path / "server.py").touch()

    with pytest.raises(ValueError, match=message):
        Suite.from_inputs(
            ["server=server.py"],
            count=count,
            context=TestPathContext(working_dir=tmp_path),
        )


def test_suite_rejects_role_test_pattern(tmp_path):
    """Role tests must not use wildcard patterns."""
    (tmp_path / "server.py").touch()

    with pytest.raises(ValueError, match="not a pattern"):
        Suite.from_inputs(
            ["server=*.py"], context=TestPathContext(working_dir=tmp_path)
        )


def test_suite_rejects_role_test_directory(tmp_path):
    """Role tests must resolve to a file rather than a directory."""
    (tmp_path / "server_tests").mkdir()

    with pytest.raises(ValueError, match="contains no test files"):
        Suite.from_inputs(
            ["server=server_tests"], context=TestPathContext(working_dir=tmp_path)
        )


def test_role_validation_rejects_non_file_resolved_path(monkeypatch, tmp_path):
    """Role validation rejects a resolved path that is not a file."""
    directory = tmp_path / "server_tests"
    directory.mkdir()
    resolved_path = TestPath(directory, directory, None, directory.name)
    monkeypatch.setattr(
        TestPathResolver,
        "resolve",
        staticmethod(lambda selector, context: [resolved_path]),
    )

    with pytest.raises(ValueError, match="exactly one test file"):
        RoleSuiteInputStrategy._validate_role_test_files(
            {"server": "server_tests"}, TestPathContext(working_dir=tmp_path)
        )


def test_test_suite_returns_each_test_in_order(tmp_path):
    """A suite iterates over all collected tests in order."""
    first = TestPath(tmp_path / "first.py", tmp_path / "first.py", None, "first.py")
    second = TestPath(tmp_path / "second.py", tmp_path / "second.py", None, "second.py")
    backend = Backend.from_mapping({"program": "true"})

    reports = Suite(
        SuiteOpts(),
        [
            Test(first, TestOpts(), backend=backend),
            Test(second, TestOpts(), backend=backend),
        ],
        runner="runner_sequential",
    ).run()

    assert [report.test_path.file_name for report in reports] == [
        "first.py",
        "second.py",
    ]
    assert all(report.passed for report in reports)


def test_sequential_runner_uses_one_resolved_device_for_all_tests(monkeypatch):
    """Sequential execution assigns one process device to every test."""
    device = Device(name="board-1")
    tests = [
        Test(TestPath("first.py", "first.py", None, "first.py")),
        Test(TestPath("second.py", "second.py", None, "second.py")),
    ]
    executed: list[Test] = []

    monkeypatch.setattr(
        Suite,
        "_run_test",
        staticmethod(lambda test, observer=None: executed.append(test)),
    )

    Suite(
        SuiteOpts(),
        tests,
        runner="runner_sequential",
        resolved_devices=(device,),
    ).run()

    assert [test.device for test in executed] == [device, device]


def test_suite_splits_tests_into_contiguous_jobs():
    """Multiple jobs receive balanced contiguous test groups."""
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(5)
    ]
    options = SuiteOpts()

    suite_jobs = Suite(options, tests).split(jobs=2)

    assert [suite_job.tests for suite_job in suite_jobs] == [tests[:3], tests[3:]]


def test_suite_splits_disjoint_device_groups_per_job():
    """Each repeated distributed job receives exactly its count devices."""
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(4)
    ]
    devices = tuple(Device(name=f"board-{index}") for index in range(4))

    suite_jobs = Suite(
        SuiteOpts(jobs=2, count=2),
        tests,
        resolved_devices=devices,
    ).split(jobs=2)

    assert [suite_job.resolved_devices for suite_job in suite_jobs] == [
        devices[:2],
        devices[2:],
    ]


def test_suite_rejects_insufficient_devices_for_distributed_jobs():
    """Distributed splitting rejects overlapping device assignments."""
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(2)
    ]

    with pytest.raises(ValueError, match="needs 4 devices"):
        Suite(
            SuiteOpts(jobs=2, count=2),
            tests,
            resolved_devices=(Device(name="board-1"), Device(name="board-2")),
        ).split(jobs=2)


def test_suite_does_not_split_one_job_or_one_test():
    """One job or one test stays in a single group."""
    test = Test(TestPath("test.py", "test.py", None, "test.py"))
    options = SuiteOpts()

    assert Suite(options, [test]).split(jobs=1) == [
        Suite(options, [test], runner="runner_sequential")
    ]
    assert Suite(options, []).split(jobs=2) == [
        Suite(options, [], runner="runner_sequential")
    ]


def test_suite_runs_jobs_in_parallel(monkeypatch):
    """Multiple job groups start before any job is joined."""
    events = []

    class FakeProcess:
        def __init__(self, target, args):
            self.args = args
            self.exitcode = 0

        def start(self):
            pass
            events.append(("start", self.args[0]))

        def join(self):
            events.append(("join", self.args[0]))

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(4)
    ]

    Suite(SuiteOpts(jobs=2), tests, runner="runner_distributed").run()

    assert [event[0] for event in events] == ["start", "start", "join", "join"]


def test_distributed_runner_runs_single_suite_directly(monkeypatch):
    """Distributed execution delegates directly when splitting yields one job."""
    test = Test(TestPath("test.py", "test.py", None, "test.py"))
    suite = Suite(SuiteOpts(jobs=2), [test], runner="runner_distributed")
    called = []

    monkeypatch.setattr(Suite, "split", lambda self, jobs: [self])
    monkeypatch.setattr(Suite, "run", lambda self: called.append(self) or [])

    assert suite.runner_distributed() == []
    assert called == [suite]


def test_suite_raises_when_a_job_process_fails(monkeypatch):
    """Suite execution reports a failed job process."""

    class FakeProcess:
        def __init__(self, target, args):
            self.exitcode = 1

        def start(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(2)
    ]

    with pytest.raises(RuntimeError, match="jobs failed"):
        Suite(SuiteOpts(jobs=2), tests, runner="runner_distributed").run()


def test_suite_runs_plain_tests_directly(monkeypatch):
    """A plain test with one device runs without a worker process."""
    events = []

    class FakeProcess:
        def __init__(self, target, args):
            self.args = args
            self.exitcode = 0

        def start(self):
            events.append(("start", self.args[0]))

        def join(self):
            events.append(("join", self.args[0]))

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath(Path("first.py"), Path("first.py"), None, "first.py"),
        TestOpts(),
        backend=backend,
    )

    reports = Suite(SuiteOpts(), [test], runner="runner_sequential").run()

    assert events == []
    assert [(report.test_path.file_name, report.passed) for report in reports] == [
        ("first.py", True)
    ]


def test_roled_runner_starts_requested_process_count(monkeypatch):
    """Role execution starts one process per requested role replica."""
    events = []

    class FakeProcess:
        def __init__(self, target, args):
            self.args = args
            self.exitcode = 0

        def start(self):
            events.append(("start", self.args[0]))

        def join(self):
            events.append(("join", self.args[0]))

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    server = Test(
        TestPath("server.py", "server.py", None, "server.py"),
        options=TestOpts(role="server"),
    )
    client = Test(
        TestPath("client.py", "client.py", None, "client.py"),
        options=TestOpts(role="client"),
    )

    Suite(SuiteOpts(), [server, server, client], runner="runner_parallel").run()

    assert [event[0] for event in events] == [
        "start",
        "start",
        "start",
        "join",
        "join",
        "join",
    ]
    assert [event[1] for event in events[:3]] == [server, server, client]
    assert [event[1] for event in events[3:]] == [server, server, client]


def test_repeated_runner_starts_requested_process_count(monkeypatch):
    """Repeated execution starts one process per requested replica."""
    events = []

    class FakeProcess:
        def __init__(self, target, args):
            self.args = args
            self.exitcode = 0

        def start(self):
            events.append(("start", self.args[0]))

        def join(self):
            events.append(("join", self.args[0]))

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    backend = Backend.from_mapping({"program": "true"})
    first = Test(
        TestPath("first.py", "first.py", None, "first.py"),
        TestOpts(),
        backend=backend,
    )

    Suite(
        SuiteOpts(count=2),
        [first],
        runner="runner_repeated",
        resolved_devices=(Device(name="board-1"), Device(name="board-2")),
    ).run()

    assert [event[0] for event in events] == [
        "start",
        "start",
        "join",
        "join",
    ]
    assert [event[1].test_path.file_name for event in events] == [
        "first.py",
        "first.py",
        "first.py",
        "first.py",
    ]


def test_repeated_runner_runs_each_test_file_as_a_parallel_group(monkeypatch):
    """Repeated tests run sequentially by file, with replicas running together."""
    events = []

    class FakeProcess:
        def __init__(self, target, args):
            self.args = args
            self.exitcode = 0

        def start(self):
            events.append(("start", self.args[0]))

        def join(self):
            events.append(("join", self.args[0]))

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    backend = Backend.from_mapping({"program": "true"})
    first = Test(
        TestPath("first.py", "first.py", None, "first.py"),
        TestOpts(),
        backend=backend,
    )
    second = Test(
        TestPath("second.py", "second.py", None, "second.py"),
        TestOpts(),
        backend=backend,
    )

    Suite(
        SuiteOpts(count=2),
        [first, second],
        runner="runner_repeated",
        resolved_devices=(Device(name="board-1"), Device(name="board-2")),
    ).run()

    assert [event[0] for event in events] == [
        "start",
        "start",
        "join",
        "join",
        "start",
        "start",
        "join",
        "join",
    ]
    assert [event[1].test_path.file_name for event in events] == [
        "first.py",
        "first.py",
        "first.py",
        "first.py",
        "second.py",
        "second.py",
        "second.py",
        "second.py",
    ]


def test_repeated_runner_routes_single_tests_through_a_sub_suite(monkeypatch):
    """A file with no replicas still runs through its own parallel sub-suite."""
    events = []

    class FakeProcess:
        def __init__(self, target, args):
            self.args = args
            self.exitcode = 0

        def start(self):
            events.append(("start", self.args[0]))

        def join(self):
            events.append(("join", self.args[0]))

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    backend = Backend.from_mapping({"program": "true"})
    second = Test(
        TestPath("second.py", "second.py", None, "second.py"),
        TestOpts(),
        backend=backend,
    )

    Suite(
        SuiteOpts(),
        [second],
        runner="runner_repeated",
        resolved_devices=(Device(name="board-1"),),
    ).run()

    assert [event[0] for event in events] == ["start", "join"]
    assert events[0][1].test_path.file_name == "second.py"
    assert events[0][1].device == Device(name="board-1")


def test_repeated_runner_raises_when_a_process_fails(monkeypatch):
    """Repeated execution reports a failed child process."""
    processes = []

    class FakeProcess:
        def __init__(self, target, args):
            self.exitcode = 1 if not processes else 0
            processes.append(self)

        def start(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    test = Test(
        TestPath("failed.py", "failed.py", None, "failed.py"),
        TestOpts(),
    )

    with pytest.raises(RuntimeError, match="test workers failed"):
        Suite(
            SuiteOpts(count=2),
            [test],
            runner="runner_repeated",
            resolved_devices=(Device(name="board-1"), Device(name="board-2")),
        ).run()


def test_roled_runner_raises_when_a_process_fails(monkeypatch):
    """Role execution reports a failed child process."""
    processes = []

    class FakeProcess:
        def __init__(self, target, args):
            self.exitcode = 1 if not processes else 0
            processes.append(self)

        def start(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    test = Test(
        TestPath("failed.py", "failed.py", None, "failed.py"),
        TestOpts(role="server"),
    )

    with pytest.raises(RuntimeError, match="test workers failed"):
        Suite(SuiteOpts(), [test], runner="runner_parallel").run()


def test_run_test_runs_the_given_test():
    """Running a test without an observer just executes it directly."""
    executed = []

    class FakeTest:
        def run(self):
            executed.append(True)

    Suite._run_test(FakeTest())

    assert executed == [True]


def test_run_test_queues_a_report_with_job_id():
    """Running a test with an observer publishes its labeled report."""
    published = []

    class FakeQueue:
        def put(self, report):
            published.append(report)

    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath(Path("check.py"), Path("check.py"), None, "check.py"),
        TestOpts(),
        backend=backend,
    )

    Suite._run_test(test, SuiteParallelTestReportObserver(FakeQueue(), "1"))

    assert published
    assert published[-1].job_id == "1"


def test_queue_observer_publishes_report_with_job_id():
    """The child queue observer tags reports with their job id."""
    queued = []

    class FakeQueue:
        def put(self, report):
            queued.append(report)

    report = make_report("check.py", TestStatus.BUILDING)

    SuiteParallelTestReportObserver(FakeQueue(), "1").report_changed(report)

    assert queued == [make_report("check.py", TestStatus.BUILDING, job_id="1")]


def test_run_job_queues_a_plain_test_report():
    """A plain test queues its labeled report when given an event queue."""
    published = []

    class FakeQueue:
        def put(self, report):
            published.append(report)

    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath(Path("check.py"), Path("check.py"), None, "check.py"),
        TestOpts(),
        backend=backend,
    )

    reports = Suite(SuiteOpts(), [test]).runner_sequential(
        SuiteParallelTestReportObserver(FakeQueue())
    )

    assert len(reports) == 1
    assert published
    assert all(item.test_path.file_name == "check.py" for item in published)
    assert published[-1].passed


def test_runner_repeated_queues_a_plain_test_report(monkeypatch):
    """A plain test in a repeated group queues its report via the queue."""
    published = []

    class FakeQueue:
        def put(self, report):
            published.append(report)

    class FakeProcess:
        def __init__(self, target, args):
            self._target = target
            self._args = args
            self.exitcode = 0

        def start(self):
            self._target(*self._args)

        def join(self):
            pass

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath(Path("check.py"), Path("check.py"), None, "check.py"),
        TestOpts(),
        backend=backend,
    )

    reports = Suite(
        SuiteOpts(),
        [test],
        runner="runner_repeated",
        resolved_devices=(Device(name="board-1"),),
    ).runner_repeated(SuiteParallelTestReportObserver(FakeQueue()))

    assert reports == []
    assert published
    assert all(item.test_path.file_name == "check.py" for item in published)
    assert published[-1].passed


def test_run_parallel_processes_drains_live_reports():
    """Live parallel execution drains notifications while workers are running."""

    class FakeProcess:
        exitcode = 0

        def start(self):
            pass

        def join(self):
            pass

    class FakeNotifier:
        def __init__(self):
            self.running = True
            self.notifications = 0

        @property
        def processes_running(self):
            return self.running

        def register_process(self, process):
            pass

        def notify(self):
            self.notifications += 1
            self.running = False
            return []

    notifier = FakeNotifier()

    assert Suite.run_parallel_processes([FakeProcess()], notifier) == []
    assert notifier.notifications == 2


def test_suite_parallel_notifier_tracks_registered_processes():
    """The notifier reports whether registered processes are running."""

    class FakeProcess:
        def __init__(self, running):
            self.running = running

        def is_alive(self):
            return self.running

    notifier = SuiteParallelTestReportNotifier()
    notifier.register_process(FakeProcess(False))
    assert not notifier.processes_running

    notifier.register_process(FakeProcess(True))
    assert notifier.processes_running


def test_suite_parallel_notifier_queues_labeled_report():
    """The notifier forwards labeled reports to final observers."""

    class FakeQueue:
        def __init__(self, report):
            self.report = report

        def get_nowait(self):
            if self.report is None:
                raise queue.Empty
            report = self.report
            self.report = None
            return report

    class RecordingObserver:
        def __init__(self):
            self.reports = []

        def report_changed(self, report):
            self.reports.append(report)

    report = make_report("check.py", TestStatus.BUILDING)
    recording_observer = RecordingObserver()
    notifier = SuiteParallelTestReportNotifier(
        (recording_observer,),
        event_queue=FakeQueue(replace(report, job_id="1")),
    )
    notifier.notify()

    assert recording_observer.reports == [
        make_report("check.py", TestStatus.BUILDING, job_id="1")
    ]
