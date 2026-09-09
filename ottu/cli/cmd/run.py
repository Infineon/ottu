"""The ``ottu run`` command."""

import click

from ottu.cli.context import CliContext
from ottu.suite import Suite
from ottu.test import TestPathContext


@click.command()
@click.argument("tests", nargs=-1)
@click.option(
    "--tests-dir",
    type=click.Path(path_type=str),
    help="Directory to search when discovering tests.",
)
@click.option(
    "--pattern",
    default=None,
    help="Glob pattern used for automatic test discovery.",
)
@click.option("--exclude", "-x", multiple=True, type=str, help="Tests to exclude.")
@click.option(
    "--count",
    "-c",
    type=str,
    help="Device count or comma-separated role=count values.",
)
@click.pass_obj
def run(
    cli_ctx: CliContext,
    tests: tuple[str, ...],
    tests_dir: str | None,
    pattern: str | None,
    exclude: tuple[str, ...],
    count: str | None,
) -> None:
    """Run the main command with the given CLI context."""
    test_inputs = () if pattern is not None else tests
    click.echo(f"Project root: {cli_ctx.project_root}")
    click.echo(f"Working directory: {cli_ctx.working_dir}")
    click.echo(f"Tests directory: {tests_dir}")
    click.echo(f"Tests: {test_inputs}")

    suite = Suite.from_inputs(
        test_inputs,
        context=TestPathContext(
            working_dir=cli_ctx.working_dir,
            project_root=cli_ctx.project_root,
            tests_dir=tests_dir,
            pattern=pattern or "**/*",
        ),
        exclude=exclude,
        count=count,
    )
    click.echo(f"Resolved tests: {[test.test_path for test in suite.tests]}")
    suite.run()
