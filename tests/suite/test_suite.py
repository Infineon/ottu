"""Tests for the suite and its execution modes."""

from pathlib import Path

import pytest
from ottu.backend import Backend
from ottu.device import (
    Device,
    DeviceAccessSerial,
)
from ottu.report import QueueTestReportObserver, TestReport
from ottu.suite import (
    RoleCount,
    Suite,
    SuiteDistributed,
    SuiteOpts,
    SuiteReplicated,
    SuiteRole,
    SuiteSequential,
)
from ottu.test import Test, TestOpts, TestPath


def make_suite(*, kind=SuiteSequential, devices=(), **values):
    """Create a suite of the given class that already shares these devices."""
    values.setdefault("device_pool", {None: tuple(devices)})
    return kind(**values)


def make_report(name, status):
    path = TestPath(name, name, None, name)
    return TestReport(path, status)


def test_suite_is_abstract():
    with pytest.raises(TypeError, match="abstract"):
        Suite()


def test_suite_distributed_assigns_the_devices_the_jobs_share_out(monkeypatch):
    offline = catalog_device("offline", "/dev/ttyUSB0")
    boards = [
        catalog_device(f"board-{index}", f"/dev/ttyUSB{index}") for index in (1, 2, 3)
    ]
    monkeypatch.setattr(Device, "is_connected", lambda self: self.name != "offline")

    booked = SuiteDistributed(
        tests=[request_test("a.py"), request_test("b.py")],
        options=SuiteOpts(jobs=2, count=1),
        device_pool={None: (offline, *boards)},
    )._book_devices()

    assert booked == boards[:2]


def test_suite_distributed_rejects_too_few_connected_devices(monkeypatch):
    monkeypatch.setattr(Device, "is_connected", lambda self: True)

    with pytest.raises(ValueError, match="needs 4 connected devices, but only 2"):
        SuiteDistributed(
            tests=[request_test("a.py"), request_test("b.py")],
            options=SuiteOpts(jobs=2, count=2),
            device_pool={None: (Device(name="a"), Device(name="b"))},
        )._book_devices()


def test_suite_role_books_distinct_devices_per_role(monkeypatch):
    offline = catalog_device("offline", "/dev/ttyUSB0")
    server = catalog_device("server-board", "/dev/ttyUSB1")
    client_a = catalog_device("client-a", "/dev/ttyUSB2")
    client_b = catalog_device("client-b", "/dev/ttyUSB3")
    monkeypatch.setattr(Device, "is_connected", lambda self: self.name != "offline")

    booked = SuiteRole(
        tests=[
            request_test("server.py", role="server"),
            request_test("client.py", role="client"),
        ],
        options=SuiteOpts(count=(RoleCount(role="client", count=2),)),
        device_pool={
            "server": (offline, server),
            "client": (client_a, client_b),
        },
    )._book_devices()

    assert booked == [server, client_a, client_b]


def test_suite_role_rejects_a_role_with_too_few_connected_devices(monkeypatch):
    monkeypatch.setattr(Device, "is_connected", lambda self: False)

    with pytest.raises(ValueError, match="Role 'server' needs 1 connected devices"):
        SuiteRole(
            tests=[request_test("server.py", role="server")],
            device_pool={"server": (catalog_device("offline", "/dev/ttyUSB0"),)},
        )._book_devices()


def test_suite_role_does_not_share_devices_between_roles(monkeypatch):
    monkeypatch.setattr(Device, "is_connected", lambda self: True)
    shared = Device(name="shared")

    with pytest.raises(ValueError, match="Role 'client' needs 1 connected devices"):
        SuiteRole(
            tests=[
                request_test("server.py", role="server"),
                request_test("client.py", role="client"),
            ],
            device_pool={"server": (shared,), "client": (shared,)},
        )._book_devices()


def test_suite_role_rejects_tests_without_a_role():
    with pytest.raises(ValueError, match="must have a role"):
        SuiteRole(tests=[request_test("plain.py")])._book_devices()


