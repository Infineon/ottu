"""Tests for suite input classification."""

import pytest
from ottu.suite import Suite, SuiteOpts, SuiteParallelism, _run_test_in_process
from ottu.test import Test, TestOpts, TestPath


def test_classify_test_inputs_classifies_single_suite():
    """Unqualified inputs are a single-device suite."""
    mode, classified_inputs = Suite._classify_test_inputs(["test_a.py", "test_b.py"])

    assert mode is None
    assert classified_inputs == ((None, "test_a.py"), (None, "test_b.py"))


def test_classify_test_inputs_strips_multi_role_prefixes():
    """Role-qualified inputs become role metadata and plain paths."""
    mode, classified_inputs = Suite._classify_test_inputs(
        ["server=server.py", "client=client.py"]
    )

    assert mode is SuiteParallelism.ROLED
    assert classified_inputs == (("server", "server.py"), ("client", "client.py"))


def test_classify_test_inputs_rejects_duplicate_roles():
    """Each role can have only one test input."""
    with pytest.raises(ValueError, match="provided more than once"):
        Suite._classify_test_inputs(["server=one.py", "server=two.py"])


def test_classify_test_inputs_rejects_mixed_roles_and_plain_inputs():
    """Role-qualified and unqualified inputs cannot be mixed."""
    with pytest.raises(ValueError, match="cannot be mixed"):
        Suite._classify_test_inputs(["server=server.py", "client.py"])


def test_suite_from_inputs_resolves_tests_and_sets_mode(tmp_path):
    """Suite construction resolves inputs into executable tests and options."""
    server_test = tmp_path / "server.py"
    client_test = tmp_path / "client.py"
    server_test.touch()
    client_test.touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        working_dir=tmp_path,
    )

    assert suite.options.parallelism is SuiteParallelism.ROLED
    assert all(isinstance(test, Test) for test in suite.tests)
    assert [test.options.role for test in suite.tests] == ["server", "client"]
    assert [test.test_path.absolute_path for test in suite.tests] == [
        server_test,
        client_test,
    ]


