"""Test execution and option tests."""

from pathlib import Path

import pytest
from ottu.backend import Backend
from ottu.device import Device, DeviceAccessSerial
from ottu.output import (
    OutputParserType,
    TestOutcome,
    TestOutput,
    TestOutputOpts,
    TestOutputParser,
)
from ottu.result import TestStatus
from ottu.test import Test, TestOpts
from ottu.test_path import TestPath, TestPathContext


def test_test_run_requires_a_backend(tmp_path):
    """A test cannot run without an assigned backend."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")

    with pytest.raises(ValueError, match="backend is required"):
        Test(test_path).run()


def test_test_run_invokes_assigned_backend(monkeypatch, tmp_path):
    """A test delegates execution to its assigned backend."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program {device}"})
    calls = []

    def run_backend(_backend, test_path, device, **kwargs):
        calls.append((test_path, device, kwargs))

    monkeypatch.setattr(
        DeviceAccessSerial,
        "connect",
        lambda self, device: type(
            "Connection",
            (),
            {
                "readline": lambda self: b"",
                "close": lambda self: None,
            },
        )(),
    )

    monkeypatch.setattr(Backend, "run", run_backend)

    test = Test(
        test_path,
        device=Device.from_string("name=board-1,address=/dev/ttyUSB0"),
        backend=backend,
    )
    test.run()

    assert len(calls) == 1
    called_test_path, device, kwargs = calls[0]
    assert called_test_path == test_path
    assert device == test.device
    assert kwargs["observers"] == ()
    assert kwargs["defines"][0] == "OTTU_FRAMED_OUTPUT_ENABLED=1"
    assert set(kwargs) == {"observers", "defines"}
    assert test.device.name == "board-1"


def test_test_display_name_uses_working_directory_relative_path(tmp_path):
    test_path = TestPath(
        tmp_path / "tests" / "check.py",
        Path("tests/check.py"),
        None,
        "check.py",
    )

    from ottu.cli.output import CliOutput

    assert CliOutput._test_name(test_path) == "check.py"


def test_test_run_propagates_backend_failure(monkeypatch, tmp_path):
    """Backend execution failures propagate as host execution errors."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program {device}"})

    def fail_backend(_backend, _test_path, _device, **_kwargs):
        raise RuntimeError("backend failed")

    monkeypatch.setattr(Backend, "run", fail_backend)

    with pytest.raises(RuntimeError, match="backend failed"):
        Test(test_path, backend=backend).run()


def test_test_run_returns_device_reported_failure(monkeypatch, tmp_path):
    """A failure parsed from device output becomes a failed test result."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})

    monkeypatch.setattr(
        DeviceAccessSerial,
        "connect",
        lambda self, device: type("Connection", (), {"close": lambda self: None})(),
    )
    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: None,
    )

    class Output:
        def parse(self, connection):
            return TestOutput(("FAIL",), TestOutcome.FAIL)

    monkeypatch.setattr(TestOutputParser, "parse", Output().parse)

    result = Test(
        test_path,
        device=Device.from_string("address=/dev/ttyUSB0"),
        backend=backend,
    ).run()

    assert result.status is TestStatus.DONE
    assert result.outcome is TestOutcome.FAIL
    assert not result.passed
    assert result.output == TestOutput(("FAIL",), TestOutcome.FAIL)


def test_test_run_notifies_observer_of_final_status(monkeypatch, tmp_path):
    """Test execution emits a final pass or fail event to observers."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    events = []

    class Observer:
        def result_changed(self, result):
            events.append(result)

    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: None,
    )

    Test(test_path, backend=backend, observers=(Observer(),)).run()

    assert [(event.test_path.file_name, event.status) for event in events] == [
        ("check.py", TestStatus.CONNECTING),
        ("check.py", TestStatus.DONE),
    ]
    assert [event.outcome for event in events] == [None, TestOutcome.PASS]


def test_test_run_reads_output_after_backend(monkeypatch, tmp_path):
    """Test execution reads device output after backend execution."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    events = []
    statuses = []

    class Output:
        def parse(self, connection):
            events.append(connection)
            return TestOutput(("PASS",), TestOutcome.PASS)

    monkeypatch.setattr(TestOutputParser, "parse", Output().parse)

    class Observer:
        def result_changed(self, result):
            statuses.append(result.status)

    monkeypatch.setattr(
        DeviceAccessSerial,
        "connect",
        lambda self, device: type("Connection", (), {"close": lambda self: None})(),
    )

    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: None,
    )

    result = Test(
        test_path,
        device=Device.from_string("address=/dev/ttyUSB0"),
        backend=backend,
        observers=(Observer(),),
    ).run()

    assert len(events) == 1
    assert events[0] is not None
    assert result.output == TestOutput(("PASS",), TestOutcome.PASS)
    assert result.outcome is TestOutcome.PASS
    assert statuses == [
        TestStatus.CONNECTING,
        TestStatus.EXECUTING,
        TestStatus.DONE,
    ]