def test_suite_role_runs_every_replica_as_one_group_on_its_role_devices(monkeypatch):
    groups = []
    monkeypatch.setattr(
        Suite,
        "_run_concurrently",
        lambda self, tests, observer=None: groups.append((list(tests), observer)) or [],
    )
    server = Device(name="server-board")
    client_a = Device(name="client-a")
    client_b = Device(name="client-b")
    suite = SuiteRole(
        tests=[
            request_test("server.py", role="server"),
            request_test("client.py", role="client"),
        ],
        options=SuiteOpts(count=(RoleCount(role="client", count=2),)),
    )
    observer = object()

    assert suite._runner([server, client_a, client_b], observer) == []

    ((replicas, forwarded),) = groups
    assert forwarded is observer
    assert [(test.options.role, test.device) for test in replicas] == [
        ("server", server),
        ("client", client_a),
        ("client", client_b),
    ]


def test_suite_sequential_books_one_connected_device(monkeypatch):
    unavailable = catalog_device("offline", "/dev/ttyUSB0")
    selected = catalog_device("selected", "/dev/ttyUSB1")
    spare = catalog_device("spare", "/dev/ttyUSB2")
    monkeypatch.setattr(
        Device,
        "is_connected",
        lambda self: self.name != "offline",
    )

    booked = SuiteSequential(
        tests=[request_test("a.py"), request_test("b.py")],
        device_pool={None: (unavailable, selected, spare)},
    )._book_devices()

    assert booked == [selected]


def test_suite_sequential_does_not_book_a_device_without_hardware_access():
    with pytest.raises(ValueError, match="needs 1 connected devices, but only 0"):
        SuiteSequential(
            tests=[request_test("a.py")],
            device_pool={None: (Device(name="board-1"),)},
        )._book_devices()


def test_suite_sequential_rejects_an_empty_connected_pool(monkeypatch):
    monkeypatch.setattr(Device, "is_connected", lambda self: False)

    with pytest.raises(ValueError, match="needs 1 connected devices"):
        SuiteSequential(
            tests=[request_test("a.py")],
            device_pool={None: (catalog_device("offline", "/dev/ttyUSB0"),)},
        )._book_devices()


def test_suite_sequential_runs_every_test_in_order_on_the_first_device(monkeypatch):
    tests = [request_test("first.py"), request_test("second.py")]
    executed = []
    monkeypatch.setattr(
        Suite,
        "_run_test",
        staticmethod(lambda test, observer=None: executed.append(test)),
    )
    device = Device(name="board-1")

    reports = SuiteSequential(tests=tests)._runner([device, Device(name="board-2")])

    assert reports == [None, None]
    assert [test.test_path.file_name for test in executed] == ["first.py", "second.py"]
    assert [test.device for test in executed] == [device, device]


def test_suite_sequential_runs_tests_unchanged_without_devices(monkeypatch):
    tests = [request_test("first.py")]
    executed = []
    monkeypatch.setattr(
        Suite,
        "_run_test",
        staticmethod(lambda test, observer=None: executed.append(test)),
    )

    SuiteSequential(tests=tests)._runner([])

    assert executed == tests


def test_suite_sequential_runner_forwards_the_observer(monkeypatch):
    observers = []
    monkeypatch.setattr(
        Suite,
        "_run_test",
        staticmethod(lambda test, observer=None: observers.append(observer)),
    )
    observer = object()

    SuiteSequential(tests=[request_test("a.py")])._runner([], observer)

    assert observers == [observer]


def test_suite_replicated_books_count_connected_devices(monkeypatch):
    offline = catalog_device("offline", "/dev/ttyUSB0")
    first = catalog_device("first", "/dev/ttyUSB1")
    second = catalog_device("second", "/dev/ttyUSB2")
    spare = catalog_device("spare", "/dev/ttyUSB3")
    monkeypatch.setattr(Device, "is_connected", lambda self: self.name != "offline")

    booked = SuiteReplicated(
        tests=[request_test("a.py"), request_test("b.py")],
        options=SuiteOpts(count=2),
        device_pool={None: (offline, first, second, spare)},
    )._book_devices()

    assert booked == [first, second]


def test_suite_replicated_rejects_too_few_connected_devices(monkeypatch):
    monkeypatch.setattr(Device, "is_connected", lambda self: False)

    with pytest.raises(ValueError, match="needs 2 connected devices, but only 0"):
        SuiteReplicated(
            tests=[request_test("a.py")],
            options=SuiteOpts(count=2),
            device_pool={
                None: (
                    catalog_device("a", "/dev/ttyUSB0"),
                    catalog_device("b", "/dev/ttyUSB1"),
                )
            },
        )._book_devices()


