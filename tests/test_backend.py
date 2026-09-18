"""Backend definition and execution tests."""

import subprocess

import pytest
from ottu.backend import Backend
from ottu.backend_builtins import BACKEND_BUILTINS
from ottu.result import TestStatus


class RecordingObserver:
    def __init__(self):
        self.events = []

    def result_changed(self, result):
        self.events.append(result)


def test_backend_runs_rendered_commands():
    """A resolved device supplies values to backend commands."""
    backend = Backend.from_mapping(
        {
            "build": ["arduino-cli", "compile", "--board", "{board}"],
            "program": ["arduino-cli", "upload", "--port", "{port}"],
        }
    )
    commands = []
    backend.run(
        "tests/hello-world.py",
        {"board": "uno", "port": "/dev/ttyUSB0"},
        run_command=lambda command, **kwargs: commands.append((command, kwargs)),
    )
    assert commands == [
        (
            ("arduino-cli", "compile", "--board", "uno"),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        ),
        (
            ("arduino-cli", "upload", "--port", "/dev/ttyUSB0"),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        ),
    ]


def test_backend_renders_test_path():
    """A backend command can receive the resolved test path."""
    backend = Backend.from_mapping({"build": ["arduino-cli", "compile", "{test_path}"]})
    commands = []
    backend.run(
        "tests/hello_world.ino",
        {"name": "uno"},
        run_command=lambda command, **kwargs: commands.append(command),
    )

    assert commands == [("arduino-cli", "compile", "tests/hello_world.ino")]


def test_backend_notifies_observers_for_each_stage():
    """Backend execution emits building and flashing progress events."""
    backend = Backend.from_mapping({"build": "echo build", "program": "echo flash"})
    observer = RecordingObserver()

    backend.run(
        "tests/hello-world.py",
        {},
        observers=(observer,),
        run_command=lambda command, **kwargs: None,
    )

    assert [(event.test_name, event.status) for event in observer.events] == [
        ("hello-world.py", TestStatus.BUILDING),
        ("hello-world.py", TestStatus.FLASHING),
    ]


def test_backend_loads_parametric_yaml(tmp_path):
    """YAML commands preserve placeholders until a device is supplied."""
    definition = tmp_path / "backend.yml"
    definition.write_text(
        """
build: arduino-cli compile --board {board}
program: [arduino-cli, upload, --port, '{port}']
""",
        encoding="utf-8",
    )

    backend = Backend.from_yaml(definition)

    assert backend.build == (
        "arduino-cli",
        "compile",
        "--board",
        "{board}",
    )


def test_debug_backend_echoes_device_commands():
    """The built-in debug backend renders and runs both backend steps."""
    backend = Backend.from_mapping(BACKEND_BUILTINS["debug"])
    commands = []

    backend.run(
        "tests/test-device.py",
        {"device": "test-device"},
        run_command=lambda command, **kwargs: commands.append((command, kwargs)),
    )

    assert commands == [
        (
            ("echo", "build", "test-device"),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        ),
        (
            ("echo", "program", "test-device"),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        ),
    ]


def test_backend_can_omit_build():
    """A backend can provide only programming for prebuilt firmware."""
    backend = Backend.from_mapping(
        {"program": ["mpremote", "connect", "{port}", "run", "main.py"]}
    )
    commands = []

    backend.run(
        "tests/hello-world.py",
        {"port": "/dev/ttyUSB0"},
        run_command=lambda command, **kwargs: commands.append((command, kwargs)),
    )

    assert backend.build is None
    assert commands == [
        (
            ("mpremote", "connect", "/dev/ttyUSB0", "run", "main.py"),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        )
    ]


def test_backend_rejects_empty_definition():
    """A backend must provide at least one executable command."""
    with pytest.raises(ValueError, match="at least one command"):
        Backend.from_mapping({})


@pytest.mark.parametrize("command", ["", [1]])
def test_backend_rejects_invalid_command(command):
    """Backend commands must contain string arguments."""
    with pytest.raises(ValueError, match="must contain a command"):
        Backend.from_mapping({"build": command})


def test_backend_loads_builtin():
    """A built-in backend can be selected by name."""
    backend = Backend.from_name("debug")

    assert backend.build == ("echo", "build", "{device}")


def test_backend_loads_default_without_project_root():
    backend = Backend.load()

    assert backend.build == ("echo", "build", "{device}")


def test_backend_loads_project_yaml(tmp_path):
    """A backend reference can point to a project-local YAML file."""
    (tmp_path / ".ottu").write_text(
        "version: 1\nbackend: custom.yml\n",
        encoding="utf-8",
    )
    definition = tmp_path / "custom.yml"
    definition.write_text("program: echo program {device}\n", encoding="utf-8")

    backend = Backend.load(project_root=tmp_path)

    assert backend.program == ("echo", "program", "{device}")


def test_backend_rejects_unknown_source():
    """Unknown backend references fail with a useful error."""
    with pytest.raises(ValueError, match="Unknown backend 'missing'"):
        Backend.from_name("missing")
