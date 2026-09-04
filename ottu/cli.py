"""Main CLI entry point for OTTU."""

from dataclasses import dataclass
from pathlib import Path

import click

from ottu import __version__


@dataclass(frozen=True)
class CliContext:
    """
    CLI context when ottu is invoked.
    This is required to correctly resolve paths arguments which
    are relative to the project root or to the current working directory.
    """

    project_root: Path | None
    working_dir: Path | None = None

    @classmethod
    def discover(
        cls, start: Path | str | None = None, working_dir: Path | str | None = None
    ) -> "CliContext":
        """
        Resolve CLI state from an optional project-root override
        and working directory override.
        """
        prj_root = cls.find_project_root(start)
        wk_dir = Path(working_dir) if working_dir else Path.cwd()
        return cls(project_root=prj_root, working_dir=wk_dir)

    @staticmethod
    def find_project_root(start: Path | str | None = None) -> Path | None:
        """
        Locate the project root given a starting path.
        The project root will contain a .ottu file indicating the
        root directory of the project.
        Walks up the directory tree from the starting path until
        it finds a directory containing a .ottu file or reaches the filesystem root.
        """
        start_path = Path(start) if start else Path.cwd()
        current = start_path
        while current != current.parent:
            if (current / ".ottu").exists():
                return current
            current = current.parent
        return None


##########################################################


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


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