def test_suite_replicated_runs_each_tests_replicas_on_distinct_devices(monkeypatch):
    groups = []
    monkeypatch.setattr(
        Suite,
        "_run_concurrently",
        lambda self, tests, observer=None: (
            groups.append(
                ([(test.test_path.file_name, test.device) for test in tests], observer)
            )
            or []
        ),
    )
    first = Device(name="first")
    second = Device(name="second")
    observer = object()
    suite = SuiteReplicated(
        tests=[request_test("a.py"), request_test("b.py")],
        options=SuiteOpts(count=2),
    )

    assert suite._runner([first, second], observer) == []
    assert groups == [
        ([("a.py", first), ("a.py", second)], observer),
        ([("b.py", first), ("b.py", second)], observer),
    ]


def test_suite_distributed_jobs_get_their_own_devices():
    devices = (Device(name="board-1"), Device(name="board-2"))
    suite = SuiteDistributed(
        tests=[request_test("a.py"), request_test("b.py")],
        options=SuiteOpts(jobs=2, count=2),
    )

    ((job, job_devices),) = suite._split(1, devices)

    assert isinstance(job, SuiteReplicated)
    assert job_devices == devices


def test_assign_devices_pairs_replicas_with_distinct_devices():
    """Each replica is paired one-to-one with a distinct device when able."""
    test = Test(TestPath("check.py", "check.py", None, "check.py"))

    tests = Suite._assign_devices(
        [test], (Device(name="board-1"), Device(name="board-2")), 2
    )

    assert [t.device.name for t in tests if t.device] == ["board-1", "board-2"]


def test_assign_devices_rejects_insufficient_devices_for_replicas():
    """Replicas must not exceed the number of devices supplied."""
    test = Test(TestPath("check.py", "check.py", None, "check.py"))

    with pytest.raises(ValueError, match="needs 2 devices"):
        Suite._assign_devices([test], (Device(name="board-1"),), 2)


def test_assign_devices_rejects_missing_device_for_replica():
    """Assignment requires a device for every replica."""
    test = Test(TestPath("check.py", "check.py", None, "check.py"))

    with pytest.raises(ValueError, match="needs 1 devices"):
        Suite._assign_devices([test], ())


def test_assign_devices_rejects_missing_devices_for_replicas():
    """Assignment requires a distinct device for every replica."""
    test = Test(TestPath("check.py", "check.py", None, "check.py"))

    with pytest.raises(ValueError, match="needs 2 devices"):
        Suite._assign_devices([test], (), required_count=2)


@pytest.mark.parametrize("jobs", [0, -1, True, "2"])
def test_suite_opts_rejects_invalid_jobs(jobs):
    """Suite jobs must be a positive integer rather than a coercible value."""
    with pytest.raises(ValueError, match="positive integer"):
        SuiteOpts(jobs=jobs)


@pytest.mark.parametrize("count", [0, -1])
def test_suite_opts_rejects_non_positive_counts(count):
    with pytest.raises(ValueError, match="Suite count must be a positive integer"):
        SuiteOpts(count=count)


@pytest.mark.parametrize("count", [(), True, "2", 1.5])
def test_suite_opts_rejects_counts_that_are_neither_integers_nor_role_counts(count):
    with pytest.raises(ValueError, match="positive integer or role counts"):
        SuiteOpts(count=count)


def test_suite_opts_rejects_role_counts_of_the_wrong_type():
    with pytest.raises(TypeError, match="must be RoleCount values"):
        SuiteOpts(count=("server",))


def test_suite_opts_rejects_a_role_count_given_twice():
    count = (RoleCount(role="server", count=1), RoleCount(role="server", count=2))

    with pytest.raises(ValueError, match="provided more than once"):
        SuiteOpts(count=count)


def test_suite_opts_validate_jobs_accepts_positive_integer():
    """The jobs validator accepts a positive integer."""
    SuiteOpts._validate_jobs(1)


@pytest.mark.parametrize("jobs", [0, -1, True, "2"])
def test_suite_opts_validate_jobs_rejects_invalid_value(jobs):
    """The jobs validator rejects non-positive and non-integer values."""
    with pytest.raises(ValueError, match="positive integer"):
        SuiteOpts._validate_jobs(jobs)


