"""Test report tests."""

import queue
from dataclasses import replace
from pathlib import Path

from ottu.output import TestOutput, TestResult
from ottu.report import (
    QueueTestReportObserver,
    QueueTestReportRelay,
    TestOutputExporter,
    TestReport,
    TestReportNotifier,
    TestStatus,
)
from ottu.test_path import TestPath


def make_report(status, result=None):
    return TestReport(
        TestPath("check.py", "check.py", None, "check.py"),
        status,
        output=TestOutput((), result) if result is not None else None,
    )


def test_report_passes_only_with_passing_result():
    assert make_report(TestStatus.DONE, TestResult.PASS).passed
    assert not make_report(TestStatus.DONE, TestResult.FAIL).passed
    assert not make_report(TestStatus.DONE, TestResult.UNVERIFIED).passed


def test_report_without_result_has_not_passed():
    assert not make_report(TestStatus.EXECUTING).passed


def test_report_result_comes_from_its_output():
    assert make_report(TestStatus.DONE, TestResult.FAIL).result is TestResult.FAIL
    assert make_report(TestStatus.DONE, TestResult.UNVERIFIED).result is (
        TestResult.UNVERIFIED
    )


def test_report_has_no_result_before_it_has_output():
    assert make_report(TestStatus.EXECUTING).result is None


def test_report_has_no_result_while_its_output_is_not_judged():
    report = TestReport(
        TestPath("check.py", "check.py", None, "check.py"),
        TestStatus.EXECUTING,
        output=TestOutput(("partial",)),
    )

    assert report.result is None
    assert not report.passed


class RecordingObserver:
    def __init__(self):
        self.reports = []

    def report_changed(self, report):
        self.reports.append(report)


def test_notifier_hands_each_report_to_every_observer_in_order():
    first, second = RecordingObserver(), RecordingObserver()
    building = make_report(TestStatus.BUILDING)
    flashing = make_report(TestStatus.FLASHING)

    notifier = TestReportNotifier((first, second))
    notifier.notify(building)
    notifier.notify(flashing)

    assert first.reports == [building, flashing]
    assert second.reports == [building, flashing]


def test_notifier_without_observers_does_nothing():
    TestReportNotifier().notify(make_report(TestStatus.DONE))


def test_queue_observer_publishes_report_with_job_id():
    """The child queue observer tags reports with their job id."""
    queued = []

    class FakeQueue:
        def put(self, report):
            queued.append(report)

    report = make_report(TestStatus.BUILDING)

    QueueTestReportObserver(FakeQueue(), "1").report_changed(report)

    assert queued == [replace(report, job_id="1")]


def test_queue_relay_tracks_registered_processes():
    """The relay reports whether registered processes are running."""

    class FakeProcess:
        def __init__(self, running):
            self.running = running

        def is_alive(self):
            return self.running

    relay = QueueTestReportRelay()
    relay.register_process(FakeProcess(False))
    assert not relay.processes_running

    relay.register_process(FakeProcess(True))
    assert relay.processes_running


def test_queue_relay_forwards_queued_reports_to_observers():
    """The relay forwards labeled reports to final observers."""

    class FakeQueue:
        def __init__(self, report):
            self.report = report

        def get_nowait(self):
            if self.report is None:
                raise queue.Empty
            report = self.report
            self.report = None
            return report

    report = replace(make_report(TestStatus.BUILDING), job_id="1")
    recording_observer = RecordingObserver()
    relay = QueueTestReportRelay(
        (recording_observer,),
        event_queue=FakeQueue(report),
    )

    assert relay.forward() == [report]
    assert recording_observer.reports == [report]


def test_output_exporter_saves_test_output_under_relative_path(tmp_path):
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

    TestOutputExporter(tmp_path).report_changed(report)

    assert (tmp_path / "tests" / "results" / "nested" / "check.py.out").read_text(
        encoding="utf-8"
    ) == "6 Tests 1 Failures 0 Ignored\nFAIL\n"


