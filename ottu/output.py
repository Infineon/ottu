"""User-facing terminal output for Ottu."""

import sys

from rich.console import Console


class Output:
    """User-facing output for test and suite execution."""

    @staticmethod
    def print_test_result(
        test_name: str, passed: bool, *, console: Console | None = None
    ) -> None:
        """Print one colored test result for a human-readable CLI run."""
        console = console or Console(file=sys.stdout)
        status = (
            "[bold green]PASS[/bold green]" if passed else "[bold red]FAIL[/bold red]"
        )
        console.print(f"{test_name:<40} {status}")
