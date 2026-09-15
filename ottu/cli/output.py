"""Human-readable reporting for the Ottu command line."""

import sys

from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from ottu.result import TestResult


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
        self._spinner: Spinner | None = None
        self._label: Text | None = None

    @staticmethod
    def report(result: TestResult, *, console: Console | None = None) -> None:
        """Print one test result."""
        console = console or Console(file=sys.stdout)
        status = (
            "[bold green]PASS[/bold green]"
            if result.passed
            else "[bold red]FAIL[/bold red]"
        )
        console.print(f"{result.test_name:<40} {status}")

    @classmethod
    def report_all(
        cls, results: list[TestResult], *, console: Console | None = None
    ) -> None:
        """Print all test results."""
        for result in results:
            cls.report(result, console=console)

    def update(self, name: str, status: str) -> None:
        if status in {"PASS", "FAIL"}:
            if self._live is not None:
                self._live.update(self._final_text(name, status))
                self._live.stop()
                self._live = None
                self._spinner = None
                self._label = None
            else:
                self._console.print(self._final_text(name, status))
            return

        if self._live is None:
            self._spinner = Spinner(
                "dots6",
                style=self._STATUS_COLORS.get(status),
            )
            self._label = self._stage_text(name, status)
            self._live = Live(
                Columns([self._label, self._spinner], expand=False, padding=(0, 0)),
                console=self._console,
                refresh_per_second=5,
            )
            self._live.start()
        else:
            self._label = self._stage_text(name, status)
            spinner = self._spinner
            assert spinner is not None
            spinner.style = self._STATUS_COLORS.get(status)
            self._live.update(
                Columns([self._label, spinner], expand=False, padding=(0, 0))
            )

    def result_changed(self, result: TestResult) -> None:
        """Render a typed execution result event."""
        self.update(result.test_name, result.status.value)

    @classmethod
    def _final_text(cls, name: str, status: str) -> Text:
        text = Text(f"{name:<40} ")
        text.append(status, style=cls._STATUS_COLORS[status])
        return text

    @classmethod
    def _stage_text(cls, name: str, status: str) -> Text:
        text = Text(f"{name:<40} ")
        text.append(status, style=cls._STATUS_COLORS.get(status))
        text.append(" ")
        return text
