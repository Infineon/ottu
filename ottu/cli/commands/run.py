"""The ``ottu run`` command."""

import click

from ottu.cli.context import CliContext
from ottu.test import TestPathResolver


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
@click.pass_obj
def run(
    cli_ctx: CliContext,
    tests: tuple[str, ...],
    tests_dir: str | None,
    pattern: str | None,
) -> None:
    """Run the main command with the given CLI context."""
    test_inputs = () if pattern is not None else tests
    click.echo(f"Project root: {cli_ctx.project_root}")
    click.echo(f"Working directory: {cli_ctx.working_dir}")
    click.echo(f"Tests directory: {tests_dir}")
    click.echo(f"Tests: {test_inputs}")

    test_list = TestPathResolver.validate_and_resolve_all(
        test_inputs,
        working_dir=cli_ctx.working_dir,
        project_root=cli_ctx.project_root,
        tests_dir=tests_dir,
        pattern=pattern or "**/*",
    )
    click.echo(f"Resolved tests: {test_list}")
