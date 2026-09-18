"""Declarative embedded backend execution."""

import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ottu.backend_builtins import BACKEND_BUILTINS
from ottu.config_models.project.config import ProjectConfig
from ottu.result import TestResult, TestResultObserver, TestStatus


@dataclass(frozen=True)
class Backend:
    """A YAML-defined backend with optional build and program commands."""

    build: tuple[str, ...] | None = None
    program: tuple[str, ...] | None = None

    @classmethod
    def load(cls, project_root: str | Path | None = None) -> "Backend":
        """Load the backend configured by a project configuration."""
        source = ProjectConfig.from_project_root(project_root).backend

        path = Path(source)
        if not path.is_absolute() and project_root is not None:
            path = Path(project_root) / path
        if path.is_file():
            return cls.from_yaml(path)
        return cls.from_name(source)

    @classmethod
    def from_name(cls, name: str) -> "Backend":
        """Load a built-in backend by name."""
        if name not in BACKEND_BUILTINS:
            raise ValueError(f"Unknown backend '{name}'.")
        return cls.from_mapping(BACKEND_BUILTINS[name])

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Backend":
        """Load a backend definition from a YAML file."""
        with Path(path).open(encoding="utf-8") as definition:
            value = yaml.safe_load(definition) or {}
        return cls.from_mapping(value)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Backend":
        """Build a backend from a parsed YAML mapping."""
        raw_steps = value
        commands = {
            name: cls._parse_command(name, raw_steps[name])
            for name in ("build", "program")
            if name in raw_steps
        }
        if not commands:
            raise ValueError("Backend must define at least one command.")
        return cls(**commands)

    @staticmethod
    def _parse_command(name: str, value: str | Sequence[str]) -> tuple[str, ...]:
        """Parse one command from a YAML string or argument sequence."""
        command = tuple(shlex.split(value)) if isinstance(value, str) else tuple(value)
        if not command or any(not isinstance(argument, str) for argument in command):
            raise ValueError(f"Backend command '{name}' must contain a command.")
        return command

    def run(
        self,
        test_path: str | Path,
        device: Mapping[str, Any],
        *,
        working_dir: str | Path | None = None,
        run_command: Callable[..., Any] = subprocess.run,
        observers: Sequence[TestResultObserver] = (),
    ) -> None:
        """Run backend commands for a resolved device."""
        variables = dict(device)
        variables.setdefault("device", "")
        variables["test_path"] = str(test_path)
        for configured_command, status in (
            (self.build, TestStatus.BUILDING),
            (self.program, TestStatus.FLASHING),
        ):
            if configured_command is None:
                continue
            command = tuple(
                argument.format_map(variables) for argument in configured_command
            )
            self._notify(observers, test_path, status)
            run_command(
                command,
                cwd=working_dir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

    @staticmethod
    def _notify(
        observers: Sequence[TestResultObserver],
        test_path: str | Path,
        status: TestStatus,
    ) -> None:
        """Notify observers about a backend execution stage."""
        if not observers:
            return
        result = TestResult(Path(test_path).name, status)
        for observer in observers:
            observer.result_changed(result)
