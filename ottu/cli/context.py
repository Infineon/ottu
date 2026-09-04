"""Shared context for CLI commands."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CliContext:
    """CLI path state shared by commands."""

    project_root: Path | None
    working_dir: Path | None = None

    @classmethod
    def discover(
        cls, start: Path | str | None = None, working_dir: Path | str | None = None
    ) -> "CliContext":
        """Resolve CLI state from optional project and working directories."""
        project_root = cls.find_project_root(start)
        resolved_working_dir = Path(working_dir) if working_dir else Path.cwd()
        return cls(project_root=project_root, working_dir=resolved_working_dir)

    @staticmethod
    def find_project_root(start: Path | str | None = None) -> Path | None:
        """Find the nearest directory containing a ``.ottu`` marker."""
        start_path = Path(start) if start else Path.cwd()
        current = start_path
        while current != current.parent:
            if (current / ".ottu").exists():
                return current
            current = current.parent
        return None