def test_test_run_uses_expected_output_file(monkeypatch, tmp_path):
    """A sibling .exp file selects expected-output parsing for the test."""
    test_file = tmp_path / "check.py"
    test_file.touch()
    (tmp_path / "check.py.exp").write_text("ready\nPASS\n", encoding="utf-8")
    test_path = TestPath(test_file, test_file, None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    lines = iter((b"ready\n", b"PASS\n", b""))

    monkeypatch.setattr(
        DeviceAccessSerial,
        "connect",
        lambda self, device: type(
            "Connection",
            (),
            {
                "readline": lambda self: next(lines, b""),
                "close": lambda self: None,
            },
        )(),
    )
    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: None,
    )

    result = Test(
        test_path,
        device=Device.from_string("address=/dev/ttyUSB0"),
        backend=backend,
    ).run()

    assert result.output == TestOutput(("ready\n", "PASS\n"), TestOutcome.PASS)


@pytest.mark.parametrize(
    ("lines", "outcome"),
    [
        ([b"6 Tests 0 Failures 0 Ignored\n", b"OK\n"], TestOutcome.PASS),
        ([b"6 Tests 1 Failures 0 Ignored\n", b"FAIL\n"], TestOutcome.FAIL),
        ([b"ready\n"], TestOutcome.UNVERIFIED),
        ([], TestOutcome.UNVERIFIED),
    ],
)
def test_test_run_detects_unity_output_without_expected_file(
    monkeypatch, tmp_path, lines, outcome
):
    """Without an .exp file, output is checked as Unity or left unverified."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    serial_lines = iter(lines)

    monkeypatch.setattr(
        DeviceAccessSerial,
        "connect",
        lambda self, device: type(
            "Connection",
            (),
            {
                "readline": lambda self: next(serial_lines, b""),
                "close": lambda self: None,
            },
        )(),
    )
    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: None,
    )

    result = Test(
        test_path,
        options=TestOpts(output=TestOutputOpts(idle_timeout=0)),
        device=Device.from_string("address=/dev/ttyUSB0"),
        backend=backend,
    ).run()

    assert result.status is TestStatus.DONE
    assert result.outcome is outcome


def test_test_run_without_connection_passes(monkeypatch, tmp_path):
    """A run with no output to check passes."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: None,
    )

    result = Test(test_path, backend=backend).run()

    assert result.output == TestOutput((), TestOutcome.PASS)
    assert result.outcome is TestOutcome.PASS


