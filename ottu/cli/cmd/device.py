"""The ``ottu device`` command group."""

import json
from pathlib import Path

import click
import yaml

from ottu.cli.context import CliContext
from ottu.device import Device, DeviceQuery


@click.group()
def device() -> None:
    """Inspect devices."""


@device.command()
@click.argument("key")
@click.option(
    "--dev-list",
    required=True,
    type=click.Path(path_type=Path),
    help="Device list YAML file.",
)
@click.option(
    "--filter",
    "-f",
    "filters",
    multiple=True,
    help="A key=value filter; repeat the option to match any of them.",
)
@click.option(
    "--only-connected/--all",
    default=True,
    show_default=True,
    help="Only consider devices that are currently connected.",
)
@click.pass_obj
def query(
    cli_ctx: CliContext,
    key: str,
    dev_list: Path,
    filters: tuple[str, ...],
    only_connected: bool,
) -> None:
    """Print KEY for the devices in a device list that match the filters."""
    path = (cli_ctx.working_dir or Path.cwd()) / dev_list
    try:
        devices = Device.from_file(str(path))
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise click.ClickException(
            f"Cannot load device list '{path}': {error}"
        ) from error

    try:
        values = DeviceQuery.select(
            devices, key, filters, check_connected=only_connected
        )
    except ValueError as error:
        raise click.UsageError(str(error)) from error

    for value in values:
        click.echo(value if isinstance(value, str) else json.dumps(value))
