"""Structured reports produced by Ottu test execution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from multiprocessing import Process, Queue
from queue import Empty
from typing import Protocol

from ottu.device import Device
from ottu.output import TestOutput, TestResult
from ottu.test_path import TestPath


class TestStatus(str, Enum):
    """Lifecycle statuses emitted while one test executes."""

    CONNECTING = "connecting"
    BUILDING = "building"
    FLASHING = "flashing"
    EXECUTING = "executing"
    DONE = "done"


@dataclass(frozen=True)
class TestReport:
    """Lifecycle report of one resolved test path.

    The verdict comes from the output, so it is ``None`` until the test has
    produced an interpreted output.
    """

    test_path: TestPath
    status: TestStatus
    device: Device | None = None
    output: TestOutput | None = None
    message: str | None = None
    job_id: str | None = None

    @property
    def result(self) -> TestResult | None:
        """The verdict of the test, if its output has been interpreted."""
        return self.output.result if self.output is not None else None

    @property
    def passed(self) -> bool:
        """Whether the test finished with a passing result."""
        return self.result is TestResult.PASS


class TestReportObserver(Protocol):
    """Observer notified when a test report changes status."""

    def report_changed(self, report: TestReport) -> None:
        """Handle one lifecycle report."""


class TestReportNotifier:
    """Fan one test report out to every observer."""

    def __init__(self, observers: Sequence[TestReportObserver] = ()) -> None:
        self._observers = tuple(observers)

    def notify(self, report: TestReport) -> None:
        """Hand the report to each observer in order."""
        for observer in self._observers:
            observer.report_changed(report)


class QueueTestReportObserver:
    """Publish a child-process test report to a parent queue."""

    def __init__(
        self, event_queue: Queue[TestReport], job_id: str | None = None
    ) -> None:
        self._event_queue = event_queue
        self._job_id = job_id

    def report_changed(self, report: TestReport) -> None:
        """Queue one report from a parallel test execution."""
        self._event_queue.put(replace(report, job_id=self._job_id))

    @property
    def event_queue(self) -> Queue[TestReport]:
        """Return the queue this observer publishes to."""
        return self._event_queue


class QueueTestReportRelay:
    """Relay reports from parallel child processes to the final observers.
    The relay registers child processes, drains their test reports from
    the shared queue, and forwards them to a notifier."""

    def __init__(
        self,
        observers: Sequence[TestReportObserver] = (),
        *,
        event_queue: Queue[TestReport] | None = None,
    ) -> None:
        self._event_queue = event_queue if event_queue is not None else Queue()
        self._notifier = TestReportNotifier(observers)
        self._processes: list[Process] = []

    @property
    def event_queue(self) -> Queue[TestReport]:
        """Return the queue shared with child processes."""
        return self._event_queue

    @property
    def processes_running(self) -> bool:
        """Return whether any registered process is still running."""
        return any(self._is_alive(process) for process in self._processes)

    @staticmethod
    def _is_alive(process: Process) -> bool:
        is_alive = getattr(process, "is_alive", None)
        return bool(is_alive and is_alive())

    def register_process(self, process: Process) -> None:
        """Register a process whose reports this relay will forward."""
        self._processes.append(process)

    def forward(self) -> list[TestReport]:
        """Drain queued reports, notify the final observers, and return them."""
        reports: list[TestReport] = []
        while True:
            try:
                report = self._event_queue.get_nowait()
            except Empty:
                return reports
            reports.append(report)
            self._notifier.notify(report)
