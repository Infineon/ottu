"""Structured results produced by Ottu test execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ottu.device import Device
from ottu.output import TestOutcome, TestOutput
from ottu.test_path import TestPath


class TestStatus(str, Enum):
    """Lifecycle statuses emitted while one test executes."""

    CONNECTING = "connecting"
    BUILDING = "building"
    FLASHING = "flashing"
    EXECUTING = "executing"
    DONE = "done"


@dataclass(frozen=True)
class TestResult:
    """Lifecycle result of one resolved test path.

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
    def outcome(self) -> TestOutcome | None:
        """The verdict of the test, if its output has been interpreted."""
        return self.output.outcome if self.output is not None else None

    @property
    def passed(self) -> bool:
        """Whether the test finished with a passing outcome."""
        return self.outcome is TestOutcome.PASS


class TestResultObserver(Protocol):
    """Observer notified when a test result changes status."""

    def result_changed(self, result: TestResult) -> None:
        """Handle one lifecycle result."""
