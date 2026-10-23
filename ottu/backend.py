"""Declarative embedded backend execution."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ottu.backend_builtins import BACKEND_BUILTINS
from ottu.config_models.project.config import ProjectConfig
from ottu.device import Device
from ottu.report import TestReport, TestReportNotifier, TestStatus
from ottu.test_path import TestPath


class BackendCommandError(subprocess.CalledProcessError):
    """A backend command failed; its message ends with the command's output.

    This is a ``CalledProcessError`` with the same constructor, so existing
    handlers and attributes keep working; only the message gains the last lines
    of the output, which is otherwise captured and lost.
    """

    OUTPUT_TAIL_LINES = 20

    def __str__(self) -> str:
        message = super().__str__()
        output = self.output if self.output is not None else b""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        lines = str(output).strip().splitlines()
        if not lines:
            return message
        tail = lines[-self.OUTPUT_TAIL_LINES :]
        omitted = len(lines) - len(tail)
        heading = f"Command output (last {len(tail)} lines):"
        if omitted:
            heading = f"Command output (last {len(tail)} of {len(lines)} lines):"
        return "\n".join([message, heading, *tail])


@dataclass(frozen=True)
class Backend:
    """A YAML-defined backend with optional build and program commands.

    ``define_prefix`` is written in front of every build define that fills the
    ``{defines}`` placeholder: ``-D`` for most compilers, or something else
    (even empty) for toolchains that take defines another way.
    """

    build: tuple[str, ...] | None = None
    program: tuple[str, ...] | None = None
    define_prefix: str = "-D"

    @classmethod
    def load(cls, project_root: str | Path | None = None) -> Backend:
        """Load the backend configured by a project configuration."""
        source = ProjectConfig.from_project_root(project_root).backend

        path = Path(source)
        if not path.is_absolute() and project_root is not None:
            path = Path(project_root) / path
        if path.is_file():
            return cls.from_yaml(path)
        return cls.from_name(source)

    @classmethod
    def from_name(cls, name: str) -> Backend:
        """Load a built-in backend by name."""
        if name not in BACKEND_BUILTINS:
            raise ValueError(f"Unknown backend '{name}'.")
        return cls.from_mapping(BACKEND_BUILTINS[name])

    @classmethod
    def from_yaml(cls, path: str | Path) -> Backend:
        """Load a backend definition from a YAML file."""
        with Path(path).open(encoding="utf-8") as definition:
            value = yaml.safe_load(definition) or {}
        return cls.from_mapping(value)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Backend:
        """Build a backend from a parsed YAML mapping."""
        raw_steps = value
        commands = {
            name: cls._parse_command(name, raw_steps[name])
            for name in ("build", "program")
            if name in raw_steps
        }
        if not commands:
            raise ValueError("Backend must define at least one command.")
        define_prefix = raw_steps.get("define_prefix", cls.define_prefix)
        if not isinstance(define_prefix, str):
            raise ValueError("Backend 'define_prefix' must be a string.")
        return cls(**commands, define_prefix=define_prefix)

    @staticmethod
    def _parse_command(name: str, value: str | Sequence[str]) -> tuple[str, ...]:
        """Parse one command from a YAML string or argument sequence."""
        command = tuple(shlex.split(value)) if isinstance(value, str) else tuple(value)
        if not command or any(not isinstance(argument, str) for argument in command):
            raise ValueError(f"Backend command '{name}' must contain a command.")
        return command

    def run(
        self,
        test_path: TestPath,
        device: Device,
        *,
        working_dir: str | Path | None = None,
        run_command: Callable[..., Any] = subprocess.run,
        notifier: TestReportNotifier | None = None,
        defines: Sequence[str] = (),
    ) -> None:
        """Run backend commands for a resolved device.

        Each stage is announced through the notifier, if given.
        ``defines`` are bare ``NAME=value`` strings for the build step only. They
        fill the ``{defines}`` placeholder, and a build command without it
        ignores them.
        """
        variables = device.backend_variables()
        variables.setdefault("device", "")
        variables["test_path"] = str(test_path.absolute_path)
        for configured_command, status, step_defines in (
            (self.build, TestStatus.BUILDING, defines),
            (self.program, TestStatus.FLASHING, ()),
        ):
            if configured_command is None:
                continue
            command = self._render(configured_command, variables, step_defines)
            if notifier is not None:
                notifier.notify(TestReport(test_path, status, device=device))
            try:
                run_command(
                    command,
                    cwd=working_dir,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            except subprocess.CalledProcessError as error:
                raise BackendCommandError(
                    error.returncode, error.cmd, error.output, error.stderr
                ) from error

    def _render(
        self,
        command: tuple[str, ...],
        variables: Mapping[str, str],
        defines: Sequence[str],
    ) -> tuple[str, ...]:
        """Render the placeholders of a command, expanding ``{defines}``.

        Alone as an argument, ``{defines}`` becomes one argument per define;
        inside a larger argument the defines are joined with spaces.
        """
        rendered_defines = [f"{self.define_prefix}{define}" for define in defines]
        values = {**variables, "defines": " ".join(rendered_defines)}
        arguments: list[str] = []
        for argument in command:
            if argument == "{defines}":
                arguments.extend(rendered_defines)
            else:
                arguments.append(argument.format_map(values))
        return tuple(arguments)
