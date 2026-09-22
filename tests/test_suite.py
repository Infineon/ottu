"""Tests for suite input classification."""

import queue

import pytest
from ottu.backend import Backend
from ottu.result import TestResult, TestStatus
from ottu.suite import (
    RoleSuiteInputStrategy,
    StandardSuiteInputStrategy,
    Suite,
    SuiteInputStrategy,
    SuiteOpts,
    SuiteParallelObserver,
    SuiteParallelResult,
    _queued_test,
    _QueueObserver,
)
from ottu.test import Test, TestOpts, TestPath, TestPathContext, TestPathResolver


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


def test_suite_from_inputs_resolves_tests_and_sets_mode(tmp_path):
    """Suite construction resolves inputs into executable tests and options."""
    server_test = tmp_path / "server.py"
    client_test = tmp_path / "client.py"
    server_test.touch()
    client_test.touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
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
    """A numeric count selects repeated execution for plain tests."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    suite = Suite.from_inputs(
        ["check.py"], count="3", context=TestPathContext(working_dir=tmp_path)
    )

    assert [test.options.count for test in suite.tests] == [3]


def test_suite_from_inputs_expands_tests_for_each_device(tmp_path):
    """Suite construction creates one test for each test/device pair."""
    first_test = tmp_path / "first.py"
    second_test = tmp_path / "second.py"
    first_test.touch()
    second_test.touch()

    suite = Suite.from_inputs(
        ["first.py", "second.py"],
        devices=("board-1", "port=/dev/ttyUSB0,baud=9600"),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert len(suite.tests) == 4
    assert [test.test_path.file_name for test in suite.tests] == [
        "first.py",
        "first.py",
        "second.py",
        "second.py",
    ]
    assert [test.device for test in suite.tests] == [
        "board-1",
        "port=/dev/ttyUSB0,baud=9600",
        "board-1",
        "port=/dev/ttyUSB0,baud=9600",
    ]


def test_suite_from_inputs_without_devices_keeps_one_test_per_file(tmp_path):
    """Suite construction does not duplicate tests when no device is given."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    suite = Suite.from_inputs(
        ["check.py"],
        context=TestPathContext(working_dir=tmp_path),
    )

    assert len(suite.tests) == 1
    assert suite.tests[0].device is None


def test_role_suite_from_inputs_broadcasts_one_unqualified_device(tmp_path):
    """One unqualified device query is assigned to every role."""
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        devices=("board-1",),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [test.device for test in suite.tests] == ["board-1", "board-1"]


def test_role_suite_from_inputs_routes_role_qualified_devices(tmp_path):
    """Role-qualified device queries are assigned to their matching roles."""
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        devices=(
            "role=server,port=/dev/ttyUSB0",
            "role=client,port=/dev/ttyUSB1",
        ),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [test.device for test in suite.tests] == [
        "role=server,port=/dev/ttyUSB0",
        "role=client,port=/dev/ttyUSB1",
    ]


