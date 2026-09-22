"""Structured results produced by Ottu test execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Protocol

from ottu.device import DeviceConnection


class TestStatus(str, Enum):
    """Statuses emitted while one test executes."""

    __test__ = False

    CONNECTING = "connecting"
    BUILDING = "building"
    FLASHING = "flashing"
    EXECUTING = "executing"
    PASSED = "PASS"
    FAILED = "FAIL"


@dataclass(frozen=True)
class TestOutput:
    """Captured output and its interpreted test status."""

    __test__ = False

    lines: tuple[str, ...]
    status: TestStatus | None = None


Clock = Callable[[], float]


class TestOutputParser:
    """Read and interpret output from an open device connection."""

    __test__ = False

    @classmethod
    def from_test_path(
        cls,
        test_path: str | Path,
        *,
        idle_timeout: float = 5.0,
        clock: Clock = monotonic,
    ) -> TestOutputParser:
        """Select an expected-output parser when a sibling .exp file exists."""
        path = Path(test_path)
        expected_output_path = path.with_name(f"{path.name}.exp")
        if expected_output_path.is_file():
            return ExpectedOutputParser(
                expected_output_path,
                idle_timeout=idle_timeout,
                clock=clock,
            )
        return cls(idle_timeout=idle_timeout, clock=clock)

    def __init__(
        self,
        *,
        idle_timeout: float = 5.0,
        clock: Clock = monotonic,
    ) -> None:
        self._idle_timeout = idle_timeout
        self._clock = clock

    def parse(self, connection: DeviceConnection) -> TestOutput:
        """Read output until idle and return captured output and status."""
        idle_deadline = self._clock() + self._idle_timeout
        lines: list[str] = []
        while True:
            line = connection.readline()
            if not line:
                if self._clock() >= idle_deadline:
                    break
                continue
            lines.append(self.line_parser(line))
            idle_deadline = self._clock() + self._idle_timeout
        return self.all_lines_parser(lines)

    def line_parser(self, line: bytes) -> str:
        """Parse a single output line."""
        return line.decode(errors="replace").rstrip("\r\n")

    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        """Parse captured lines into a test output."""
        return TestOutput(tuple(lines))


class ExpectedOutputParser(TestOutputParser):
    """Compare captured output with an expected-output file."""

    def __init__(
        self,
        expected_output_path: str | Path,
        *,
        idle_timeout: float = 5.0,
        clock: Clock = monotonic,
    ) -> None:
        super().__init__(idle_timeout=idle_timeout, clock=clock)
        self._expected_output_path = Path(expected_output_path)

    def line_parser(self, line: bytes) -> str:
        """Decode output without removing its line ending."""
        return line.decode(errors="replace")

    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        """Pass only when captured lines match the expected-output file."""
        with self._expected_output_path.open(newline="") as expected_output:
            expected_lines = tuple(expected_output.read().splitlines(keepends=True))
        output_lines = tuple(lines)
        status = (
            TestStatus.PASSED if output_lines == expected_lines else TestStatus.FAILED
        )
        return TestOutput(output_lines, status)


@dataclass(frozen=True)
class TestResult:
    """Lifecycle result of one resolved test."""

    __test__ = False

    test_name: str
    status: TestStatus
    output: TestOutput | None = None
    message: str | None = None
    device: str | None = None

    @property
    def passed(self) -> bool:
        """Whether the test reached a passing terminal status."""
        return self.status is TestStatus.PASSED


class TestResultObserver(Protocol):
    """Observer notified when a test result changes status."""

    def result_changed(self, result: TestResult) -> None:
        """Handle one lifecycle result."""