@pytest.mark.usefixtures("fake_devices_connected")
def test_test_suite_returns_each_test_in_order(tmp_path):
    """A suite iterates over all collected tests in order."""
    first = TestPath(tmp_path / "first.py", tmp_path / "first.py", None, "first.py")
    second = TestPath(tmp_path / "second.py", tmp_path / "second.py", None, "second.py")
    backend = Backend.from_mapping({"program": "true"})

    reports = make_suite(
        options=SuiteOpts(),
        tests=[
            Test(first, TestOpts(), backend=backend),
            Test(second, TestOpts(), backend=backend),
        ],
        kind=SuiteSequential,
        device_pool={None: (Device(name="board-1"),)},
    ).run()

    assert [report.test_path.file_name for report in reports] == [
        "first.py",
        "second.py",
    ]
    assert all(report.passed for report in reports)


def test_sequential_runner_uses_one_resolved_device_for_all_tests(monkeypatch):
    """Sequential execution assigns one process device to every test."""
    monkeypatch.setattr(Device, "is_connected", lambda self: True)
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

    make_suite(
        options=SuiteOpts(), tests=tests, kind=SuiteSequential, devices=(device,)
    ).run()

    assert [test.device for test in executed] == [device, device]


def test_suite_splits_tests_into_contiguous_jobs():
    """Multiple jobs receive balanced contiguous test groups."""
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(5)
    ]
    options = SuiteOpts()

    suite_jobs = SuiteDistributed(options=options, tests=tests)._split(2, [])

    assert [suite_job.tests for suite_job, _ in suite_jobs] == [tests[:3], tests[3:]]


def test_suite_splits_disjoint_device_groups_per_job():
    """Each replicated distributed job receives exactly its count devices."""
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(4)
    ]
    devices = tuple(Device(name=f"board-{index}") for index in range(4))

    suite_jobs = SuiteDistributed(
        options=SuiteOpts(jobs=2, count=2),
        tests=tests,
    )._split(2, devices)

    assert [job_devices for _, job_devices in suite_jobs] == [
        devices[:2],
        devices[2:],
    ]
    assert all(isinstance(suite_job, SuiteReplicated) for suite_job, _ in suite_jobs)


def test_suite_rejects_insufficient_devices_for_distributed_jobs():
    """Distributed splitting rejects overlapping device assignments."""
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(2)
    ]

    with pytest.raises(ValueError, match="needs 4 devices"):
        SuiteDistributed(
            options=SuiteOpts(jobs=2, count=2),
            tests=tests,
        )._split(2, (Device(name="board-1"), Device(name="board-2")))


def test_suite_does_not_split_one_job_or_one_test():
    """One job or one test stays in a single group with every device."""
    test = Test(TestPath("test.py", "test.py", None, "test.py"))
    options = SuiteOpts()
    devices = (Device(name="board-1"),)

    assert SuiteDistributed(options=options, tests=[test])._split(1, devices) == [
        (SuiteSequential(options=options, tests=[test]), devices)
    ]
    assert SuiteDistributed(options=options, tests=[])._split(2, devices) == [
        (SuiteSequential(options=options, tests=[]), devices)
    ]


@pytest.mark.usefixtures("fake_devices_connected")
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(4)
    ]

    make_suite(
        options=SuiteOpts(jobs=2),
        tests=tests,
        kind=SuiteDistributed,
        device_pool={None: (Device(name="a"), Device(name="b"))},
    ).run()

    assert [event[0] for event in events] == ["start", "start", "join", "join"]


def test_distributed_runner_runs_single_suite_directly(monkeypatch):
    """Distributed execution delegates directly when splitting yields one job."""
    test = Test(TestPath("test.py", "test.py", None, "test.py"))
    suite = make_suite(options=SuiteOpts(jobs=2), tests=[test], kind=SuiteDistributed)
    single = SuiteSequential(options=SuiteOpts(), tests=[test])
    device = Device(name="board-1")
    called = []

    monkeypatch.setattr(
        SuiteDistributed, "_split", lambda self, jobs, devices: [(single, devices)]
    )
    monkeypatch.setattr(
        SuiteSequential,
        "_runner",
        lambda self, devices, observer=None: (
            called.append((self, devices, observer)) or []
        ),
    )
    observer = object()

    assert suite._runner([device], observer) == []
    assert called == [(single, [device], observer)]


