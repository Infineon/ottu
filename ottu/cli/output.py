"""Human-readable reporting for the Ottu command line."""

import sys
from pathlib import Path

from rich.cells import cell_len
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ottu.device import Device
from ottu.output import TestOutput, TestResult
from ottu.report import TestReport, TestStatus
from ottu.test_path import TestPath


class CliOutput:
    """Render test reports for a human-readable CLI run."""

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
        self._reports: list[TestReport] = []
        self._spinners: dict[tuple[str, str | int | None, str | None], Spinner] = {}
        self._device_indexes: dict[tuple[str | None, str | None, str | None], int] = {}
        self._suite_active = False
        self._separator_width = 0

    def begin_suite(
        self,
        name: str,
        devices: tuple[Device, ...],
        test_paths: tuple[TestPath, ...],
    ) -> None:
        """Start a suite report with its devices and fresh test results."""
        self._reports.clear()
        self._spinners.clear()
        self._device_indexes = {
            self._device_identity(device): index
            for index, device in enumerate(devices, start=1)
        }
        self._suite_active = True
        suite_line = Text(f"> suite : {name}")
        suite_line.stylize("blue", 0, len("> suite :"))
        device_lines = tuple(
            line
            for index, device in enumerate(devices, start=1)
            for line in self._device_lines(index, device)
        )
        test_lines = tuple(
            f"{self._display_name(path, len(devices) or None)}  UNVERIFIED"
            for path in test_paths
        )
        lines = [
            suite_line.plain,
            *(line.plain for line in device_lines),
            *test_lines,
        ]
        if not devices:
            lines.append("no devices")
        self._separator_width = max(cell_len(line) for line in lines)

        self._print_separator()
        self._console.print(suite_line)
        self._print_separator()
        for line in device_lines:
            self._print_line(line)
        if not devices:
            self._print_line(Text("no devices"))
        self._print_separator(spaced=True)

    @staticmethod
    def _device_lines(index: int, device: Device) -> tuple[Text, ...]:
        """Format one device as a colored heading and stacked values."""
        label = f"> device [{index}]"
        heading = Text(label, style="cyan")
        values = []
        key_width = max(map(len, ("name", "uid", "address")))
        for key in ("name", "uid", "address"):
            line = Text("  ")
            line.append(key, style="magenta")
            line.append(" " * (key_width - len(key)))
            line.append(" : ", style="magenta")
            line.append(str(device.get(key) or "-"))
            values.append(line)
        return (heading, *values)

    @staticmethod
    def report(report: TestReport, *, console: Console | None = None) -> None:
        """Print one test report."""
        console = console or Console(file=sys.stdout)
        widths = CliOutput._column_widths([report])
        console.print(CliOutput._report_text(report, widths), soft_wrap=True)

    @classmethod
    def report_all(
        cls, reports: list[TestReport], *, console: Console | None = None
    ) -> None:
        """Print all test reports."""
        console = console or Console(file=sys.stdout)
        widths = cls._column_widths(reports)
        for report in reports:
            console.print(cls._report_text(report, widths), soft_wrap=True)

    def update(
        self,
        test_path: TestPath,
        status: str,
        device: Device | None = None,
        job_id: str | None = None,
        result: str | None = None,
    ) -> None:
        report = TestReport(
            test_path,
            TestStatus(status),
            device=device,
            job_id=job_id,
            output=TestOutput((), TestResult(result)) if result is not None else None,
        )
        self._update_report(report)

    def _update_report(self, report: TestReport) -> None:
        """Store and render one report event."""
        name = self._test_name(report.test_path)
        device = self._device_name(report.device)
        device_index = self._device_index(report.device)
        job_id = report.job_id
        status = self._display_status(report)
        report_key = (
            name,
            device_index if device_index is not None else device,
            job_id,
        )
        report_index = next(
            (
                index
                for index, current in enumerate(self._reports)
                if (
                    self._test_name(current.test_path),
                    (
                        self._device_index(current.device)
                        if self._device_index(current.device) is not None
                        else self._device_name(current.device)
                    ),
                    current.job_id,
                )
                == report_key
            ),
            None,
        )
        if report_index is None:
            self._reports.append(report)
        else:
            self._reports[report_index] = report

        if report.status is TestStatus.DONE:
            self._spinners.pop(report_key, None)
        else:
            spinner = self._spinners.get(report_key)
            if spinner is None:
                spinner = Spinner("dots6", style=self._STATUS_COLORS.get(status))
                self._spinners[report_key] = spinner
            else:
                spinner.style = self._STATUS_COLORS.get(status)

        if self._live is None:
            if self._spinners:
                self._live = Live(
                    self._render_reports(),
                    console=self._console,
                    refresh_per_second=5,
                )
                self._live.start()
            else:
                self._console.print(
                    self._report_text(
                        report,
                        self._column_widths([report], self._device_indexes),
                        device_index,
                    ),
                    soft_wrap=True,
                )
            return

        self._live.update(self._render_reports())

    def finish(self) -> None:
        """Finalize test progress and print the suite result summary."""
        if self._live is not None:
            self._live.update(self._render_reports())
            self._live.stop()
            self._live = None
            if not self._console.is_terminal:
                self._console.print()
        self._spinners.clear()
        if not self._suite_active:
            return

        results = [report.result for report in self._reports]
        summary = [
            f"{count} {label}"
            for result, label in (
                (TestResult.PASS, "passed"),
                (TestResult.FAIL, "failed"),
                (TestResult.UNVERIFIED, "unverified"),
                (None, "incomplete"),
            )
            if (count := sum(item is result for item in results)) > 0
        ]
        summary_line = Text(", ".join(summary) if summary else "0 tests")
        self._print_separator(spaced=True)
        self._console.print(summary_line)
        self._print_separator()
        self._suite_active = False

    def _print_line(self, line: Text) -> None:
        self._console.print(line, soft_wrap=True)

    def _print_separator(self, *, spaced: bool = False) -> None:
        if spaced:
            line = ("- " * ((self._separator_width + 1) // 2))[: self._separator_width]
        else:
            line = "─" * self._separator_width
        separator = Text(line)
        if not spaced:
            separator.stylize("blue")
        self._console.print(separator, soft_wrap=True)

    def report_changed(self, report: TestReport) -> None:
        """Render a typed execution report event."""
        self._update_report(report)

    def _render_reports(self) -> Table:
        name_width, status_width = self._column_widths(
            self._reports, self._device_indexes
        )
        table = Table.grid(padding=(0, 2))
        table.add_column(width=name_width, no_wrap=True)
        table.add_column(width=status_width + 2, no_wrap=True)
        for report in self._reports:
            report_key = (
                self._test_name(report.test_path),
                (
                    self._device_index(report.device)
                    if self._device_index(report.device) is not None
                    else self._device_name(report.device)
                ),
                report.job_id,
            )
            spinner = self._spinners.get(report_key)
            status = self._status_text(self._display_status(report))
            if spinner:
                spinner_table = Table.grid(padding=(0, 1))
                spinner_table.add_column(no_wrap=True)
                spinner_table.add_column(no_wrap=True)
                spinner_table.add_row(status, spinner)
                status_column: Table | Text = spinner_table
            else:
                status_column = status
            table.add_row(
                Text(
                    self._display_name(
                        report.test_path,
                        self._device_index(report.device),
                    )
                ),
                status_column,
            )
        return table

    @classmethod
    def _column_widths(
        cls,
        reports: list[TestReport],
        device_indexes: dict[tuple[str | None, str | None, str | None], int]
        | None = None,
    ) -> tuple[int, int]:
        """Return widths sized to the longest value in each report column."""
        return (
            max(
                (
                    len(
                        cls._display_name(
                            report.test_path,
                            cls._device_index_from_map(report.device, device_indexes),
                        )
                    )
                    for report in reports
                ),
                default=0,
            ),
            max((len(cls._display_status(report)) for report in reports), default=0),
        )

    @classmethod
    def _report_text(
        cls,
        report: TestReport,
        widths: tuple[int, int],
        device_index: int | None = None,
    ) -> Text:
        """Format one report using the supplied dynamic column widths."""
        name_width, _ = widths
        column_gap = "  "
        display_name = cls._display_name(report.test_path, device_index)
        text = Text(f"{display_name:<{name_width}}{column_gap}")
        status = cls._display_status(report)
        text.append(status, style=cls._STATUS_COLORS[status])
        return text

    @staticmethod
    def _display_status(report: TestReport) -> str:
        """Return the result of a finished test, else its lifecycle status."""
        if report.status is TestStatus.DONE and report.result is not None:
            return str(report.result.value)
        return str(report.status.value)

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
    def _display_name(cls, test_path: TestPath, device_index: int | None = None) -> str:
        """Prefix a test path with its assigned device index."""
        name = cls._test_name(test_path)
        if device_index is not None:
            name = f"[{device_index}] {name}"
        return name

    @staticmethod
    def _device_name(device: Device | None) -> str:
        """Return the resolved device name for display."""
        if device is None:
            return ""
        return device.name or device.get("address") or ""

    @staticmethod
    def _device_identity(
        device: Device,
    ) -> tuple[str | None, str | None, str | None]:
        """Return the identifying values used to map a device to its index."""
        return device.name, device.get("uid"), device.get("address")

    def _device_index(self, device: Device | None) -> int | None:
        if device is None:
            return None
        return self._device_indexes.get(self._device_identity(device))

    @classmethod
    def _device_index_from_map(
        cls,
        device: Device | None,
        device_indexes: dict[tuple[str | None, str | None, str | None], int] | None,
    ) -> int | None:
        if device is None or device_indexes is None:
            return None
        return device_indexes.get(cls._device_identity(device))

    @classmethod
    def _status_text(cls, status: str) -> Text:
        text = Text()
        text.append(status, style=cls._STATUS_COLORS[status])
        return text