def test_suite_from_inputs_sets_replicated_count(tmp_path):
    """A numeric count selects replicated execution for plain tests."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    suite = Suite.from_inputs(["check.py"], counts=("3",), working_dir=tmp_path)

    assert suite.options.parallelism is SuiteParallelism.REPLICATED
    assert [test.options.count for test in suite.tests] == [3]


def test_suite_from_inputs_sets_role_counts(tmp_path):
    """Role counts are stored on their matching tests."""
    server_test = tmp_path / "server.py"
    client_test = tmp_path / "client.py"
    server_test.touch()
    client_test.touch()

    suite = Suite.from_inputs(
        ["server=server.py", "client=client.py"],
        counts=("server=1", "client=4"),
        working_dir=tmp_path,
    )

    assert [test.options.count for test in suite.tests] == [1, 4]


@pytest.mark.parametrize("counts", [("1", "2"), ("server=2",), ("bad",), ("0",)])
def test_suite_rejects_invalid_non_roled_counts(tmp_path, counts):
    """Non-role inputs reject multiple or role-qualified counts."""
    (tmp_path / "check.py").touch()

    with pytest.raises(ValueError):
        Suite.from_inputs(["check.py"], counts=counts, working_dir=tmp_path)


@pytest.mark.parametrize(
    "counts, message",
    [
        (("server",), "role=count"),
        (("other=2",), "Unknown role"),
        (("server=bad",), "positive integer"),
        (("server=0",), "positive integer"),
        (("server=1", "server=2"), "more than once"),
    ],
)
def test_suite_rejects_invalid_role_counts(tmp_path, counts, message):
    """Role counts must identify each role once with a positive integer."""
    (tmp_path / "server.py").touch()

    with pytest.raises(ValueError, match=message):
        Suite.from_inputs(["server=server.py"], counts=counts, working_dir=tmp_path)


def test_suite_rejects_role_test_pattern(tmp_path):
    """Role tests must not use wildcard patterns."""
    (tmp_path / "server.py").touch()

    with pytest.raises(ValueError, match="not a pattern"):
        Suite.from_inputs(["server=*.py"], working_dir=tmp_path)


def test_suite_rejects_role_test_directory(tmp_path):
    """Role tests must resolve to a file rather than a directory."""
    (tmp_path / "server_tests").mkdir()

    with pytest.raises(ValueError, match="exactly one test file"):
        Suite.from_inputs(["server=server_tests"], working_dir=tmp_path)


def test_test_suite_runs_each_test_in_order(capsys, tmp_path):
    """A suite iterates over all collected tests in order."""
    first = TestPath(tmp_path / "first.py", tmp_path / "first.py", None, "first.py")
    second = TestPath(tmp_path / "second.py", tmp_path / "second.py", None, "second.py")

    Suite(
        SuiteOpts(),
        [Test(first, TestOpts()), Test(second, TestOpts())],
    ).run()

    assert capsys.readouterr().out == (
        f"Running test: {tmp_path / 'first.py'}\n"
        f"Running test: {tmp_path / 'second.py'}\n"
    )


def test_suite_selects_runner_for_each_parallelism_strategy():
    """Suite dispatches each parallelism value to its matching runner."""
    suite = Suite(SuiteOpts(), [])

    assert suite._runner_for(None) == suite._run_sequential
    assert suite._runner_for(SuiteParallelism.REPLICATED) == suite._run_replicated
    assert suite._runner_for(SuiteParallelism.DISTRIBUTED) == suite._run_distributed
    assert suite._runner_for(SuiteParallelism.ROLED) == suite._run_roled


@pytest.mark.parametrize(
    "parallelism",
    [
        SuiteParallelism.REPLICATED,
        SuiteParallelism.DISTRIBUTED,
        SuiteParallelism.ROLED,
    ],
)
def test_suite_placeholder_runners_are_callable(parallelism):
    """Placeholder strategies can be selected until their implementations land."""
    Suite(SuiteOpts(parallelism=parallelism), []).run()


def test_roled_runner_starts_all_processes_before_joining(monkeypatch):
    """Role execution starts one process per test before waiting for them."""
    events = []

    class FakeProcess:
        def __init__(self, target, args):
            self.target = target
            self.args = args
            self.exitcode = 0

        def start(self):
            events.append(("start", self.args[0]))

        def join(self):
            events.append(("join", self.args[0]))

    monkeypatch.setattr("ottu.suite.Process", FakeProcess)
    first = Test(TestPath("first.py", "first.py", None, "first.py"), TestOpts())
    second = Test(TestPath("second.py", "second.py", None, "second.py"), TestOpts())

    Suite(SuiteOpts(SuiteParallelism.ROLED), [first, second]).run()

    assert [event[0] for event in events] == ["start", "start", "join", "join"]


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

    Suite(SuiteOpts(SuiteParallelism.ROLED), [server, client]).run()

    assert [event[0] for event in events] == [
        "start",
        "start",
        "start",
        "join",
        "join",
        "join",
    ]
    assert [event[1] for event in events[:3]] == [server, server, client]


def test_replicated_runner_starts_requested_process_count(monkeypatch):
    """Replicated execution starts one process per test replica."""
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
    first = Test(
        TestPath("first.py", "first.py", None, "first.py"),
        TestOpts(count=2),
    )
    second = Test(
        TestPath("second.py", "second.py", None, "second.py"),
        TestOpts(count=1),
    )

    Suite(SuiteOpts(SuiteParallelism.REPLICATED), [first, second]).run()

    assert [event[0] for event in events] == [
        "start",
        "start",
        "start",
        "join",
        "join",
        "join",
    ]
    assert [event[1] for event in events[:3]] == [first, first, second]


def test_replicated_runner_raises_when_a_process_fails(monkeypatch):
    """Replicated execution reports a failed child process."""
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
        TestOpts(count=1),
    )

    with pytest.raises(RuntimeError, match="replicated tests failed"):
        Suite(SuiteOpts(SuiteParallelism.REPLICATED), [test]).run()


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
    test = Test(TestPath("failed.py", "failed.py", None, "failed.py"))

    with pytest.raises(RuntimeError, match="role tests failed"):
        Suite(SuiteOpts(SuiteParallelism.ROLED), [test]).run()


def test_run_test_in_process_runs_the_given_test():
    """The process target delegates execution to its test."""
    executed = []

    class FakeTest:
        def run(self):
            executed.append(True)

    _run_test_in_process(FakeTest())

    assert executed == [True]