@pytest.mark.usefixtures("fake_devices_connected")
def test_suite_raises_when_a_job_process_fails(monkeypatch):
    """Suite execution reports a failed job process."""

    class FakeProcess:
        def __init__(self, target, args):
            self.exitcode = 1

        def start(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(2)
    ]

    with pytest.raises(RuntimeError, match="jobs failed"):
        make_suite(
            options=SuiteOpts(jobs=2),
            tests=tests,
            kind=SuiteDistributed,
            device_pool={None: (Device(name="a"), Device(name="b"))},
        ).run()


@pytest.mark.usefixtures("fake_devices_connected")
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath(Path("first.py"), Path("first.py"), None, "first.py"),
        TestOpts(),
        backend=backend,
    )

    reports = make_suite(
        options=SuiteOpts(),
        tests=[test],
        kind=SuiteSequential,
        device_pool={None: (Device(name="board-1"),)},
    ).run()

    assert events == []
    assert [(report.test_path.file_name, report.passed) for report in reports] == [
        ("first.py", True)
    ]


@pytest.mark.usefixtures("fake_devices_connected")
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    server = Test(
        TestPath("server.py", "server.py", None, "server.py"),
        options=TestOpts(role="server"),
    )
    client = Test(
        TestPath("client.py", "client.py", None, "client.py"),
        options=TestOpts(role="client"),
    )

    make_suite(
        options=SuiteOpts(),
        tests=[server, server, client],
        kind=SuiteRole,
        device_pool={
            "server": (Device(name="server"),),
            "client": (Device(name="client"),),
        },
    ).run()

    assert [event[0] for event in events] == [
        "start",
        "start",
        "start",
        "join",
        "join",
        "join",
    ]
    expected = [("server", "server"), ("server", "server"), ("client", "client")]
    assert [(test.options.role, test.device.name) for _, test in events[:3]] == expected
    assert [(test.options.role, test.device.name) for _, test in events[3:]] == expected


