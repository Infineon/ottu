"""Tests for CLI test-result reporting."""

from io import StringIO
from pathlib import Path

from ottu.cli.output import CliOutput
from ottu.device import Device
from ottu.result import TestResult, TestStatus
from ottu.test import Test
from ottu.test_path import TestPath
from rich.console import Console
from rich.text import Text


def make_test(name, device=None):
    path = Path(name)
    if isinstance(device, str):
        device = Device.from_string(device)
    return Test(TestPath(path, path, None, path.name), device=device)


def make_result(name, status, device=None):
    test = make_test(name, device)
    return TestResult(test.test_path, status, device=test.device)


def test_test_result_prints_pass(capsys):
    CliOutput.report(make_result("check.py", TestStatus.PASSED))

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "PASS" in output


def test_test_result_prints_fail(capsys):
    CliOutput.report(make_result("check.py", TestStatus.FAILED))

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "FAIL" in output


def test_report_all_prints_each_result(capsys):
    CliOutput.report_all(
        [
            make_result("first.py", TestStatus.PASSED),
            make_result("second.py", TestStatus.FAILED),
        ]
    )

    output = capsys.readouterr().out
    assert "first.py" in output
    assert "second.py" in output


def test_report_all_sizes_columns_to_longest_result():
    output = StringIO()
    CliOutput.report_all(
        [
            make_result("short.py", TestStatus.PASSED, device="one"),
            make_result(
                "hello-universe.ino",
                TestStatus.FAILED,
                device="infineon:psoc6:cy8ckit_062s2_ai",
            ),
        ],
        console=Console(file=output, width=200),
    )

    assert "short.py" in output.getvalue()
    assert "hello-universe.ino" in output.getvalue()
    widths = CliOutput._column_widths(
        [
            make_result("short.py", TestStatus.PASSED, device="one"),
            make_result(
                "hello-universe.ino",
                TestStatus.FAILED,
                device="infineon:psoc6:cy8ckit_062s2_ai",
            ),
        ]
    )
    text = CliOutput._result_text(
        make_result("short.py", TestStatus.PASSED, device="one"), widths
    ).plain
    assert text.endswith("\t\t\t\t\t\tPASS")


def test_progress_sizes_columns_to_longest_result(monkeypatch):
    class FakeLive:
        def __init__(self, renderable, **kwargs):
            self.renderable = renderable

        def start(self):
            pass

        def update(self, renderable):
            self.renderable = renderable

        def stop(self):
            pass

    monkeypatch.setattr("ottu.cli.output.Live", FakeLive)

    progress = CliOutput()
    progress.update(make_test("short.py", "one").test_path, "building")
    progress.update(
        make_test("hello-universe.ino").test_path,
        "FAIL",
        device=Device.from_string("infineon:psoc6:cy8ckit_062s2_ai"),
    )

    table = progress._live.renderable
    assert table.columns[0].width == len("hello-universe.ino")
    assert table.columns[1].width == len("infineon:psoc6:cy8ckit_062s2_ai")
    assert table.columns[2].width == len("building") + 2


def test_progress_prints_final_status_without_live_spinner(capsys):
    progress = CliOutput()

    progress.update(make_test("check.py").test_path, "PASS")
    progress.finish()

    assert "check.py" in capsys.readouterr().out


def test_progress_keeps_spinner_across_execution_stages(monkeypatch):
    """Building and flashing update one spinner before it is finalized."""
    events = []

    class FakeSpinner:
        def __init__(self, name, *, style):
            self.name = name
            self.style = style

        def __rich_console__(self, console, options):
            yield Text("spinner")

    class FakeLive:
        def __init__(self, spinner, **kwargs):
            self.spinner = spinner
            events.append(("create", spinner))

        def start(self):
            events.append(("start", self.spinner))

        def update(self, renderable):
            events.append(("update", renderable))

        def stop(self):
            events.append(("stop", self.spinner))

    monkeypatch.setattr("ottu.cli.output.Spinner", FakeSpinner)
    monkeypatch.setattr("ottu.cli.output.Live", FakeLive)

    progress = CliOutput()
    progress.update(make_test("hello-world").test_path, "building")
    spinner = progress._spinners[("hello-world", "", None)]
    progress.update(make_test("hello-world").test_path, "flashing")
    progress.update(make_test("hello-world").test_path, "PASS")
    progress.finish()

    assert spinner is not None
    assert spinner.name == "dots6"
    assert progress._results[0].status.value == "PASS"
    assert len(events[2][1].rows) == 1
    assert [event[0] for event in events] == [
        "create",
        "start",
        "update",
        "update",
        "update",
        "stop",
    ]


def test_progress_stop_clears_active_spinner(monkeypatch):
    class FakeSpinner:
        def __init__(self, name, *, style):
            self.name = name
            self.style = style

        def __rich_console__(self, console, options):
            yield Text("spinner")

    class FakeLive:
        def __init__(self, spinner, **kwargs):
            self.spinner = spinner
            self.stopped = False

        def start(self):
            pass

        def update(self, renderable):
            pass

        def stop(self):
            self.stopped = True

    monkeypatch.setattr("ottu.cli.output.Spinner", FakeSpinner)
    monkeypatch.setattr("ottu.cli.output.Live", FakeLive)

    progress = CliOutput()
    progress.update(make_test("check.py").test_path, "building")
    live = progress._live

    progress.update(make_test("check.py").test_path, "PASS")
    progress.finish()

    assert live is not None
    assert live.stopped
    assert progress._live is None
    assert progress._spinners == {}


def test_progress_keeps_multiple_results_in_one_live_render(monkeypatch):
    renders = []

    class FakeLive:
        def __init__(self, renderable, **kwargs):
            renders.append(renderable)

        def start(self):
            pass

        def update(self, renderable):
            renders.append(renderable)

        def stop(self):
            pass

    monkeypatch.setattr("ottu.cli.output.Live", FakeLive)

    progress = CliOutput()
    progress.update(make_test("first.py").test_path, "building")
    progress.update(make_test("second.py").test_path, "flashing")

    assert [CliOutput._test_name(result.test_path) for result in progress._results] == [
        "first.py",
        "second.py",
    ]
    assert len(renders[-1].rows) == 2


def test_progress_separates_same_test_by_device(monkeypatch):
    class FakeLive:
        def __init__(self, renderable, **kwargs):
            self.renderable = renderable

        def start(self):
            pass

        def update(self, renderable):
            self.renderable = renderable

        def stop(self):
            pass

    monkeypatch.setattr("ottu.cli.output.Live", FakeLive)

    progress = CliOutput()
    progress.update(
        make_test("check.py").test_path,
        "building",
        device=Device.from_string("/dev/ttyUSB0"),
    )
    progress.update(
        make_test("check.py").test_path,
        "building",
        device=Device.from_string("/dev/ttyUSB1"),
    )

    assert [
        (CliOutput._test_name(result.test_path), CliOutput._device_name(result.device))
        for result in progress._results
    ] == [
        ("check.py", "/dev/ttyUSB0"),
        ("check.py", "/dev/ttyUSB1"),
    ]
