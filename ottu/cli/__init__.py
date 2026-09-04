"""Main CLI entry point for OTTU."""

import click

from ottu import __version__
from ottu.cli.command.run import run
from ottu.cli.context import CliContext


@click.group()
@click.option(
    "--project-root",
    type=click.Path(path_type=str),
    help="Override project root discovery.",
)
@click.option(
    "--working-dir",
    type=click.Path(path_type=str),
    help="Override the current working directory.",
)
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx: click.Context, project_root: str | None, working_dir: str | None) -> None:
    """ottu - On-target testing utility for embedded boards."""
    ctx.obj = CliContext.discover(start=project_root, working_dir=working_dir)


cli.add_command(run)


def main() -> None:
    """Entry point for the CLI."""
    cli()
