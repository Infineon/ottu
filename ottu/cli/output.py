"""Human-readable reporting for the Ottu command line."""

import sys
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ottu.device import Device
from ottu.result import TestResult, TestStatus
from ottu.test_path import TestPath


class CliOutput:
    """Render test results for a human-readable CLI run."""

    _STATUS_COLORS = {
        "connecting": "gray",
        "building": "blue",
        "flashing": "dark_orange",
        "executing": "purple",
        "PASS": "green",
        "FAIL": "red",
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
    ) -> None:
        result = TestResult(test_path, TestStatus(status), device=device, job_id=job_id)
        self._update_result(result)

    def _update_result(self, result: TestResult) -> None:
        """Store and render one result event."""
        name = self._test_name(result.test_path)
        device = self._device_name(result.device)
        job_id = result.job_id
        status = result.status.value
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

        if result.status in {TestStatus.PASSED, TestStatus.FAILED}:
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
            status = self._status_text(result.status.value)
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
            max((len(result.status.value) for result in results), default=0),
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
        text.append(result.status.value, style=cls._STATUS_COLORS[result.status.value])
        return text

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
