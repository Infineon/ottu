"""Main CLI entry point for OTTU."""

import click

from ottu import __version__


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """ottu - On-target testing utility for embedded boards."""
    pass


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