def test_replicated_runner_starts_requested_process_count(monkeypatch):
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    monkeypatch.setattr(Device, "is_connected", lambda self: True)
    backend = Backend.from_mapping({"program": "true"})
    first = Test(
        TestPath("first.py", "first.py", None, "first.py"),
        TestOpts(),
        backend=backend,
    )

    make_suite(
        options=SuiteOpts(count=2),
        tests=[first],
        kind=SuiteReplicated,
        devices=(Device(name="board-1"), Device(name="board-2")),
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


def test_replicated_runner_runs_each_test_file_as_a_parallel_group(monkeypatch):
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    monkeypatch.setattr(Device, "is_connected", lambda self: True)
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

    make_suite(
        options=SuiteOpts(count=2),
        tests=[first, second],
        kind=SuiteReplicated,
        devices=(Device(name="board-1"), Device(name="board-2")),
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


def test_replicated_runner_routes_single_tests_through_a_sub_suite(monkeypatch):
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    monkeypatch.setattr(Device, "is_connected", lambda self: True)
    backend = Backend.from_mapping({"program": "true"})
    second = Test(
        TestPath("second.py", "second.py", None, "second.py"),
        TestOpts(),
        backend=backend,
    )

    make_suite(
        options=SuiteOpts(),
        tests=[second],
        kind=SuiteReplicated,
        devices=(Device(name="board-1"),),
    ).run()

    assert [event[0] for event in events] == ["start", "join"]
    assert events[0][1].test_path.file_name == "second.py"
    assert events[0][1].device == Device(name="board-1")


def test_replicated_runner_raises_when_a_process_fails(monkeypatch):
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    monkeypatch.setattr(Device, "is_connected", lambda self: True)
    test = Test(
        TestPath("failed.py", "failed.py", None, "failed.py"),
        TestOpts(),
    )

    with pytest.raises(RuntimeError, match="test workers failed"):
        make_suite(
            options=SuiteOpts(count=2),
            tests=[test],
            kind=SuiteReplicated,
            devices=(Device(name="board-1"), Device(name="board-2")),
        ).run()


@pytest.mark.usefixtures("fake_devices_connected")
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    test = Test(
        TestPath("failed.py", "failed.py", None, "failed.py"),
        TestOpts(role="server"),
    )

    with pytest.raises(RuntimeError, match="test workers failed"):
        make_suite(
            options=SuiteOpts(),
            tests=[test],
            kind=SuiteRole,
            device_pool={"server": (Device(name="server"),)},
        ).run()


def test_run_test_runs_the_given_test():
    """Running a test without an observer just executes it directly."""
    executed = []

    class FakeTest:
        def run(self):
            executed.append(True)

    Suite._run_test(FakeTest())

    assert executed == [True]


def test_run_test_queues_a_report_through_the_observer():
    """Running a test with an observer publishes its report."""
    published = []

    class FakeQueue:
        def put(self, report):
            published.append(report)

    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath(Path("check.py"), Path("check.py"), None, "check.py"),
        TestOpts(),
        device=Device(name="board-1"),
        backend=backend,
    )

    Suite._run_test(test, QueueTestReportObserver(FakeQueue()))

    assert published
    assert published[-1].passed


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

    reports = SuiteSequential(options=SuiteOpts(), tests=[test])._runner(
        [Device(name="board-1")], QueueTestReportObserver(FakeQueue())
    )

    assert len(reports) == 1
    assert published
    assert all(item.test_path.file_name == "check.py" for item in published)
    assert published[-1].passed


def test_replicated_runner_queues_a_plain_test_report(monkeypatch):
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

    monkeypatch.setattr("ottu.suite.suite.Process", FakeProcess)
    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath(Path("check.py"), Path("check.py"), None, "check.py"),
        TestOpts(),
        backend=backend,
    )

    suite = SuiteReplicated(options=SuiteOpts(), tests=[test])

    reports = suite._runner(
        [Device(name="board-1")], QueueTestReportObserver(FakeQueue())
    )

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

    class FakeRelay:
        def __init__(self):
            self.running = True
            self.notifications = 0

        @property
        def processes_running(self):
            return self.running

        def register_process(self, process):
            pass

        def forward(self):
            self.notifications += 1
            self.running = False
            return []

    relay = FakeRelay()

    assert Suite._run_parallel_processes([FakeProcess()], relay) == []
    assert relay.notifications == 2


class RecordingObserver:
    def __init__(self, events):
        self.events = events

    def suite_started(self, report):
        self.events.append(("suite_started", report))

    def report_changed(self, report):
        self.events.append(("report_changed", report))


@pytest.mark.usefixtures("fake_devices_connected")
def test_suite_run_notifies_observers_with_acquired_devices_before_tests(monkeypatch):
    """Observers hear about the suite after acquisition, before any test runs."""
    events = []
    acquired = Device(name="acquired")
    monkeypatch.setattr(Device, "acquire", lambda self: acquired)
    path = TestPath(Path("a.py"), Path("a.py"), None, "a.py")
    test = Test(path, device=Device(name="requested"))
    suite = make_suite(
        options=SuiteOpts(),
        tests=[test],
        kind=SuiteSequential,
        name="smoke",
        observers=(RecordingObserver(events),),
        device_pool={None: (Device(name="requested"),)},
    )
    monkeypatch.setattr(
        SuiteSequential,
        "_runner",
        lambda self, devices, observer=None: events.append(("runner", devices)) or [],
    )

    suite.run()

    assert [event[0] for event in events] == ["suite_started", "runner"]
    report = events[0][1]
    assert report.name == "smoke"
    assert report.devices == (acquired,)
    assert report.test_paths == (path,)
    assert events[1][1] == [acquired]


@pytest.mark.usefixtures("fake_devices_connected")
def test_suite_run_skips_observers_without_suite_events():
    class ReportOnly:
        def report_changed(self, report):
            raise AssertionError("not a test event")

    make_suite(
        options=SuiteOpts(),
        tests=[],
        kind=SuiteSequential,
        observers=(ReportOnly(),),
        device_pool={None: (Device(name="board-1"),)},
    ).run()


def request_test(name, role=None):
    return Test(
        TestPath(Path(name), Path(name), None, name),
        options=TestOpts(role=role),
    )


def catalog_device(name, port):
    return Device(name=name, access=DeviceAccessSerial(address=port))
