"""The ``ottu run`` command."""

from pathlib import Path

import click

from ottu.backend import Backend
from ottu.cli.context import CliContext
from ottu.cli.output import CliOutput
from ottu.suite import Suite
from ottu.test_path import TestPathContext


@click.command()
@click.argument("tests", nargs=-1)
@click.option("--exclude", "-x", multiple=True, type=str, help="Tests to exclude.")
@click.option(
    "--device",
    multiple=True,
    type=str,
    help="Device identifier or comma-separated device key=value values.",
)
@click.option(
    "--dev-list",
    type=click.Path(path_type=Path),
    default=None,
    help="Device list YAML file the --device values are resolved against.",
)
@click.option(
    "--count",
    "-c",
    type=str,
    help="Device count or comma-separated role=count values.",
)
@click.option(
    "--jobs",
    "-j",
    default=1,
    type=click.IntRange(min=1),
    show_default=True,
    help="Maximum number of concurrent jobs.",
)
@click.pass_obj
def run(
    cli_ctx: CliContext,
    tests: tuple[str, ...],
    exclude: tuple[str, ...],
    device: tuple[str, ...],
    dev_list: Path | None,
    count: str | None,
    jobs: int,
) -> None:
    """Run the main command with the given CLI context."""

    cli_output = CliOutput()
    suite = Suite.from_inputs(
        tests,
        context=TestPathContext.load(
            working_dir=cli_ctx.working_dir,
            project_root=cli_ctx.project_root,
        ),
        exclude=exclude,
        devices=device,
        dev_list=dev_list,
        count=count,
        jobs=jobs,
        backend=Backend.load(
            project_root=cli_ctx.project_root,
        ),
        observers=(cli_output,),
    )
    try:
        suite.run()
    finally:
        cli_output.finish()
