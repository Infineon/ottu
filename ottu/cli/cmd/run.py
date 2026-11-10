"""The ``ottu run`` command."""

from pathlib import Path

import click

from ottu.backend import Backend
from ottu.cli.context import CliContext
from ottu.cli.output import CliOutput
from ottu.cli.parse import (
    parse_suite_count,
    parse_suite_device_input,
    parse_suite_input,
)
from ottu.plan import Plan
from ottu.report import TestOutputExporter
from ottu.suite import SuiteBuilder
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
    help="Device identifier or comma-separated device key=value values, "
    "optionally qualified with role=ROLE. "
    "Repeat for alternatives (OR). With --plan, each value is combined (AND) "
    "with every requires.device of a suite; suites it conflicts with or that "
    "have too few matching devices in --dev-list are skipped.",
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
    help="Test repetition count or comma-separated role=count values. "
    "Overrides the plan's counts.",
)
@click.option(
    "--jobs",
    "-j",
    default=1,
    type=click.IntRange(min=1),
    show_default=True,
    help="Maximum number of concurrent jobs; also applies to plan suites.",
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
        TestOutputExporter(cli_ctx.working_dir, cli_ctx.project_root),
    )

    if plan is None:
        suite_input = parse_suite_input(tests, exclude, count, device)
        suites = [
            SuiteBuilder.build(
                context,
                suite_input,
                dev_list,
                jobs,
                backend=backend,
                observers=observers,
                name="Test run",
            )
        ]
    else:
        suites = Plan.from_file(plan).build_suites(
            context,
            tests,
            exclude,
            parse_suite_count(count) if count else None,
            [parse_suite_device_input(value) for value in device],
            dev_list,
            jobs,
            backend=backend,
            observers=observers,
        )
    try:
        for suite in suites:
            suite.run()
            cli_output.finish()
    finally:
        cli_output.finish()
