"""Backend definition and execution tests."""

import pickle
import subprocess

import pytest
from ottu.backend import Backend, BackendCommandError
from ottu.backend_builtins import BACKEND_BUILTINS
from ottu.device import Device
from ottu.result import TestStatus
from ottu.test import Test
from ottu.test_path import TestPath


def make_test(name="check.py"):
    return Test(TestPath(name, name, None, name))


def failing_run(output, stage_to_fail=None):
    """Return a run_command that fails with the given captured output."""
    calls = []

    def run_command(command, **kwargs):
        calls.append(command)
        if stage_to_fail is None or len(calls) == stage_to_fail:
            raise subprocess.CalledProcessError(1, command, output=output)

    return run_command, calls


def run_failing(backend, run_command):
    backend.run(
        make_test("tests/hello-world.py").test_path,
        Device(name="uno"),
        run_command=run_command,
    )


class RecordingObserver:
    def __init__(self):
        self.events = []

    def result_changed(self, result):
        self.events.append(result)


def test_backend_runs_rendered_commands():
    """A resolved device supplies values to backend commands."""
    backend = Backend.from_mapping(
        {
            "build": ["arduino-cli", "compile", "--device", "{device}"],
            "program": ["arduino-cli", "upload", "--name", "{name}"],
        }
    )
    commands = []
    backend.run(
        make_test("tests/hello-world.py").test_path,
        Device(name="uno"),
        run_command=lambda command, **kwargs: commands.append((command, kwargs)),
    )
    assert commands == [
        (
            ("arduino-cli", "compile", "--device", "uno"),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        ),
        (
            ("arduino-cli", "upload", "--name", "uno"),
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
        make_test("tests/hello_world.ino").test_path,
        Device(name="uno"),
        run_command=lambda command, **kwargs: commands.append(command),
    )

    assert commands == [("arduino-cli", "compile", "tests/hello_world.ino")]


def test_backend_notifies_observers_for_each_stage():
    """Backend execution emits building and flashing progress events."""
    backend = Backend.from_mapping({"build": "echo build", "program": "echo flash"})
    observer = RecordingObserver()

    backend.run(
        make_test("hello-world.py").test_path,
        Device(),
        observers=(observer,),
        run_command=lambda command, **kwargs: None,
    )

    assert [(event.test_path.file_name, event.status) for event in observer.events] == [
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
        make_test("tests/test-device.py").test_path,
        Device(name="test-device"),
        run_command=lambda command, **kwargs: commands.append((command, kwargs)),
    )

    assert commands == [
        (
            ("sh", "-c", "sleep 3; echo build test-device "),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        ),
        (
            ("sh", "-c", "sleep 3; echo program test-device"),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        ),
    ]


def test_debug_backend_echoes_the_build_defines():
    """The debug build shows the defines it would hand to a real compiler."""
    backend = Backend.from_mapping(BACKEND_BUILTINS["debug"])

    commands = run_commands(backend, DEFINES, Device(name="test-device"))

    assert commands[0] == (
        "sh",
        "-c",
        "sleep 3; echo build test-device "
        "-DOTTU_FRAMED_OUTPUT_ENABLED=1 -DOTTU_TEST_FRAME_TOKEN=abc",
    )
    assert commands[1] == ("sh", "-c", "sleep 3; echo program test-device")


def test_debug_backend_build_is_valid_shell_with_defines():
    """The rendered debug build runs in a shell and prints its defines."""
    backend = Backend.from_mapping(BACKEND_BUILTINS["debug"])
    command = run_commands(backend, DEFINES, Device(name="test-device"))[0]

    result = subprocess.run(
        ("sh", "-c", command[2].replace("sleep 3; ", "")),
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == (
        "build test-device -DOTTU_FRAMED_OUTPUT_ENABLED=1 -DOTTU_TEST_FRAME_TOKEN=abc"
    )


def test_backend_can_omit_build():
    """A backend can provide only programming for prebuilt firmware."""
    backend = Backend.from_mapping(
        {"program": ["mpremote", "connect", "{name}", "run", "main.py"]}
    )
    commands = []

    backend.run(
        make_test("tests/hello-world.py").test_path,
        Device(name="uno"),
        run_command=lambda command, **kwargs: commands.append((command, kwargs)),
    )

    assert backend.build is None
    assert commands == [
        (
            ("mpremote", "connect", "uno", "run", "main.py"),
            {
                "cwd": None,
                "check": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
            },
        )
    ]


DEFINES = ["OTTU_FRAMED_OUTPUT_ENABLED=1", "OTTU_TEST_FRAME_TOKEN=abc"]


def run_commands(backend, defines=(), device=None):
    """Run a backend and return the rendered commands."""
    commands = []
    backend.run(
        make_test("tests/hello-world.py").test_path,
        device or Device(name="uno"),
        run_command=lambda command, **kwargs: commands.append(command),
        defines=defines,
    )
    return commands


def test_backend_splices_defines_when_alone_as_an_argument():
    """A lone {defines} argument becomes one argument per define."""
    backend = Backend.from_mapping({"build": ["gcc", "{defines}", "main.c"]})

    assert run_commands(backend, DEFINES) == [
        (
            "gcc",
            "-DOTTU_FRAMED_OUTPUT_ENABLED=1",
            "-DOTTU_TEST_FRAME_TOKEN=abc",
            "main.c",
        )
    ]


def test_backend_joins_defines_inside_an_argument():
    """{defines} inside a larger argument joins the defines with spaces."""
    backend = Backend.from_mapping({"build": ["tool", "--flags={defines}"]})

    assert run_commands(backend, DEFINES) == [
        (
            "tool",
            "--flags=-DOTTU_FRAMED_OUTPUT_ENABLED=1 -DOTTU_TEST_FRAME_TOKEN=abc",
        )
    ]


def test_backend_uses_its_define_prefix():
    backend = Backend.from_mapping(
        {"build": ["make", "{defines}"], "define_prefix": "DEFINES+="}
    )

    assert run_commands(backend, ["A=1"]) == [("make", "DEFINES+=A=1")]


def test_backend_can_use_an_empty_define_prefix():
    backend = Backend.from_mapping(
        {"build": ["make", "{defines}"], "define_prefix": ""}
    )

    assert run_commands(backend, ["A=1"]) == [("make", "A=1")]


def test_backend_ignores_defines_without_a_placeholder():
    """A build command without {defines} runs unchanged."""
    backend = Backend.from_mapping({"build": ["gcc", "main.c"]})

    assert run_commands(backend, DEFINES) == [("gcc", "main.c")]


def test_backend_renders_an_empty_placeholder_without_defines():
    spliced = Backend.from_mapping({"build": ["gcc", "{defines}", "main.c"]})
    joined = Backend.from_mapping({"build": ["tool", "--flags={defines}"]})

    assert run_commands(spliced) == [("gcc", "main.c")]
    assert run_commands(joined) == [("tool", "--flags=")]


def test_backend_gives_defines_to_the_build_step_only():
    backend = Backend.from_mapping(
        {"build": ["gcc", "{defines}"], "program": ["flash", "{defines}"]}
    )

    assert run_commands(backend, ["A=1"]) == [("gcc", "-DA=1"), ("flash",)]


def test_backend_defaults_to_the_d_define_prefix():
    assert Backend.from_mapping({"build": "gcc"}).define_prefix == "-D"


def test_backend_loads_the_define_prefix_from_yaml(tmp_path):
    definition = tmp_path / "backend.yml"
    definition.write_text(
        "build: make {defines}\ndefine_prefix: 'DEFINES+='\n", encoding="utf-8"
    )

    backend = Backend.from_yaml(definition)

    assert backend.define_prefix == "DEFINES+="
    assert run_commands(backend, ["A=1"]) == [("make", "DEFINES+=A=1")]


def test_backend_rejects_a_non_string_define_prefix():
    with pytest.raises(ValueError, match="define_prefix"):
        Backend.from_mapping({"build": "gcc", "define_prefix": 1})


def test_arduino_cli_backend_passes_defines_as_extra_flags():
    """The built-in arduino-cli build gets the defines as one build property."""
    backend = Backend.from_name("arduino-cli")
    device = Device.from_string("name=uno,address=/dev/ttyUSB0")

    commands = run_commands(backend, DEFINES, device)

    assert commands[0] == (
        "arduino-cli",
        "compile",
        "-b",
        "uno",
        "--build-property",
        "compiler.cpp.extra_flags="
        "-DOTTU_FRAMED_OUTPUT_ENABLED=1 -DOTTU_TEST_FRAME_TOKEN=abc",
        "tests/hello-world.py",
    )


def test_failed_build_error_includes_the_command_output():
    backend = Backend.from_mapping({"build": "gcc main.c"})
    run_command, _ = failing_run(b"main.c:3: error: expected ';'\nBuild failed\n")

    with pytest.raises(BackendCommandError) as raised:
        run_failing(backend, run_command)

    message = str(raised.value)
    assert "returned non-zero exit status 1" in message
    assert "Command output (last 2 lines):" in message
    assert message.endswith("main.c:3: error: expected ';'\nBuild failed")


def test_failed_command_error_is_still_a_called_process_error():
    backend = Backend.from_mapping({"build": "gcc main.c"})
    run_command, _ = failing_run(b"boom\n")

    with pytest.raises(subprocess.CalledProcessError) as raised:
        run_failing(backend, run_command)

    assert raised.value.returncode == 1
    assert raised.value.cmd == ("gcc", "main.c")
    assert raised.value.output == b"boom\n"
    assert isinstance(raised.value.__cause__, subprocess.CalledProcessError)


def test_failed_program_step_also_reports_its_output():
    backend = Backend.from_mapping({"build": "gcc main.c", "program": "flash now"})
    run_command, calls = failing_run(b"no device found\n", stage_to_fail=2)

    with pytest.raises(BackendCommandError, match="no device found"):
        run_failing(backend, run_command)

    assert calls == [("gcc", "main.c"), ("flash", "now")]


def test_failed_command_error_keeps_only_the_last_lines_of_long_output():
    output = "\n".join(f"line {number}" for number in range(1, 51)).encode()
    error = BackendCommandError(2, ("gcc",), output=output)

    lines = str(error).splitlines()

    assert "Command output (last 20 of 50 lines):" in lines
    assert lines[-1] == "line 50"
    assert lines[-20] == "line 31"
    assert "line 30" not in lines


def test_failed_command_error_without_output_is_the_plain_message():
    for output in (None, b"", b"  \n"):
        error = BackendCommandError(1, ("gcc",), output=output)

        assert str(error) == str(subprocess.CalledProcessError(1, ("gcc",)))


def test_failed_command_error_decodes_invalid_bytes():
    error = BackendCommandError(1, ("gcc",), output=b"bad \xff byte\n")

    assert str(error).endswith("bad \ufffd byte")


def test_failed_command_error_accepts_text_output():
    error = BackendCommandError(1, ("gcc",), output="already text\n")

    assert str(error).endswith("already text")


def test_failed_command_error_survives_pickling():
    """Suite workers are processes, so the error must cross a pickle boundary."""
    error = BackendCommandError(3, ("gcc", "main.c"), output=b"oops\n")

    restored = pickle.loads(pickle.dumps(error))

    assert isinstance(restored, BackendCommandError)
    assert restored.returncode == 3
    assert restored.cmd == ("gcc", "main.c")
    assert str(restored) == str(error)


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

    assert backend.build == ("sh", "-c", "sleep 3; echo build {device} {defines}")


def test_backend_loads_default_without_project_root():
    backend = Backend.load()

    assert backend.build == ("sh", "-c", "sleep 3; echo build {device} {defines}")


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
