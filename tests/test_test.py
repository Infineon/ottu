"""Test path resolution tests."""

import pytest
from ottu.backend import Backend
from ottu.device import Device, SerialDeviceAccess
from ottu.result import TestOutput, TestOutputParser, TestStatus
from ottu.test import Test, TestOpts, TestPath, TestPathContext, TestPathResolver


def test_resolve_relative_path_from_working_directory(tmp_path):
    test_file = tmp_path / "check.py"
    test_file.touch()

    result = TestPathResolver.resolve("check.py", TestPathContext(working_dir=tmp_path))

    assert result == [
        TestPath(test_file, test_file.relative_to(tmp_path), None, "check.py")
    ]


def test_resolve_path_from_default_tests_directory(tmp_path):
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = TestPathResolver.resolve("check.py", TestPathContext(working_dir=tmp_path))

    assert result[0].absolute_path == test_file


def test_resolve_path_with_project_relative_form(tmp_path):
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = TestPathResolver.resolve(
        "check.py",
        TestPathContext(working_dir=tmp_path / "work", project_root=tmp_path),
    )

    assert result[0].project_root_relative_path == test_file.relative_to(tmp_path)


def test_resolve_absolute_path(tmp_path):
    test_file = tmp_path / "check.py"
    test_file.touch()

    result = TestPathResolver.resolve(
        str(test_file), TestPathContext(working_dir=tmp_path)
    )

    assert result[0].absolute_path == test_file


def test_resolve_all_expands_glob(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "b.py").touch()
    (tests_dir / "a.py").touch()

    result = TestPathResolver.resolve_all(
        ["*.py"], TestPathContext(working_dir=tmp_path, tests_dir="tests")
    )

    assert [entry.file_name for entry in result] == ["a.py", "b.py"]


def test_resolve_all_excludes_expected_output_files_from_glob(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "check.py").touch()
    (tests_dir / "check.py.exp").touch()

    result = TestPathResolver.resolve_all(
        ["*"], TestPathContext(working_dir=tmp_path, tests_dir="tests")
    )

    assert [entry.file_name for entry in result] == ["check.py"]


def test_resolve_directory_expands_child_test_files(tmp_path):
    test_directory = tmp_path / "hello-universe"
    test_directory.mkdir()
    test_file = test_directory / "hello-universe.ino"
    test_file.touch()
    (test_directory / "hello-universe.ino.exp").touch()

    result = TestPathResolver.resolve(
        "hello-universe", TestPathContext(working_dir=tmp_path)
    )

    assert [entry.absolute_path for entry in result] == [test_file]


def test_resolve_empty_directory_raises(tmp_path):
    (tmp_path / "empty").mkdir()

    with pytest.raises(ValueError, match="contains no test files"):
        TestPathResolver.resolve("empty", TestPathContext(working_dir=tmp_path))


def test_resolve_unmatched_glob_raises(tmp_path):
    """A glob with no file matches is rejected."""
    with pytest.raises(ValueError, match="did not match any files"):
        TestPathResolver.resolve("*.py", TestPathContext(working_dir=tmp_path))


def test_resolve_missing_path_raises(tmp_path):
    """A non-glob input with no candidates is rejected."""
    with pytest.raises(ValueError, match="does not exist"):
        TestPathResolver.resolve("missing.py", TestPathContext(working_dir=tmp_path))


def test_validate_and_resolve_all_combines_inputs(tmp_path):
    """All inputs are resolved into one ordered result list."""
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.touch()
    second.touch()

    result = TestPathResolver.resolve_all(
        [
            "first.py",
            "second.py",
        ],
        TestPathContext(working_dir=tmp_path),
    )

    assert [entry.absolute_path for entry in result] == [first, second]


def test_validate_and_resolve_all_discovers_when_inputs_are_empty(tmp_path):
    """An empty input list delegates to automatic discovery."""
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = TestPathResolver.resolve_all(
        [], TestPathContext(working_dir=tmp_path, pattern="**/*.py")
    )

    assert [entry.absolute_path for entry in result] == [test_file]


def test_validate_and_resolve_all_discovers_for_no_selectors(tmp_path):
    """No selectors trigger discovery using the supplied context."""
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = TestPathResolver.resolve_all(
        [], TestPathContext(working_dir=tmp_path, pattern="*.py")
    )

    assert [entry.absolute_path for entry in result] == [test_file]


