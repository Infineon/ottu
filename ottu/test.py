from collections.abc import Sequence
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
from ottu.test_path import TestPath, TestPathContext, TestPathResolver


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

    @classmethod
    def from_inputs(
        cls,
        test_selectors: Sequence[str],
        *,
        context: TestPathContext | None = None,
        exclude_test_selectors: Sequence[str] = (),
        options: TestOpts | None = None,
        backend: Backend | None = None,
        observers: Sequence[TestReportObserver] = (),
    ) -> list["Test"]:
        """Resolve test selectors and create tests.

        Without options, each test gets its own, and so its own output token.
        """
        context = context or TestPathContext()
        test_paths = TestPathResolver.resolve_all(
            test_selectors,
            context,
            exclude_test_selectors=exclude_test_selectors,
        )
        return [
            cls(
                test_path,
                options=options if options is not None else TestOpts(),
                backend=backend,
                observers=tuple(observers),
            )
            for test_path in test_paths
        ]

    def run(self) -> TestReport:
        """Run one resolved test and return its report."""
        if self.backend is None:
            raise ValueError("Test backend is required.")

        parser = TestOutputParser.create(
            self.test_path.absolute_path,
            self.options.output,
        )
        device = self.device or Device()
        device = device.acquire()
        self.device = device
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
