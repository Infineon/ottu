"""The ``ottu run`` command."""

import click

from ottu.backend import Backend
from ottu.cli.context import CliContext
from ottu.cli.output import CliOutput
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
    "--device",
    multiple=True,
    type=str,
    help="Device identifier or comma-separated device key=value values.",
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
@click.option(
    "--backend",
    default="debug",
    show_default=True,
    help="Built-in backend name or project-local YAML path.",
)
@click.pass_obj
def run(
    cli_ctx: CliContext,
    tests: tuple[str, ...],
    tests_dir: str | None,
    pattern: str | None,
    exclude: tuple[str, ...],
    device: tuple[str, ...],
    count: str | None,
    jobs: int,
    backend: str,
) -> None:
    """Run the main command with the given CLI context."""
    test_inputs = () if pattern is not None else tests
    selected_backend = Backend.from_name(backend, project_root=cli_ctx.project_root)

    cli_output = CliOutput()
    suite = Suite.from_inputs(
        test_inputs,
        context=TestPathContext(
            working_dir=cli_ctx.working_dir,
            project_root=cli_ctx.project_root,
            tests_dir=tests_dir,
            pattern=pattern or "**/*",
        ),
        exclude=exclude,
        devices=device,
        count=count,
        jobs=jobs,
        backend=selected_backend,
        observers=(cli_output,),
    )
    suite.run()