@pytest.mark.parametrize(
    "devices, message",
    [
        (("role=server,port=/dev/ttyUSB0",), "Missing device query"),
        (
            ("role=server,port=/dev/ttyUSB0", "role=server,port=/dev/ttyUSB1"),
            "more than once",
        ),
        (
            ("role=other,port=/dev/ttyUSB0", "role=client,port=/dev/ttyUSB1"),
            "Unknown role",
        ),
        (("role=server,port=/dev/ttyUSB0", "board-1"), "cannot be mixed"),
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
            ("role=server,port=/dev/ttyUSB0",),
            ("server", "client"),
        )


def test_suite_from_inputs_sets_jobs(tmp_path):
    """Suite construction preserves the requested job limit."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    suite = Suite.from_inputs(
        ["check.py"], jobs=2, context=TestPathContext(working_dir=tmp_path)
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


def test_suite_from_inputs_sets_role_counts(tmp_path):
    """Role counts are stored on their matching tests."""
    server_test = tmp_path / "server.py"
    client_test = tmp_path / "client.py"
    server_test.touch()
    client_test.touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        count="server=1,client=4",
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [test.options.count for test in suite.tests] == [1, 4]


def test_suite_from_inputs_applies_integer_count_to_all_roles(tmp_path):
    """A single integer count applies to every role."""
    server_test = tmp_path / "server.py"
    client_test = tmp_path / "client.py"
    server_test.touch()
    client_test.touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        count="5",
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [test.options.count for test in suite.tests] == [5, 5]


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

    results = Suite(
        SuiteOpts(),
        [
            Test(first, TestOpts(), backend=backend),
            Test(second, TestOpts(), backend=backend),
        ],
    ).run()

    assert [result.test_name for result in results] == ["first.py", "second.py"]
    assert all(result.passed for result in results)


def test_suite_splits_tests_into_contiguous_jobs():
    """Multiple jobs receive balanced contiguous test groups."""
    tests = [
        Test(TestPath(f"test-{index}.py", f"test-{index}.py", None, "test.py"))
        for index in range(5)
    ]
    options = SuiteOpts()

    suite_jobs = Suite(options, tests).split(jobs=2)

    assert [suite_job.tests for suite_job in suite_jobs] == [tests[:3], tests[3:]]


def test_suite_does_not_split_one_job_or_one_test():
    """One job or one test stays in a single group."""
    test = Test(TestPath("test.py", "test.py", None, "test.py"))
    options = SuiteOpts()

    assert Suite(options, [test]).split(jobs=1) == [Suite(options, [test])]
    assert Suite(options, []).split(jobs=2) == [Suite(options, [])]


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

    Suite(SuiteOpts(jobs=2), tests).run()

    assert [event[0] for event in events] == ["start", "start", "join", "join"]


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
        Suite(SuiteOpts(jobs=2), tests).run()


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
        TestPath("first.py", "first.py", None, "first.py"),
        TestOpts(),
        backend=backend,
    )

    results = Suite(SuiteOpts(), [test]).run()

    assert events == []
    assert [(result.test_name, result.passed) for result in results] == [
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
        options=TestOpts(role="server", count=2),
    )
    client = Test(
        TestPath("client.py", "client.py", None, "client.py"),
        options=TestOpts(role="client", count=1),
    )

    Suite(SuiteOpts(), [server, client]).run()

    assert [event[0] for event in events] == [
        "start",
        "start",
        "join",
        "join",
        "start",
        "join",
    ]
    assert [event[1] for event in events[:3]] == [server, server, server]
    assert events[4][1] is client


def test_repeated_runner_starts_requested_process_count(monkeypatch):
    """Repeated execution starts one process per test repeat."""
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
        TestOpts(count=2),
        backend=backend,
    )
    second = Test(
        TestPath("second.py", "second.py", None, "second.py"),
        TestOpts(count=1),
        backend=backend,
    )

    Suite(SuiteOpts(), [first, second]).run()

    assert [event[0] for event in events] == ["start", "start", "join", "join"]
    assert [event[1] for event in events[:2]] == [first, first]


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
        TestOpts(count=2),
    )

    with pytest.raises(RuntimeError, match="test workers failed"):
        Suite(SuiteOpts(), [test]).run()


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
        Suite(SuiteOpts(), [test]).run()


def test_suite_job_test_process_runs_the_given_test():
    """The job's process target delegates execution to its test."""
    executed = []

    class FakeTest:
        def run(self):
            executed.append(True)

    Suite._run_test_in_process(FakeTest())

    assert executed == [True]


def test_suite_job_test_process_queues_the_given_test(monkeypatch):
    """The job process target wraps tests when given an event queue."""
    executed = []

    class FakeTest:
        def run(self):
            executed.append(True)

    class FakeQueuedTest:
        def run(self):
            executed.append(True)

    monkeypatch.setattr(
        "ottu.suite._queued_test",
        lambda test, event_queue, label: FakeQueuedTest(),
    )

    Suite._run_test_in_process(FakeTest(), object(), "check.py [1]")

    assert executed == [True]


def test_queue_observer_publishes_labeled_result():
    """The child queue observer wraps results with its execution label."""
    queued = []

    class FakeQueue:
        def put(self, result):
            queued.append(result)

    result = TestResult("check.py", TestStatus.BUILDING)

    _QueueObserver(FakeQueue(), "check.py [1]").result_changed(result)

    assert queued == [SuiteParallelResult(result, "check.py [1]")]


def test_run_job_queues_a_plain_test_result():
    """A plain test queues its labeled result when given an event queue."""
    published = []

    class FakeQueue:
        def put(self, result):
            published.append(result)

    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath("check.py", "check.py", None, "check.py"),
        TestOpts(),
        backend=backend,
    )

    results = Suite(SuiteOpts(), [test]).run_job(FakeQueue())

    assert results == []
    assert published
    assert all(item.execution_name == "check.py" for item in published)
    assert published[-1].result.passed


def test_queued_test_wraps_test_with_a_queue_observer():
    """The queued test wrapper preserves fields and adds a queue observer."""
    backend = Backend.from_mapping({"program": "true"})
    test = Test(
        TestPath("check.py", "check.py", None, "check.py"),
        TestOpts(),
        device="board-1",
        backend=backend,
    )

    wrapped = _queued_test(test, object(), "check.py [1]")

    assert wrapped.test_path is test.test_path
    assert wrapped.options is test.options
    assert wrapped.device == "board-1"
    assert wrapped.backend is backend
    assert len(wrapped.observers) == 1
    assert isinstance(wrapped.observers[0], _QueueObserver)


def test_suite_parallel_observer_tracks_registered_processes():
    """The coordinator reports whether registered processes are running."""

    class FakeProcess:
        def __init__(self, running):
            self.running = running

        def is_alive(self):
            return self.running

    observer = SuiteParallelObserver()
    observer.register_process(FakeProcess(False))
    assert not observer.processes_running

    observer.register_process(FakeProcess(True))
    assert observer.processes_running


def test_suite_parallel_observer_queues_labeled_result():
    """Parallel observers forward labeled results to final observers."""

    class FakeQueue:
        def __init__(self, result):
            self.result = result

        def get_nowait(self):
            if self.result is None:
                raise queue.Empty
            result = self.result
            self.result = None
            return result

    class RecordingObserver:
        def __init__(self):
            self.results = []

        def result_changed(self, result):
            self.results.append(result)

    result = TestResult("check.py", TestStatus.BUILDING)
    recording_observer = RecordingObserver()
    observer = SuiteParallelObserver(
        (recording_observer,),
        event_queue=FakeQueue(SuiteParallelResult(result, "check.py [1]")),
    )
    observer._notify()

    assert recording_observer.results == [
        TestResult("check.py [1]", TestStatus.BUILDING)
    ]