def test_test_run_parses_with_the_tests_own_output_options(monkeypatch, tmp_path):
    """The parser gets the same options whose token the target build uses."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    parser_opts = []
    create = TestOutputParser.create

    def spy(path, opts=None, **kwargs):
        parser_opts.append(opts)
        return create(path, opts, **kwargs)

    monkeypatch.setattr(TestOutputParser, "create", spy)
    monkeypatch.setattr(
        TestOutputParser,
        "parse",
        lambda self, connection: TestOutput(("PASS",), TestOutcome.PASS),
    )
    monkeypatch.setattr(
        DeviceAccessSerial,
        "connect",
        lambda self, device: type("Connection", (), {"close": lambda self: None})(),
    )
    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: None,
    )
    test = Test(
        test_path,
        device=Device.from_string("address=/dev/ttyUSB0"),
        backend=backend,
    )

    test.run()

    assert len(parser_opts) == 1
    assert parser_opts[0] is test.options.output
    assert test.options.output.framed_output_opts.token is not None


def test_test_from_inputs_gives_each_test_its_own_output_token(tmp_path):
    """Tests built without options do not share an output token."""
    (tmp_path / "first.py").touch()
    (tmp_path / "second.py").touch()

    tests = Test.from_inputs(
        ["first.py", "second.py"],
        context=TestPathContext(working_dir=tmp_path),
    )

    tokens = {test.options.output.framed_output_opts.token for test in tests}
    assert len(tests) == 2
    assert None not in tokens
    assert len(tokens) == 2


def test_test_from_inputs_shares_supplied_options(tmp_path):
    """Options passed in are used as given, including their token."""
    (tmp_path / "first.py").touch()
    (tmp_path / "second.py").touch()
    options = TestOpts()

    tests = Test.from_inputs(
        ["first.py", "second.py"],
        options=options,
        context=TestPathContext(working_dir=tmp_path),
    )

    assert all(test.options is options for test in tests)


def test_test_run_creates_the_parser_before_the_backend_runs(monkeypatch, tmp_path):
    """The parser's options must exist before the build, which needs them."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    events = []
    create = TestOutputParser.create

    def spy(path, opts=None, **kwargs):
        events.append("parser")
        return create(path, opts, **kwargs)

    monkeypatch.setattr(TestOutputParser, "create", spy)
    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: events.append("backend"),
    )

    Test(test_path, backend=backend).run()

    assert events == ["parser", "backend"]


def test_test_run_fails_before_building_when_no_parser_can_be_created(
    monkeypatch, tmp_path
):
    """An explicit expected-output match without a file fails before the build."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    built = []
    events = []

    class Observer:
        def result_changed(self, result):
            events.append(result.status)

    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: built.append(True),
    )
    options = TestOpts(output=TestOutputOpts(parser=OutputParserType.EXP_MATCH))

    with pytest.raises(FileNotFoundError, match="No expected-output file"):
        Test(
            test_path,
            options=options,
            backend=backend,
            observers=(Observer(),),
        ).run()

    assert built == []
    assert events == []


def test_test_run_passes_the_parsers_build_defines_to_the_backend(
    monkeypatch, tmp_path
):
    """The build gets the token the parser will verify the output against."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    calls = []
    parsers = []
    create = TestOutputParser.create

    def spy(path, opts=None, **kwargs):
        parser = create(path, opts, **kwargs)
        parsers.append(parser)
        return parser

    monkeypatch.setattr(TestOutputParser, "create", spy)
    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: calls.append(kwargs),
    )

    Test(test_path, backend=backend).run()

    token = parsers[0].opts.framed_output_opts.token
    assert calls[0]["defines"] == [
        "OTTU_FRAMED_OUTPUT_ENABLED=1",
        f"OTTU_TEST_FRAME_TOKEN={token}",
    ]


def test_test_run_skips_output_for_name_only_device(monkeypatch, tmp_path):
    """Name-only devices do not attempt a serial connection."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})

    class Output:
        def parse(self, connection):
            raise AssertionError("serial output should not run")

    monkeypatch.setattr(TestOutputParser, "parse", Output().parse)

    monkeypatch.setattr(
        Backend,
        "run",
        lambda _backend, _test_path, _device, **kwargs: None,
    )

    Test(test_path, backend=backend).run()


def test_test_from_inputs_preserves_role(tmp_path):
    """Test construction stores its role."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    tests = Test.from_inputs(
        ["check.py"],
        options=TestOpts(role="client"),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [test.options.role for test in tests] == ["client"]


def test_test_opts_validates_role():
    """TestOpts stores a valid role value."""
    options = TestOpts(role="client")

    assert options == TestOpts(role="client")


@pytest.mark.parametrize(
    "options",
    [
        {"role": ""},
        {"role": "   "},
    ],
)
def test_test_opts_rejects_invalid_values(options):
    """TestOpts rejects empty roles."""
    with pytest.raises(ValueError):
        TestOpts(**options)


def test_test_accepts_explicit_options(tmp_path):
    """Test stores an explicit TestOpts object."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    options = TestOpts(role="client")

    test = Test(test_path, options=options)

    assert test.options is options
    assert test.options.role == "client"


def test_test_stores_device_requirement(tmp_path):
    """Test stores its device requirement independently from execution options."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")

    test = Test(test_path, device=Device.from_string("address=/dev/ttyUSB0"))

    assert test.device == Device.from_string("address=/dev/ttyUSB0")
    assert test.options == TestOpts()
