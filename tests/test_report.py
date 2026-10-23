"""Test report tests."""

import queue
from dataclasses import replace

from ottu.output import TestOutput, TestResult
from ottu.report import (
    QueueTestReportNotifier,
    QueueTestReportObserver,
    TestReport,
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


def test_queue_observer_publishes_report_with_job_id():
    """The child queue observer tags reports with their job id."""
    queued = []

    class FakeQueue:
        def put(self, report):
            queued.append(report)

    report = make_report(TestStatus.BUILDING)

    QueueTestReportObserver(FakeQueue(), "1").report_changed(report)

    assert queued == [replace(report, job_id="1")]


def test_queue_notifier_tracks_registered_processes():
    """The notifier reports whether registered processes are running."""

    class FakeProcess:
        def __init__(self, running):
            self.running = running

        def is_alive(self):
            return self.running

    notifier = QueueTestReportNotifier()
    notifier.register_process(FakeProcess(False))
    assert not notifier.processes_running

    notifier.register_process(FakeProcess(True))
    assert notifier.processes_running


def test_queue_notifier_forwards_queued_reports_to_observers():
    """The notifier forwards labeled reports to final observers."""

    class FakeQueue:
        def __init__(self, report):
            self.report = report

        def get_nowait(self):
            if self.report is None:
                raise queue.Empty
            report = self.report
            self.report = None
            return report

    class RecordingObserver:
        def __init__(self):
            self.reports = []

        def report_changed(self, report):
            self.reports.append(report)

    report = replace(make_report(TestStatus.BUILDING), job_id="1")
    recording_observer = RecordingObserver()
    notifier = QueueTestReportNotifier(
        (recording_observer,),
        event_queue=FakeQueue(report),
    )

    assert notifier.notify() == [report]
    assert recording_observer.reports == [report]
