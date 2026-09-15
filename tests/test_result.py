"""Serial test output tests."""

import pytest
from ottu.device import SerialDeviceAccess
from ottu.result import ExpectedOutputParser, TestOutput, TestOutputParser, TestStatus


class FakeSerial:
    def __init__(self, lines):
        self.lines = iter(lines)
        self.closed = False

    def readline(self):
        return next(self.lines, b"")

    def close(self):
        self.closed = True


class LowercaseOutputParser(TestOutputParser):
    def line_parser(self, line: bytes) -> str:
        return line.decode().strip().lower()

    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        status = TestStatus.PASSED if lines[-1] == "pass" else None
        return TestOutput(tuple(lines), status)


class TerminalStatusOutputParser(TestOutputParser):
    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        status = None
        for line in lines:
            normalized_line = line.strip().upper()
            if normalized_line == TestStatus.PASSED.value:
                status = TestStatus.PASSED
            elif normalized_line == TestStatus.FAILED.value:
                status = TestStatus.FAILED
        return TestOutput(tuple(lines), status)


def test_serial_device_access_connects_to_serial_port():
    connection = FakeSerial([])
    calls = []

    def serial_factory(**kwargs):
        calls.append(kwargs)
        return connection

    result = SerialDeviceAccess(serial_factory=serial_factory).connect(
        {"port": "/dev/ttyUSB0"}
    )

    assert result is connection
    assert calls == [{"port": "/dev/ttyUSB0", "baudrate": 115200, "timeout": 1.0}]


def test_test_output_reads_parses_and_prints_serial_output():
    connection = FakeSerial([b"ready\r\n", b"PASS\n"])

    output = LowercaseOutputParser(idle_timeout=0).parse(connection)

    assert output.lines == ("ready", "pass")
    assert output.status is TestStatus.PASSED


def test_test_output_returns_device_reported_failure():
    connection = FakeSerial([b"FAIL\n"])

    output = TerminalStatusOutputParser(idle_timeout=0).parse(connection)

    assert output.lines == ("FAIL",)
    assert output.status is TestStatus.FAILED


def test_expected_output_parser_passes_matching_output(tmp_path):
    expected_output = tmp_path / "check.py.exp"
    expected_output.write_text("ready\nPASS\n", encoding="utf-8")
    connection = FakeSerial([b"ready\n", b"PASS\n"])

    output = ExpectedOutputParser(expected_output, idle_timeout=0).parse(connection)

    assert output == TestOutput(("ready\n", "PASS\n"), TestStatus.PASSED)


def test_expected_output_parser_fails_different_output(tmp_path):
    expected_output = tmp_path / "check.py.exp"
    expected_output.write_text("ready\nPASS\n", encoding="utf-8")
    connection = FakeSerial([b"ready\n", b"FAIL\n"])

    output = ExpectedOutputParser(expected_output, idle_timeout=0).parse(connection)

    assert output == TestOutput(("ready\n", "FAIL\n"), TestStatus.FAILED)


def test_expected_output_parser_preserves_line_ending_semantics(tmp_path):
    expected_output = tmp_path / "check.py.exp"
    expected_output.write_bytes(b"ready\r\n")

    output = ExpectedOutputParser(expected_output, idle_timeout=0).parse(
        FakeSerial([b"ready\n"])
    )

    assert output.status is TestStatus.FAILED


def test_expected_output_parser_uses_test_path_exp_file(tmp_path):
    test_path = tmp_path / "check.py"
    expected_output = tmp_path / "check.py.exp"
    expected_output.write_text("ready\n", encoding="utf-8")

    parser = TestOutputParser.from_test_path(test_path, idle_timeout=0)
    output = parser.parse(FakeSerial([b"ready\n"]))

    assert output.status is TestStatus.PASSED


def test_test_output_parser_factory_uses_default_without_exp_file(tmp_path):
    parser = TestOutputParser.from_test_path(tmp_path / "check.py", idle_timeout=0)

    assert type(parser) is TestOutputParser


def test_test_output_default_parser_decodes_invalid_bytes():
    connection = FakeSerial([b"ready\xff\n"])

    output = TestOutputParser(idle_timeout=0).parse(connection)

    assert output.lines == ("ready\ufffd",)
    assert output.status is None


def test_test_output_waits_through_empty_reads():
    connection = FakeSerial([b"first\n", b"", b"second\n", b""])
    clock_values = iter((0.0, 0.0, 1.0, 1.0, 2.0, 6.0))

    output = TestOutputParser(
        idle_timeout=5.0,
        clock=lambda: next(clock_values),
    ).parse(connection)

    assert output.lines == ("first", "second")


def test_test_output_requires_a_serial_port():
    with pytest.raises(ValueError, match="serial port is required"):
        SerialDeviceAccess().connect({"name": "board"})


def test_test_output_propagates_reading_failure():
    connection = FakeSerial([])

    def fail_readline():
        raise RuntimeError("serial read failed")

    connection.readline = fail_readline

    with pytest.raises(RuntimeError, match="serial read failed"):
        TestOutputParser(idle_timeout=0).parse(connection)
