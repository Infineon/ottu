"""Tests for CLI test-report reporting."""

from io import StringIO
from pathlib import Path

from ottu.cli.output import CliOutput, TestOutputWriter
from ottu.device import Device
from ottu.output import TestOutput, TestResult
from ottu.report import TestReport, TestStatus
from ottu.test import Test
from ottu.test_path import TestPath
from rich.console import Console
from rich.text import Text


def make_test(name, device=None):
    path = Path(name)
    if isinstance(device, str):
        device = Device.from_string(device)
    return Test(TestPath(path, path, None, path.name), device=device)


def make_report(name, result, device=None):
    test = make_test(name, device)
    return TestReport(
        test.test_path,
        TestStatus.DONE,
        device=test.device,
        output=TestOutput((), result),
    )


def test_test_report_prints_pass(capsys):
    CliOutput.report(make_report("check.py", TestResult.PASS))

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "PASS" in output


def test_test_report_prints_fail(capsys):
    CliOutput.report(make_report("check.py", TestResult.FAIL))

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "FAIL" in output


def test_test_report_prints_unverified(capsys):
    CliOutput.report(make_report("check.py", TestResult.UNVERIFIED))

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "UNVERIFIED" in output


def test_unverified_report_is_yellow():
    report = make_report("check.py", TestResult.UNVERIFIED)

    text = CliOutput._report_text(report, CliOutput._column_widths([report]))

    assert text.spans[-1].style == "yellow"


def test_report_all_prints_each_report(capsys):
    CliOutput.report_all(
        [
            make_report("first.py", TestResult.PASS),
            make_report("second.py", TestResult.FAIL),
        ]
    )

    output = capsys.readouterr().out
    assert "first.py" in output
    assert "second.py" in output


def test_output_writer_saves_test_output_under_relative_path(tmp_path):
    test_path = TestPath(
        tmp_path / "tests" / "nested" / "check.py",
        Path("tests/nested/check.py"),
        Path("tests/nested/check.py"),
        "check.py",
    )
    report = TestReport(
        test_path,
        TestStatus.DONE,
        output=TestOutput(
            ("6 Tests 1 Failures 0 Ignored\n", "FAIL\n"), TestResult.FAIL
        ),
    )

    (tmp_path / "tests").mkdir()

    TestOutputWriter(tmp_path).report_changed(report)

    assert (tmp_path / "tests" / "results" / "nested" / "check.py.out").read_text(
        encoding="utf-8"
    ) == "6 Tests 1 Failures 0 Ignored\nFAIL\n"


def test_output_writer_uses_test_dirs_from_project_config(tmp_path):
    (tmp_path / ".ottu").write_text(
        "version: 1\ntest_dirs: [fixtures]\nbackend: debug\n", encoding="utf-8"
    )
    (tmp_path / "fixtures").mkdir()
    report = TestReport(
        TestPath(
            tmp_path / "fixtures" / "wifi" / "ap.ino",
            Path("fixtures/wifi/ap.ino"),
            Path("fixtures/wifi/ap.ino"),
            "ap.ino",
        ),
        TestStatus.DONE,
        output=TestOutput(("OK\n",), TestResult.PASS),
    )

    TestOutputWriter(tmp_path, tmp_path).report_changed(report)

    assert (tmp_path / "fixtures" / "results" / "wifi" / "ap.ino.out").read_text(
        encoding="utf-8"
    ) == "OK\n"


def test_output_writer_uses_project_relative_path_outside_working_dir(tmp_path):
    report = TestReport(
        TestPath(
            tmp_path / "project" / "tests" / "check.py",
            Path("../project/tests/check.py"),
            Path("tests/check.py"),
            "check.py",
        ),
        TestStatus.DONE,
        output=TestOutput(("FAIL\n",), TestResult.FAIL),
    )

    TestOutputWriter(tmp_path).report_changed(report)

    assert (tmp_path / "results" / "tests" / "check.py.out").read_text(
        encoding="utf-8"
    ) == "FAIL\n"


def test_output_writer_keeps_one_line_per_stripped_output_line(tmp_path):
    test_path = TestPath(tmp_path / "check.py", Path("check.py"), None, "check.py")
    report = TestReport(
        test_path,
        TestStatus.DONE,
        output=TestOutput(("TEST(a) PASS", "kept\r\n", "OK"), TestResult.PASS),
    )

    TestOutputWriter(tmp_path).report_changed(report)

    assert (tmp_path / "results" / "check.py.out").read_bytes() == (
        b"TEST(a) PASS\nkept\r\nOK\n"
    )


