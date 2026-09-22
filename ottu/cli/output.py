"""Human-readable reporting for the Ottu command line."""

import sys

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ottu.result import TestResult, TestStatus


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
        self._spinners: dict[tuple[str, str | None], Spinner] = {}

    @staticmethod
    def report(result: TestResult, *, console: Console | None = None) -> None:
        """Print one test result."""
        console = console or Console(file=sys.stdout)
        status = (
            "[bold green]PASS[/bold green]"
            if result.passed
            else "[bold red]FAIL[/bold red]"
        )
        device = result.device or ""
        console.print(f"{result.test_name:<40} {device:<24} {status}")

    @classmethod
    def report_all(
        cls, results: list[TestResult], *, console: Console | None = None
    ) -> None:
        """Print all test results."""
        for result in results:
            cls.report(result, console=console)

    def update(self, name: str, status: str, device: str | None = None) -> None:
        result = TestResult(name, TestStatus(status), device=device)
        result_key = (name, device)
        result_index = next(
            (
                index
                for index, current in enumerate(self._results)
                if (current.test_name, current.device) == result_key
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
                    self._final_text(result.test_name, status, result.device)
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
        self.update(result.test_name, result.status.value, result.device)

    def _render_results(self) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column(width=40, no_wrap=True)
        table.add_column(width=24, no_wrap=True)
        table.add_column(width=12, no_wrap=True)
        table.add_column(width=2, no_wrap=True)
        for result in self._results:
            result_key = (result.test_name, result.device)
            spinner = self._spinners.get(result_key)
            status = self._status_text(result.status.value)
            table.add_row(
                Text(result.test_name),
                Text(result.device or ""),
                status,
                spinner or "",
            )
        return table

    @classmethod
    def _final_text(cls, name: str, status: str, device: str | None = None) -> Text:
        text = Text(f"{name:<40} {device or '':<24} ")
        text.append(status, style=cls._STATUS_COLORS[status])
        return text

    @classmethod
    def _status_text(cls, status: str) -> Text:
        text = Text()
        text.append(status, style=cls._STATUS_COLORS[status])
        return text
