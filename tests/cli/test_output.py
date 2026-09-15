"""Tests for CLI test-result reporting."""

from ottu.cli.output import CliOutput
from ottu.result import TestResult, TestStatus


def test_test_result_prints_pass(capsys):
    CliOutput.report(TestResult("check.py", TestStatus.PASSED))

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "PASS" in output


def test_test_result_prints_fail(capsys):
    CliOutput.report(TestResult("check.py", TestStatus.FAILED))

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "FAIL" in output


def test_report_all_prints_each_result(capsys):
    CliOutput.report_all(
        [
            TestResult("first.py", TestStatus.PASSED),
            TestResult("second.py", TestStatus.FAILED),
        ]
    )

    output = capsys.readouterr().out
    assert "first.py" in output
    assert "second.py" in output


def test_progress_prints_final_status_without_live_spinner(capsys):
    progress = CliOutput()

    progress.update("check.py", "PASS")

    assert "check.py" in capsys.readouterr().out


def test_progress_keeps_spinner_across_execution_stages(monkeypatch):
    """Building and flashing update one spinner before it is finalized."""
    events = []

    class FakeSpinner:
        def __init__(self, name, *, style):
            self.name = name
            self.style = style

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
    progress.update("hello-world", "building")
    spinner = progress._spinner
    progress.update("hello-world", "flashing")
    progress.update("hello-world", "PASS")

    assert spinner is not None
    assert spinner.name == "dots6"
    assert progress._label is None
    assert events[2][1].renderables[0].plain == f"{'hello-world':<40} flashing "
    assert events[2][1].renderables[1] is spinner
    assert [event[0] for event in events] == [
        "create",
        "start",
        "update",
        "update",
        "stop",
    ]


def test_progress_stop_clears_active_spinner(monkeypatch):
    class FakeSpinner:
        def __init__(self, name, *, style):
            self.name = name
            self.style = style

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
    progress.update("check.py", "building")
    live = progress._live

    progress.update("check.py", "PASS")

    assert live is not None
    assert live.stopped
    assert progress._live is None
    assert progress._spinner is None
    assert progress._label is None
