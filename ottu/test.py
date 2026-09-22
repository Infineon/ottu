from collections.abc import Sequence
from dataclasses import dataclass, field

from ottu.backend import Backend
from ottu.device import Device
from ottu.result import (
    TestOutput,
    TestOutputParser,
    TestResult,
    TestResultObserver,
    TestStatus,
)
from ottu.test_path import TestPath, TestPathContext, TestPathResolver


@dataclass(frozen=True)
class TestOpts:
    """Execution options associated with one test."""

    __test__ = False

    role: str | None = None

    def __post_init__(self) -> None:
        self._validate_role(self.role)

    @staticmethod
    def _validate_role(role: str | None) -> None:
        """Reject empty or whitespace-only role names."""
        if role is not None and not role.strip():
            raise ValueError("Role must not be empty.")


@dataclass
class Test:
    # Prevent pytest from collecting this application class as a test class.
    __test__ = False

    test_path: TestPath
    options: TestOpts = field(default_factory=TestOpts)
    device: str | None = None
    backend: Backend | None = None
    observers: tuple[TestResultObserver, ...] = ()

    @classmethod
    def from_inputs(
        cls,
        test_selectors: Sequence[str],
        *,
        context: TestPathContext | None = None,
        exclude_test_selectors: Sequence[str] = (),
        options: TestOpts = TestOpts(),
        backend: Backend | None = None,
        observers: Sequence[TestResultObserver] = (),
    ) -> list["Test"]:
        """Resolve test selectors and create tests with supplied options."""
        context = context or TestPathContext()
        test_paths = TestPathResolver.resolve_all(
            test_selectors,
            context,
            exclude_test_selectors=exclude_test_selectors,
        )
        return [
            cls(
                test_path,
                options=options,
                backend=backend,
                observers=tuple(observers),
            )
            for test_path in test_paths
        ]

    def run(self) -> TestResult:
        """Run one resolved test and return its result."""
        if self.backend is None:
            raise ValueError("Test backend is required.")

        device = Device.from_string(self.device) if self.device else Device({})
        self._notify(TestStatus.CONNECTING, device=device.get("device"))
        connection = device.connect()
        output = None
        try:
            self.backend.run(
                self.test_path.absolute_path,
                device,
                observers=self.observers,
            )
            if connection is not None:
                self._notify(TestStatus.EXECUTING, device=device.get("device"))
                output = TestOutputParser.from_test_path(
                    self.test_path.absolute_path
                ).parse(connection)
        finally:
            if connection is not None:
                connection.close()
        return self._notify(
            output.status if output and output.status else TestStatus.PASSED,
            output=output,
            device=device.get("device"),
        )

    def _notify(
        self,
        status: TestStatus,
        *,
        output: TestOutput | None = None,
        device: str | None = None,
    ) -> TestResult:
        """Notify observers about a test status change."""
        result = TestResult(
            self.test_path.file_name,
            status,
            output=output,
            device=device,
        )
        for observer in self.observers:
            observer.result_changed(result)
        return result
