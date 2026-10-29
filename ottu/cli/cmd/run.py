"""The ``ottu run`` command."""

from pathlib import Path

import click
from click.core import ParameterSource

from ottu.backend import Backend
from ottu.cli.context import CliContext
from ottu.cli.output import CliOutput, TestOutputWriter
from ottu.device import Device
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
        suite_names = ["Test run"]
    else:
        _reject_plan_incompatible_options(count, jobs)
        test_plan = Plan.from_file(plan)
        selected_suites = test_plan.select(tests, exclude)
        suites = test_plan.build_suites(
            selected_suites,
            context=context,
            devices=device,
            dev_list=dev_list,
            backend=backend,
            observers=observers,
        )
        suite_names = [
            suite.name or f"Suite {index}"
            for index, suite in enumerate(selected_suites, start=1)
        ]
    try:
        for suite_name, suite in zip(suite_names, suites, strict=True):
            acquired_devices = _acquire_suite_devices(suite)
            cli_output.begin_suite(
                suite_name,
                acquired_devices,
                tuple(test.test_path for test in suite.tests),
            )
            suite.run()
            cli_output.finish()
    finally:
        cli_output.finish()


def _reject_plan_incompatible_options(count: str | None, jobs: int) -> None:
    """Reject options that a plan defines itself."""
    if count is not None:
        raise click.UsageError("--count cannot be used with --plan.")
    jobs_source = click.get_current_context().get_parameter_source("jobs")
    if jobs_source is ParameterSource.COMMANDLINE:
        raise click.UsageError("--jobs cannot be used with --plan.")


def _acquire_suite_devices(suite: Suite) -> tuple[Device, ...]:
    """Acquire each selected device once and assign the acquired values."""
    devices = tuple(suite.resolved_devices) or tuple(
        test.device for test in suite.tests if test.device is not None
    )
    acquired_by_identity: dict[tuple[str | None, str | None, str | None], Device] = {}
    acquired_devices: list[Device] = []
    for device in devices:
        identity = _device_identity(device)
        if identity not in acquired_by_identity:
            acquired = device.acquire()
            acquired_by_identity[identity] = acquired
            acquired_devices.append(acquired)

    for test in suite.tests:
        if test.device is not None:
            test.device = acquired_by_identity[_device_identity(test.device)]

    suite.resolved_devices = tuple(acquired_devices)
    return tuple(acquired_devices)


def _device_identity(
    device: Device,
) -> tuple[str | None, str | None, str | None]:
    return device.name, device.get("uid"), device.get("address")
