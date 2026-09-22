"""Test execution and option tests."""

import pytest
from ottu.backend import Backend
from ottu.device import Device, SerialDeviceAccess
from ottu.result import TestOutput, TestOutputParser, TestStatus
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
        SerialDeviceAccess,
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

    Test(
        test_path,
        device="name=board-1,port=/dev/ttyUSB0",
        backend=backend,
    ).run()

    assert len(calls) == 1
    called_test_path, device, kwargs = calls[0]
    assert called_test_path == test_path.absolute_path
    assert isinstance(device, Device)
    assert dict(device) == {
        "name": "board-1",
        "port": "/dev/ttyUSB0",
        "device": "board-1",
    }
    assert kwargs == {"observers": ()}


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
        SerialDeviceAccess,
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
            return TestOutput(("FAIL",), TestStatus.FAILED)

    monkeypatch.setattr(TestOutputParser, "parse", Output().parse)

    result = Test(
        test_path,
        device="port=/dev/ttyUSB0",
        backend=backend,
    ).run()

    assert result.status is TestStatus.FAILED
    assert result.output == TestOutput(("FAIL",), TestStatus.FAILED)


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

    assert [(event.test_name, event.status) for event in events] == [
        ("check.py", TestStatus.CONNECTING),
        ("check.py", TestStatus.PASSED),
    ]


def test_test_run_reads_output_after_backend(monkeypatch, tmp_path):
    """Test execution reads device output after backend execution."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    backend = Backend.from_mapping({"program": "echo program"})
    events = []
    statuses = []

    class Output:
        def parse(self, connection):
            events.append(connection)
            return TestOutput(("PASS",), TestStatus.PASSED)

    monkeypatch.setattr(TestOutputParser, "parse", Output().parse)

    class Observer:
        def result_changed(self, result):
            statuses.append(result.status)

    monkeypatch.setattr(
        SerialDeviceAccess,
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
        device="port=/dev/ttyUSB0",
        backend=backend,
        observers=(Observer(),),
    ).run()

    assert len(events) == 1
    assert events[0] is not None
    assert result.output == TestOutput(("PASS",), TestStatus.PASSED)
    assert statuses == [
        TestStatus.CONNECTING,
        TestStatus.EXECUTING,
        TestStatus.PASSED,
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
        SerialDeviceAccess,
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
        device="port=/dev/ttyUSB0",
        backend=backend,
    ).run()

    assert result.output == TestOutput(("ready\n", "PASS\n"), TestStatus.PASSED)


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

    test = Test(test_path, device="port=/dev/ttyUSB0")

    assert test.device == "port=/dev/ttyUSB0"
    assert test.options == TestOpts()
