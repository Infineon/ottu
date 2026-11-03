from dataclasses import dataclass, field

from ottu.backend import Backend
from ottu.device import Device
from ottu.output import (
    TestOutput,
    TestOutputOpts,
    TestOutputParser,
    TestResult,
)
from ottu.report import (
    TestReport,
    TestReportNotifier,
    TestReportObserver,
    TestStatus,
)
from ottu.test_path import TestPath


@dataclass(frozen=True)
class TestOpts:
    """Execution options associated with one test."""

    role: str | None = None
    output: TestOutputOpts = field(default_factory=TestOutputOpts)

    def __post_init__(self) -> None:
        self._validate_role(self.role)

    @staticmethod
    def _validate_role(role: str | None) -> None:
        """Reject empty or whitespace-only role names."""
        if role is not None and not role.strip():
            raise ValueError("Role must not be empty.")


@dataclass
class Test:
    test_path: TestPath
    options: TestOpts = field(default_factory=TestOpts)
    device: Device | None = None
    backend: Backend | None = None
    observers: tuple[TestReportObserver, ...] = ()
    notifier: TestReportNotifier = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.notifier = TestReportNotifier(self.observers)

    def run(self) -> TestReport:
        """Run one resolved test and return its report."""
        if self.backend is None:
            raise ValueError("Test backend is required.")
        device = self.device
        if device is None:
            raise ValueError("Test device is required.")

        parser = TestOutputParser.create(
            self.test_path.absolute_path,
            self.options.output,
        )
        self._notify(TestStatus.CONNECTING)
        connection = device.connect()
        output = None
        try:
            self.backend.run(
                self.test_path,
                device,
                notifier=self.notifier,
                defines=parser.opts.target_build_args(),
            )
            if connection is not None:
                self._notify(TestStatus.EXECUTING)
                output = parser.parse(connection)
        finally:
            if connection is not None:
                connection.close()
        if output is None:
            output = TestOutput((), TestResult.PASS)
        return self._notify(TestStatus.DONE, output=output)

    def _notify(
        self,
        status: TestStatus,
        *,
        output: TestOutput | None = None,
    ) -> TestReport:
        """Report a status change of this test to its observers."""
        report = TestReport(self.test_path, status, device=self.device, output=output)
        self.notifier.notify(report)
        return report