def test_validate_and_resolve_all_excludes_matching_glob(tmp_path):
    """Exclusions can remove multiple discovered files with one glob."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    included = tests_dir / "keep.py"
    excluded_first = tests_dir / "skip_first.py"
    excluded_second = tests_dir / "skip_second.py"
    included.touch()
    excluded_first.touch()
    excluded_second.touch()

    result = TestPathResolver.resolve_all(
        [],
        TestPathContext(working_dir=tmp_path, pattern="**/*.py"),
        exclude_test_selectors=("skip_*.py",),
    )

    assert [entry.absolute_path for entry in result] == [included]


def test_discover_finds_files_recursively_in_default_tests_directory(tmp_path):
    """Discovery finds all files under the default test directory."""
    application_file = tmp_path / "app.py"
    tests_dir = tmp_path / "tests" / "nested"
    tests_dir.mkdir(parents=True)
    first = tests_dir / "first.py"
    second = tests_dir / "second.cpp"
    application_file.touch()
    first.touch()
    second.touch()

    result = TestPathResolver.discover(TestPathContext(working_dir=tmp_path))

    assert [entry.absolute_path for entry in result] == [first, second]


def test_discover_excludes_expected_output_files(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "check.py"
    expected_file = tests_dir / "check.py.exp"
    test_file.touch()
    expected_file.touch()

    result = TestPathResolver.discover(
        TestPathContext(working_dir=tmp_path, pattern="**/*")
    )

    assert [entry.absolute_path for entry in result] == [test_file]


def test_discover_applies_custom_pattern_and_directory(tmp_path):
    """Discovery supports custom directories and extension patterns."""
    custom_dir = tmp_path / "fixtures"
    custom_dir.mkdir()
    python_test = custom_dir / "check.py"
    cpp_test = custom_dir / "check.cpp"
    python_test.touch()
    cpp_test.touch()

    result = TestPathResolver.discover(
        TestPathContext(working_dir=tmp_path, tests_dir="fixtures", pattern="**/*.py")
    )

    assert [entry.absolute_path for entry in result] == [python_test]


def test_discover_includes_project_root_tests(tmp_path):
    """Discovery searches project-root test directories as well."""
    project_tests = tmp_path / "project" / "tests"
    work_dir = tmp_path / "project" / "work"
    project_tests.mkdir(parents=True)
    work_dir.mkdir()
    test_file = project_tests / "check.py"
    test_file.touch()

    result = TestPathResolver.discover(
        TestPathContext(
            working_dir=work_dir, project_root=tmp_path / "project", pattern="*.py"
        )
    )

    assert [entry.absolute_path for entry in result] == [test_file]


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


def test_test_from_inputs_preserves_count_and_role(tmp_path):
    """Test construction stores its role and replication count."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    tests = Test.from_inputs(
        ["check.py"],
        options=TestOpts(role="client", count=3),
        context=TestPathContext(working_dir=tmp_path),
    )

    assert [(test.options.role, test.options.count) for test in tests] == [
        ("client", 3)
    ]


def test_test_opts_validates_role_and_count():
    """TestOpts stores valid role and count values."""
    options = TestOpts(role="client", count=3)

    assert options == TestOpts(role="client", count=3)


@pytest.mark.parametrize(
    "options",
    [
        {"role": "", "count": 1},
        {"role": "   ", "count": 1},
        {"role": None, "count": 0},
        {"role": None, "count": -1},
    ],
)
def test_test_opts_rejects_invalid_values(options):
    """TestOpts rejects empty roles and invalid counts."""
    with pytest.raises(ValueError):
        TestOpts(**options)


def test_test_accepts_explicit_options(tmp_path):
    """Test stores an explicit TestOpts object."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")
    options = TestOpts(role="client", count=2)

    test = Test(test_path, options=options)

    assert test.options is options
    assert test.options.role == "client"
    assert test.options.count == 2


def test_test_stores_device_requirement(tmp_path):
    """Test stores its device requirement independently from execution options."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")

    test = Test(test_path, device="port=/dev/ttyUSB0")

    assert test.device == "port=/dev/ttyUSB0"
    assert test.options == TestOpts()


def test_test_from_inputs_rejects_non_positive_count(tmp_path):
    """Test construction requires a positive replication count."""
    test_file = tmp_path / "check.py"
    test_file.touch()

    with pytest.raises(ValueError, match="positive integer"):
        Test.from_inputs(
            ["check.py"],
            options=TestOpts(count=0),
            context=TestPathContext(working_dir=tmp_path),
        )
