"""The ``ottu run`` command."""

from pathlib import Path

import click
from click.core import ParameterSource

from ottu.backend import Backend
from ottu.cli.context import CliContext
from ottu.cli.output import CliOutput, TestOutputWriter
from ottu.plan import Plan
from ottu.suite import Suite
from ottu.test_path import TestPathContext


@click.command()
@click.argument("tests", nargs=-1)
@click.option(
    "--exclude",
    "-x",
    multiple=True,
    type=str,
    help="Tests to exclude (suite names with --plan).",
)
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
@click.option(
    "--plan",
    "-P",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Test plan YAML file; TESTS and --exclude then select suite names.",
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
    plan: Path | None,
) -> None:
    """Run the main command with the given CLI context."""

    cli_output = CliOutput()
    context = TestPathContext.load(
        working_dir=cli_ctx.working_dir,
        project_root=cli_ctx.project_root,
    )
    backend = Backend.load(
        project_root=cli_ctx.project_root,
    )
    observers = (
        cli_output,
        TestOutputWriter(cli_ctx.working_dir, cli_ctx.project_root),
    )
    if plan is None:
        suites = [
            Suite.from_inputs(
                tests,
                context=context,
                exclude=exclude,
                devices=device,
                dev_list=dev_list,
                count=count,
                jobs=jobs,
                backend=backend,
                observers=observers,
            )
        ]
    else:
        _reject_plan_incompatible_options(count, jobs)
        test_plan = Plan.from_file(plan)
        suites = test_plan.build_suites(
            test_plan.select(tests, exclude),
            context=context,
            devices=device,
            dev_list=dev_list,
            backend=backend,
            observers=observers,
        )
    try:
        for suite in suites:
            suite.run()
    finally:
        cli_output.finish()


def _reject_plan_incompatible_options(count: str | None, jobs: int) -> None:
    """Reject options that a plan defines itself."""
    if count is not None:
        raise click.UsageError("--count cannot be used with --plan.")
    jobs_source = click.get_current_context().get_parameter_source("jobs")
    if jobs_source is ParameterSource.COMMANDLINE:
        raise click.UsageError("--jobs cannot be used with --plan.")