def test_report_changed_renders_the_report(capsys):
    CliOutput().report_changed(make_report("check.py", TestResult.PASS))

    assert "PASS" in capsys.readouterr().out


def test_test_name_drops_the_tests_directory_prefix():
    test_path = TestPath(
        Path("/project/tests/wifi/ap.ino"),
        Path("tests/wifi/ap.ino"),
        None,
        "ap.ino",
    )

    assert CliOutput._test_name(test_path) == "wifi/ap.ino"


def test_output_writer_uses_test_dir_of_a_separate_project_root(tmp_path):
    project = tmp_path / "project"
    working_dir = project / "sub"
    working_dir.mkdir(parents=True)
    (project / "tests").mkdir()
    report = TestReport(
        TestPath(
            project / "tests" / "check.py",
            Path("../tests/check.py"),
            Path("tests/check.py"),
            "check.py",
        ),
        TestStatus.DONE,
        output=TestOutput(("OK\n",), TestResult.PASS),
    )

    TestOutputWriter(working_dir, project).report_changed(report)

    assert (project / "tests" / "results" / "check.py.out").read_text(
        encoding="utf-8"
    ) == "OK\n"


def test_output_writer_ignores_incomplete_reports(tmp_path):
    test_path = TestPath(tmp_path / "check.py", Path("check.py"), None, "check.py")
    writer = TestOutputWriter(tmp_path)

    writer.report_changed(
        TestReport(
            test_path,
            TestStatus.EXECUTING,
            output=TestOutput(("partial\n",), TestResult.UNVERIFIED),
        )
    )
    writer.report_changed(TestReport(test_path, TestStatus.DONE))

    assert not (tmp_path / "results").exists()


def test_report_all_sizes_columns_to_longest_report():
    output = StringIO()
    CliOutput.report_all(
        [
            make_report("short.py", TestResult.PASS, device="one"),
            make_report(
                "hello-universe.ino",
                TestResult.FAIL,
                device="infineon:psoc6:cy8ckit_062s2_ai",
            ),
        ],
        console=Console(file=output, width=200),
    )

    assert "short.py" in output.getvalue()
    assert "hello-universe.ino" in output.getvalue()
    widths = CliOutput._column_widths(
        [
            make_report("short.py", TestResult.PASS, device="one"),
            make_report(
                "hello-universe.ino",
                TestResult.FAIL,
                device="infineon:psoc6:cy8ckit_062s2_ai",
            ),
        ]
    )
    assert len(widths) == 2
    text = CliOutput._report_text(
        make_report("short.py", TestResult.PASS, device="one"), widths
    ).plain
    assert text.endswith("PASS")
    assert text == "short.py" + " " * (widths[0] - len("short.py") + 2) + "PASS"


def test_progress_sizes_columns_to_longest_report(monkeypatch):
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
        "done",
        device=Device.from_string("infineon:psoc6:cy8ckit_062s2_ai"),
        result="FAIL",
    )

    table = progress._live.renderable
    assert table.columns[0].width == len("hello-universe.ino")
    assert table.columns[1].width == len("building") + 2


def test_progress_prints_final_status_without_live_spinner(capsys):
    progress = CliOutput()

    progress.update(make_test("check.py").test_path, "done", result="PASS")
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
    progress.update(make_test("hello-world").test_path, "done", result="PASS")
    progress.finish()

    assert spinner is not None
    assert spinner.name == "dots6"
    assert progress._reports[0].status is TestStatus.DONE
    assert progress._reports[0].result is TestResult.PASS
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

    progress.update(make_test("check.py").test_path, "done", result="PASS")
    progress.finish()

    assert live is not None
    assert live.stopped
    assert progress._live is None
    assert progress._spinners == {}


def test_progress_does_not_leave_blank_line_before_separator():
    output = StringIO()
    console = Console(
        file=output,
        width=80,
        force_terminal=True,
        color_system="standard",
    )
    progress = CliOutput(console=console)
    test_path = make_test("check.py").test_path

    progress.begin_suite("smoke", (), (test_path,))
    progress.update(test_path, "building")
    progress.update(test_path, "done", result="PASS")
    progress.finish()

    rendered = output.getvalue()
    assert "\x1b[0m  \n\x1b[?25h- " in rendered
    assert "\n\n" not in rendered


