"""Human-readable reporting for the Ottu command line."""

import sys
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ottu.config_models.project.config import ProjectConfig
from ottu.device import Device
from ottu.output import TestOutcome, TestOutput
from ottu.result import TestResult, TestStatus
from ottu.test_path import TestPath


class CliOutput:
    """Render test results for a human-readable CLI run."""

    _STATUS_COLORS = {
        "connecting": "gray",
        "building": "blue",
        "flashing": "dark_orange",
        "executing": "purple",
        "done": "green",
        "PASS": "green",
        "FAIL": "red",
        "UNVERIFIED": "yellow",
    }

    def __init__(self, *, console: Console | None = None) -> None:
        self._console = console or Console(file=sys.stdout)
        self._live: Live | None = None
        self._results: list[TestResult] = []
        self._spinners: dict[tuple[str, str | None, str | None], Spinner] = {}

    @staticmethod
    def report(result: TestResult, *, console: Console | None = None) -> None:
        """Print one test result."""
        console = console or Console(file=sys.stdout)
        widths = CliOutput._column_widths([result])
        console.print(CliOutput._result_text(result, widths), soft_wrap=True)

    @classmethod
    def report_all(
        cls, results: list[TestResult], *, console: Console | None = None
    ) -> None:
        """Print all test results."""
        console = console or Console(file=sys.stdout)
        widths = cls._column_widths(results)
        for result in results:
            console.print(cls._result_text(result, widths), soft_wrap=True)

    def update(
        self,
        test_path: TestPath,
        status: str,
        device: Device | None = None,
        job_id: str | None = None,
        outcome: str | None = None,
    ) -> None:
        result = TestResult(
            test_path,
            TestStatus(status),
            device=device,
            job_id=job_id,
            output=(
                TestOutput((), TestOutcome(outcome)) if outcome is not None else None
            ),
        )
        self._update_result(result)

    def _update_result(self, result: TestResult) -> None:
        """Store and render one result event."""
        name = self._test_name(result.test_path)
        device = self._device_name(result.device)
        job_id = result.job_id
        status = self._display_status(result)
        result_key = (name, device, job_id)
        result_index = next(
            (
                index
                for index, current in enumerate(self._results)
                if (
                    self._test_name(current.test_path),
                    self._device_name(current.device),
                    current.job_id,
                )
                == result_key
            ),
            None,
        )
        if result_index is None:
            self._results.append(result)
        else:
            self._results[result_index] = result

        if result.status is TestStatus.DONE:
            self._spinners.pop(result_key, None)
        else:
            spinner = self._spinners.get(result_key)
            if spinner is None:
                spinner = Spinner("dots6", style=self._STATUS_COLORS.get(status))
                self._spinners[result_key] = spinner
            else:
                spinner.style = self._STATUS_COLORS.get(status)

        if self._live is None:
            if self._spinners:
                self._live = Live(
                    self._render_results(),
                    console=self._console,
                    refresh_per_second=5,
                )
                self._live.start()
            else:
                self._console.print(
                    self._result_text(result, self._column_widths([result])),
                    soft_wrap=True,
                )
            return

        self._live.update(self._render_results())

    def finish(self) -> None:
        """Finalize the combined progress display after the suite completes."""
        if self._live is None:
            return
        self._live.update(self._render_results())
        self._live.stop()
        self._live = None
        self._spinners.clear()

    def result_changed(self, result: TestResult) -> None:
        """Render a typed execution result event."""
        self._update_result(result)

    def _render_results(self) -> Table:
        name_width, device_width, status_width = self._column_widths(self._results)
        table = Table.grid(padding=(0, 6))
        table.add_column(width=name_width, no_wrap=True)
        table.add_column(width=device_width, no_wrap=True)
        table.add_column(width=status_width + 2, no_wrap=True)
        for result in self._results:
            result_key = (
                self._test_name(result.test_path),
                self._device_name(result.device),
                result.job_id,
            )
            spinner = self._spinners.get(result_key)
            status = self._status_text(self._display_status(result))
            if spinner:
                spinner_table = Table.grid(padding=(0, 1))
                spinner_table.add_column(no_wrap=True)
                spinner_table.add_column(no_wrap=True)
                spinner_table.add_row(status, spinner)
                status_column: Table | Text = spinner_table
            else:
                status_column = status
            table.add_row(
                Text(self._display_name(result.test_path, result.job_id)),
                Text(self._device_name(result.device)),
                status_column,
            )
        return table

    @classmethod
    def _column_widths(cls, results: list[TestResult]) -> tuple[int, int, int]:
        """Return widths sized to the longest value in each result column."""
        return (
            max(
                (
                    len(cls._display_name(result.test_path, result.job_id))
                    for result in results
                ),
                default=0,
            ),
            max(
                (len(cls._device_name(result.device)) for result in results),
                default=0,
            ),
            max((len(cls._display_status(result)) for result in results), default=0),
        )

    @classmethod
    def _result_text(cls, result: TestResult, widths: tuple[int, int, int]) -> Text:
        """Format one result using the supplied dynamic column widths."""
        name_width, device_width, _ = widths
        column_gap = "\t" * 6
        display_name = cls._display_name(result.test_path, result.job_id)
        text = Text(
            f"{display_name:<{name_width}}{column_gap}"
            f"{cls._device_name(result.device):<{device_width}}{column_gap}"
        )
        status = cls._display_status(result)
        text.append(status, style=cls._STATUS_COLORS[status])
        return text

    @staticmethod
    def _display_status(result: TestResult) -> str:
        """Return the outcome of a finished test, else its lifecycle status."""
        if result.status is TestStatus.DONE and result.outcome is not None:
            return str(result.outcome.value)
        return str(result.status.value)

    @staticmethod
    def _test_name(test_path: TestPath) -> str:
        """Return the test path relative to the configured working directory."""
        relative_path = Path(test_path.working_dir_relative_path)
        if not relative_path.is_absolute() and relative_path.parts[0:1] in {
            ("test",),
            ("tests",),
        }:
            relative_path = Path(*relative_path.parts[1:])
        return (
            test_path.file_name
            if relative_path.is_absolute()
            else relative_path.as_posix()
        )

    @classmethod
    def _display_name(cls, test_path: TestPath, job_id: str | None) -> str:
        """Combine a test path with its job id for display."""
        name = cls._test_name(test_path)
        return f"{name} [{job_id}]" if job_id is not None else name

    @staticmethod
    def _device_name(device: Device | None) -> str:
        """Return the resolved device name for display."""
        if device is None:
            return ""
        return device.name or device.get("address") or ""

    @classmethod
    def _status_text(cls, status: str) -> Text:
        text = Text()
        text.append(status, style=cls._STATUS_COLORS[status])
        return text


class TestOutputWriter:
    """Write completed test output to per-test files."""

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

    def result_changed(self, result: TestResult) -> None:
        """Persist the captured output when a test finishes."""
        if result.status is not TestStatus.DONE or result.output is None:
            return

        absolute_path = result.test_path.absolute_path
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
            relative_path = Path(result.test_path.working_dir_relative_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            relative_path = result.test_path.project_root_relative_path or Path(
                result.test_path.file_name
            )
        output_path = self._result_dir / relative_path.with_name(
            f"{relative_path.name}.out"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Unity lines arrive without their line ending; expected-output lines keep it.
        lines = (
            line if line.endswith(("\n", "\r")) else f"{line}\n"
            for line in result.output.lines
        )
        output_path.write_text("".join(lines), encoding="utf-8", newline="")
