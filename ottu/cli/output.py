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
        self._spinners: dict[tuple[str, str | None, str | None], Spinner] = {}

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
        job_id = report.job_id
        status = self._display_status(report)
        report_key = (name, device, job_id)
        report_index = next(
            (
                index
                for index, current in enumerate(self._reports)
                if (
                    self._test_name(current.test_path),
                    self._device_name(current.device),
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
                    self._report_text(report, self._column_widths([report])),
                    soft_wrap=True,
                )
            return

        self._live.update(self._render_reports())

    def finish(self) -> None:
        """Finalize the combined progress display after the suite completes."""
        if self._live is None:
            return
        self._live.update(self._render_reports())
        self._live.stop()
        self._live = None
        self._spinners.clear()

    def report_changed(self, report: TestReport) -> None:
        """Render a typed execution report event."""
        self._update_report(report)

    def _render_reports(self) -> Table:
        name_width, device_width, status_width = self._column_widths(self._reports)
        table = Table.grid(padding=(0, 6))
        table.add_column(width=name_width, no_wrap=True)
        table.add_column(width=device_width, no_wrap=True)
        table.add_column(width=status_width + 2, no_wrap=True)
        for report in self._reports:
            report_key = (
                self._test_name(report.test_path),
                self._device_name(report.device),
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
                Text(self._display_name(report.test_path, report.job_id)),
                Text(self._device_name(report.device)),
                status_column,
            )
        return table

    @classmethod
    def _column_widths(cls, reports: list[TestReport]) -> tuple[int, int, int]:
        """Return widths sized to the longest value in each report column."""
        return (
            max(
                (
                    len(cls._display_name(report.test_path, report.job_id))
                    for report in reports
                ),
                default=0,
            ),
            max(
                (len(cls._device_name(report.device)) for report in reports),
                default=0,
            ),
            max((len(cls._display_status(report)) for report in reports), default=0),
        )

    @classmethod
    def _report_text(cls, report: TestReport, widths: tuple[int, int, int]) -> Text:
        """Format one report using the supplied dynamic column widths."""
        name_width, device_width, _ = widths
        column_gap = "\t" * 6
        display_name = cls._display_name(report.test_path, report.job_id)
        text = Text(
            f"{display_name:<{name_width}}{column_gap}"
            f"{cls._device_name(report.device):<{device_width}}{column_gap}"
        )
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

    def report_changed(self, report: TestReport) -> None:
        """Persist the captured output when a test finishes."""
        if report.status is not TestStatus.DONE or report.output is None:
            return

        absolute_path = report.test_path.absolute_path
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
            relative_path = Path(report.test_path.working_dir_relative_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            relative_path = report.test_path.project_root_relative_path or Path(
                report.test_path.file_name
            )
        output_path = self._result_dir / relative_path.with_name(
            f"{relative_path.name}.out"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Unity lines arrive without their line ending; expected-output lines keep it.
        lines = (
            line if line.endswith(("\n", "\r")) else f"{line}\n"
            for line in report.output.lines
        )
        output_path.write_text("".join(lines), encoding="utf-8", newline="")