def test_progress_keeps_multiple_reports_in_one_live_render(monkeypatch):
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

    assert [CliOutput._test_name(report.test_path) for report in progress._reports] == [
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
        (CliOutput._test_name(report.test_path), CliOutput._device_name(report.device))
        for report in progress._reports
    ] == [
        ("check.py", "/dev/ttyUSB0"),
        ("check.py", "/dev/ttyUSB1"),
    ]


def test_report_devices_indexes_test_and_omits_device_from_result():
    output = StringIO()
    console = Console(file=output, width=160)
    cli_output = CliOutput(console=console)
    device = Device.from_string("name=board,uid=0123456789abcdef,address=/dev/ttyUSB0")
    second_device = Device.from_string("name=board-2,uid=abcdef,address=/dev/ttyUSB1")

    test_path = make_test("check.py", device).test_path
    cli_output.begin_suite("smoke", (device, second_device), (test_path,))
    cli_output.report_changed(
        TestReport(
            test_path,
            TestStatus.DONE,
            device=device,
            output=TestOutput((), TestResult.PASS),
            job_id="1",
        )
    )
    cli_output.finish()

    lines = output.getvalue().splitlines()
    report = output.getvalue()
    assert report.index("> suite : smoke") < report.index("> device [1]")
    assert report.index("> device [1]") < report.index("  name    : board")
    assert report.index("  address : /dev/ttyUSB0") < report.index("[1] check.py")
    assert report.index("[1] check.py") < report.index("1 passed")
    assert "> device [2]\n  name    : board-2\n  uid     : abcdef\n" in report
    assert "  address : /dev/ttyUSB1" in report
    device_details = [
        line for line in lines if line.startswith(("  name", "  uid", "  address"))
    ]
    values = (
        "board",
        "0123456789abcdef",
        "/dev/ttyUSB0",
        "board-2",
        "abcdef",
        "/dev/ttyUSB1",
    )
    assert [line.index(":") for line in device_details] == [10] * 6
    assert [line.index(value) for line, value in zip(device_details, values)] == [
        12
    ] * 6
    separators = [
        line
        for line in lines
        if line and set(line).issubset({"─", "-", " "}) and set(line) != {" "}
    ]
    content_lines = [line for line in lines if line and line not in separators]
    assert separators
    assert len({len(line) for line in separators}) == 1
    separator_line_indices = [
        index for index, line in enumerate(lines) if line in separators
    ]
    assert "-" in separators[2]
    assert set(separators[2]).issubset({"-", " "})
    assert "-" in separators[3]
    assert set(separators[3]).issubset({"-", " "})
    assert set(separators[-1]) == {"─"}
    assert (
        separator_line_indices[3] < lines.index("1 passed") < separator_line_indices[4]
    )
    assert all(len(line) <= max(map(len, content_lines)) for line in separators)
    assert max(map(len, separators)) == max(map(len, content_lines))
    test_result_line = next(line for line in lines if "[1] check.py" in line)
    assert "PASS" in test_result_line
    assert "[1] check.py [1]" not in test_result_line
    assert "/dev/ttyUSB0" not in test_result_line
    assert "1 passed" in report


def test_device_output_colors_prefix_and_keys():
    output = StringIO()
    console = Console(file=output, force_terminal=True, color_system="standard")
    device = Device.from_string("name=board,uid=0123456789abcdef,address=/dev/ttyUSB0")

    for line in CliOutput._device_lines(1, device):
        console.print(line)

    rendered = output.getvalue()
    assert "\x1b[36m> device [1]\x1b[0m" in rendered
    assert "\x1b[35mname\x1b[0m   \x1b[35m : \x1b[0mboard" in rendered
    assert "\x1b[35muid\x1b[0m    \x1b[35m : \x1b[0m0123456789abcdef" in rendered
    assert "\x1b[35maddress\x1b[0m\x1b[35m : \x1b[0m/dev/ttyUSB0" in rendered


def test_spaced_separators_are_uncolored_but_continuous_separators_are_blue():
    output = StringIO()
    console = Console(file=output, force_terminal=True, color_system="standard")
    cli_output = CliOutput(console=console)
    cli_output._separator_width = 5

    cli_output._print_separator(spaced=True)
    cli_output._print_separator()

    assert output.getvalue() == "- - -\n\x1b[34m─────\x1b[0m\n"