def test_output_exporter_uses_test_dirs_from_project_config(tmp_path):
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

    TestOutputExporter(tmp_path, tmp_path).report_changed(report)

    assert (tmp_path / "fixtures" / "results" / "wifi" / "ap.ino.out").read_text(
        encoding="utf-8"
    ) == "OK\n"


def test_output_exporter_uses_project_relative_path_outside_working_dir(tmp_path):
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

    TestOutputExporter(tmp_path).report_changed(report)

    assert (tmp_path / "results" / "tests" / "check.py.out").read_text(
        encoding="utf-8"
    ) == "FAIL\n"


def test_output_exporter_keeps_one_line_per_stripped_output_line(tmp_path):
    test_path = TestPath(tmp_path / "check.py", Path("check.py"), None, "check.py")
    report = TestReport(
        test_path,
        TestStatus.DONE,
        output=TestOutput(("TEST(a) PASS", "kept\r\n", "OK"), TestResult.PASS),
    )

    TestOutputExporter(tmp_path).report_changed(report)

    assert (tmp_path / "results" / "check.py.out").read_bytes() == (
        b"TEST(a) PASS\nkept\r\nOK\n"
    )


def test_output_exporter_uses_test_dir_of_a_separate_project_root(tmp_path):
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

    TestOutputExporter(working_dir, project).report_changed(report)

    assert (project / "tests" / "results" / "check.py.out").read_text(
        encoding="utf-8"
    ) == "OK\n"


def test_output_exporter_ignores_incomplete_reports(tmp_path):
    test_path = TestPath(tmp_path / "check.py", Path("check.py"), None, "check.py")
    exporter = TestOutputExporter(tmp_path)

    exporter.report_changed(
        TestReport(
            test_path,
            TestStatus.EXECUTING,
            output=TestOutput(("partial\n",), TestResult.UNVERIFIED),
        )
    )
    exporter.report_changed(TestReport(test_path, TestStatus.DONE))

    assert not (tmp_path / "results").exists()


def test_output_exporter_falls_back_to_file_name_outside_working_dir(tmp_path):
    report = TestReport(
        TestPath(
            tmp_path / "elsewhere" / "check.py",
            Path("../elsewhere/check.py"),
            None,
            "check.py",
        ),
        TestStatus.DONE,
        output=TestOutput(("OK\n",), TestResult.PASS),
    )

    TestOutputExporter(tmp_path).report_changed(report)

    assert (tmp_path / "results" / "check.py.out").read_text(encoding="utf-8") == "OK\n"


def test_output_exporter_replaces_absolute_relative_path_with_file_name(tmp_path):
    report = TestReport(
        TestPath(
            tmp_path / "elsewhere" / "check.py",
            tmp_path / "elsewhere" / "check.py",
            None,
            "check.py",
        ),
        TestStatus.DONE,
        output=TestOutput(("OK\n",), TestResult.PASS),
    )

    TestOutputExporter(tmp_path).report_changed(report)

    assert (tmp_path / "results" / "check.py.out").is_file()


def test_output_exporter_writes_empty_file_for_empty_output(tmp_path):
    report = TestReport(
        TestPath(tmp_path / "check.py", Path("check.py"), None, "check.py"),
        TestStatus.DONE,
        output=TestOutput((), TestResult.UNVERIFIED),
    )

    TestOutputExporter(tmp_path).report_changed(report)

    assert (tmp_path / "results" / "check.py.out").read_bytes() == b""


def test_output_exporter_places_results_in_first_configured_test_dir(tmp_path):
    (tmp_path / ".ottu").write_text(
        "version: 1\ntest_dirs: [fixtures, tests]\nbackend: debug\n",
        encoding="utf-8",
    )
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "tests").mkdir()
    report = TestReport(
        TestPath(
            tmp_path / "tests" / "check.py",
            Path("tests/check.py"),
            Path("tests/check.py"),
            "check.py",
        ),
        TestStatus.DONE,
        output=TestOutput(("OK\n",), TestResult.PASS),
    )

    TestOutputExporter(tmp_path, tmp_path).report_changed(report)

    assert (tmp_path / "fixtures" / "results" / "check.py.out").read_text(
        encoding="utf-8"
    ) == "OK\n"
