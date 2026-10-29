"""Structured reports produced by Ottu test execution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty
from typing import Protocol

from ottu.config_models.project.config import ProjectConfig
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


class TestOutputExporter:
    """Export the output of each finished test to a file in the results directory."""

    def __init__(self, working_dir: Path, project_root: Path | None = None) -> None:
        """
        Place results in the first configured test directory,
        else the working dir.
        """
        roots = [working_dir.resolve()]
        if project_root is not None and project_root.resolve() not in roots:
            roots.append(project_root.resolve())
        configured = ProjectConfig.from_project_root(project_root).test_dirs
        self._test_dirs = [
            root / test_dir
            for root in roots
            for test_dir in configured
            if (root / test_dir).is_dir()
        ]
        base = self._test_dirs[0] if self._test_dirs else roots[0]
        self._result_dir = base / "results"

    def report_changed(self, report: TestReport) -> None:
        """Persist the captured output when a test finishes."""
        if report.status is not TestStatus.DONE or report.output is None:
            return

        absolute_path = report.test_path.absolute_path
        test_dir = next(
            (
                test_dir
                for test_dir in self._test_dirs
                if absolute_path.is_relative_to(test_dir)
            ),
            None,
        )
        if test_dir is not None:
            relative_path = absolute_path.relative_to(test_dir)
        else:
            relative_path = Path(report.test_path.working_dir_relative_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            relative_path = report.test_path.project_root_relative_path or Path(
                report.test_path.file_name
            )
        output_path = self._result_dir / relative_path.with_name(
            f"{relative_path.name}.out"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Unity lines arrive without their line ending; expected-output lines keep it.
        lines = (
            line if line.endswith(("\n", "\r")) else f"{line}\n"
            for line in report.output.lines
        )
        output_path.write_text("".join(lines), encoding="utf-8", newline="")


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
