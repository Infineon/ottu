"""Device output capture and parsing tests."""

import pytest
from ottu.output import (
    ExpectedOutputParser,
    FramedOutput,
    FramedOutputOpts,
    OutputParserType,
    TestOutcome,
    TestOutput,
    TestOutputOpts,
    TestOutputParser,
    UnityOutputParser,
)


class FakeSerial:
    def __init__(self, lines):
        self.lines = iter(lines)
        self.closed = False

    def readline(self):
        return next(self.lines, b"")

    def close(self):
        self.closed = True


def make_opts(**kwargs):
    return TestOutputOpts(idle_timeout=0, **kwargs)


class LowercaseOutputParser(TestOutputParser):
    def line_parser(self, line: bytes) -> str:
        return line.decode().strip().lower()

    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        outcome = TestOutcome.PASS if lines[-1] == "pass" else TestOutcome.UNVERIFIED
        return TestOutput(tuple(lines), outcome)


class TerminalOutcomeOutputParser(TestOutputParser):
    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        outcome = TestOutcome.UNVERIFIED
        for line in lines:
            normalized_line = line.strip().upper()
            if normalized_line == TestOutcome.PASS.value:
                outcome = TestOutcome.PASS
            elif normalized_line == TestOutcome.FAIL.value:
                outcome = TestOutcome.FAIL
        return TestOutput(tuple(lines), outcome)


def expected_parser(tmp_path, expected_text=None, expected_bytes=None, **opts):
    """Create an expected-output parser for a test with a sibling .exp file."""
    expected_output = tmp_path / "check.py.exp"
    if expected_bytes is not None:
        expected_output.write_bytes(expected_bytes)
    else:
        expected_output.write_text(expected_text, encoding="utf-8")
    return ExpectedOutputParser(make_opts(**opts), expected_output)


def test_test_output_reads_parses_and_prints_serial_output():
    connection = FakeSerial([b"ready\r\n", b"PASS\n"])

    output = LowercaseOutputParser(make_opts()).parse(connection)

    assert output.lines == ("ready", "pass")
    assert output.outcome is TestOutcome.PASS


def test_parser_joins_a_line_split_by_a_read_timeout():
    connection = FakeSerial([b"TEST(a, slow)", b" PASS\r\n", b"OK\n"])

    output = UnityOutputParser(make_opts()).parse(connection)

    assert output.lines == ("TEST(a, slow) PASS", "OK")


def test_parser_keeps_a_trailing_line_without_newline():
    connection = FakeSerial([b"first\n", b"partial"])

    output = UnityOutputParser(make_opts()).parse(connection)

    assert output.lines == ("first", "partial")


def test_test_output_returns_device_reported_failure():
    connection = FakeSerial([b"FAIL\n"])

    output = TerminalOutcomeOutputParser(make_opts()).parse(connection)

    assert output.lines == ("FAIL",)
    assert output.outcome is TestOutcome.FAIL


def test_expected_output_parser_passes_matching_output(tmp_path):
    parser = expected_parser(tmp_path, "ready\nPASS\n")

    output = parser.parse(FakeSerial([b"ready\n", b"PASS\n"]))

    assert output == TestOutput(("ready\n", "PASS\n"), TestOutcome.PASS)


def test_expected_output_parser_fails_different_output(tmp_path):
    parser = expected_parser(tmp_path, "ready\nPASS\n")

    output = parser.parse(FakeSerial([b"ready\n", b"FAIL\n"]))

    assert output == TestOutput(("ready\n", "FAIL\n"), TestOutcome.FAIL)


def test_expected_output_parser_preserves_line_ending_semantics(tmp_path):
    parser = expected_parser(tmp_path, expected_bytes=b"ready\r\n")

    output = parser.parse(FakeSerial([b"ready\n"]))

    assert output.outcome is TestOutcome.FAIL


def test_expected_output_parser_compares_only_framed_output(tmp_path):
    parser = expected_parser(
        tmp_path,
        "=== ottu begin 42 ===\nready\nPASS\n=== ottu end 42 ===\n",
        framed_output_opts=FramedOutputOpts(token="42"),
    )

    output = parser.parse(
        FakeSerial(
            [
                b"boot message\n",
                b"=== ottu begin 42 ===\n",
                b"ready\n",
                b"PASS\n",
                b"=== ottu end 42 ===\n",
                b"shutdown message\n",
            ]
        )
    )

    assert output == TestOutput(("ready\n", "PASS\n"), TestOutcome.PASS)


def test_expected_output_parser_accepts_end_marker_without_begin(tmp_path):
    parser = expected_parser(tmp_path, "ready\nPASS\n")

    output = parser.parse(FakeSerial([b"ready\n", b"PASS\n", b"=== ottu end ===\n"]))

    assert output == TestOutput(("ready\n", "PASS\n"), TestOutcome.PASS)


def test_expected_output_parser_compares_markers_when_framing_is_disabled(tmp_path):
    parser = expected_parser(
        tmp_path,
        "=== ottu begin ===\nready\n=== ottu end ===\n",
        framed_output_opts=None,
    )

    output = parser.parse(
        FakeSerial([b"=== ottu begin ===\n", b"ready\n", b"=== ottu end ===\n"])
    )

    assert output.outcome is TestOutcome.PASS
    assert output.lines == (
        "=== ottu begin ===\n",
        "ready\n",
        "=== ottu end ===\n",
    )


def test_expected_output_parser_rejects_different_frame_tokens(tmp_path):
    parser = expected_parser(
        tmp_path, "ready\n", framed_output_opts=FramedOutputOpts(token="41")
    )

    with pytest.raises(ValueError, match="does not match the compiled tests"):
        parser.parse(
            FakeSerial(
                [
                    b"=== ottu begin 41 ===\n",
                    b"ready\n",
                    b"=== ottu end 42 ===\n",
                ]
            )
        )


def test_output_parser_stops_reading_at_end_marker():
    connection = FakeSerial(
        [b"=== ottu begin ===\n", b"ready\n", b"=== ottu end ===\n", b"after\n"]
    )

    output = TestOutputParser(make_opts()).parse(connection)

    assert output.lines == ("ready",)
    assert list(connection.lines) == [b"after\n"]


def test_output_parser_keeps_every_line_when_framing_is_disabled():
    connection = FakeSerial(
        [b"=== ottu begin ===\n", b"ready\n", b"=== ottu end ===\n", b"after\n"]
    )

    output = TestOutputParser(make_opts(framed_output_opts=None)).parse(connection)

    assert output.lines == (
        "=== ottu begin ===",
        "ready",
        "=== ottu end ===",
        "after",
    )


def test_output_parser_fails_when_begin_marker_has_no_end():
    output = UnityOutputParser(make_opts()).parse(
        FakeSerial(
            [
                b"=== ottu begin ===\n",
                b"6 Tests 0 Failures 0 Ignored\n",
            ]
        )
    )

    assert output == TestOutput(("6 Tests 0 Failures 0 Ignored",), TestOutcome.FAIL)


def fed(lines, *opts):
    """Feed lines to a frame built with the given options, or the defaults."""
    frame = FramedOutput(*opts)
    for line in lines:
        frame.feed(line)
    return frame


def test_framed_output_without_markers_keeps_every_line():
    frame = fed(["boot", "ready"])

    assert frame.lines == ("boot", "ready")
    assert not frame.begun
    assert not frame.ended
    assert not frame.truncated


def test_framed_output_is_unframed_when_options_are_none():
    frame = fed(["boot", "=== ottu begin ===", "=== ottu end ===", "late"], None)

    assert frame.lines == ("boot", "=== ottu begin ===", "=== ottu end ===", "late")
    assert not frame.begun
    assert not frame.ended
    assert not frame.truncated


def test_framed_output_discards_output_before_begin_marker():
    frame = fed(
        ["boot", "=== ottu begin 7 ===", "ready", "=== ottu end 7 ===", "late"],
        FramedOutputOpts(token="7"),
    )

    assert frame.lines == ("ready",)
    assert frame.begun
    assert frame.ended
    assert not frame.truncated


def test_framed_output_ignores_lines_after_end_marker():
    frame = fed(["ready", "=== ottu end ===", "late"])

    assert frame.lines == ("ready",)
    assert frame.ended


def test_framed_output_is_truncated_without_end_marker():
    frame = fed(["=== ottu begin ===", "ready"])

    assert frame.lines == ("ready",)
    assert frame.truncated


def test_framed_output_rejects_different_tokens():
    with pytest.raises(ValueError, match="does not match the compiled tests"):
        fed(
            ["=== ottu begin 1 ===", "=== ottu end 2 ==="],
            FramedOutputOpts(token="1"),
        )


def test_framed_output_accepts_token_on_one_side_only():
    frame = fed(
        ["=== ottu begin 1 ===", "ready", "=== ottu end ==="],
        FramedOutputOpts(token="1"),
    )

    assert frame.lines == ("ready",)


def test_unity_output_parser_extracts_framed_output_and_summary():
    output = UnityOutputParser(
        make_opts(framed_output_opts=FramedOutputOpts(token="10"))
    ).parse(
        FakeSerial(
            [
                b"boot message\n",
                b"=== ottu begin 10 ===\n",
                b"Unity test run 1 of 1\n",
                b"TEST(interrupts, rising_edge) PASS\n",
                b"6 Tests 0 Failures 0 Ignored\n",
                b"OK\n",
                b"=== ottu end 10 ===\n",
                b"shutdown message\n",
            ]
        )
    )

    assert output.lines == (
        "Unity test run 1 of 1",
        "TEST(interrupts, rising_edge) PASS",
        "6 Tests 0 Failures 0 Ignored",
        "OK",
    )
    assert output.outcome is TestOutcome.PASS


def test_unity_output_parser_fails_on_unity_failures():
    output = UnityOutputParser(make_opts()).parse(
        FakeSerial([b"6 Tests 1 Failures 0 Ignored\n"])
    )

    assert output.outcome is TestOutcome.FAIL


def test_unity_output_parser_is_unverified_without_summary_when_auto_detected():
    output = UnityOutputParser(make_opts()).parse(FakeSerial([b"hello\n", b"world\n"]))

    assert output == TestOutput(("hello", "world"), TestOutcome.UNVERIFIED)


def test_unity_output_parser_is_unverified_without_any_output():
    output = UnityOutputParser(make_opts()).parse(FakeSerial([]))

    assert output == TestOutput((), TestOutcome.UNVERIFIED)


def test_unity_output_parser_fails_without_summary_when_explicitly_requested():
    output = UnityOutputParser(make_opts(parser=OutputParserType.UNITY)).parse(
        FakeSerial([b"hello\n"])
    )

    assert output == TestOutput(("hello",), TestOutcome.FAIL)


def test_unity_output_parser_rejects_different_frame_tokens():
    with pytest.raises(ValueError, match="does not match the compiled tests"):
        UnityOutputParser(
            make_opts(framed_output_opts=FramedOutputOpts(token="41"))
        ).parse(
            FakeSerial(
                [
                    b"=== ottu begin 41 ===\n",
                    b"6 Tests 0 Failures 0 Ignored\n",
                    b"=== ottu end 42 ===\n",
                ]
            )
        )


def test_expected_file_for_is_the_sibling_exp_file(tmp_path):
    (tmp_path / "check.py.exp").write_text("ready\n", encoding="utf-8")

    assert ExpectedOutputParser.expected_file_for(tmp_path / "check.py") == (
        tmp_path / "check.py.exp"
    )


def test_expected_file_for_is_none_without_an_exp_file(tmp_path):
    assert ExpectedOutputParser.expected_file_for(tmp_path / "check.py") is None


def test_create_gives_the_expected_parser_its_exp_file(tmp_path):
    (tmp_path / "check.py.exp").write_text("ready\n", encoding="utf-8")

    parser = TestOutputParser.create(tmp_path / "check.py", make_opts())

    assert parser.expected_output_path == tmp_path / "check.py.exp"


def test_create_selects_expected_output_parser_for_exp_file(tmp_path):
    (tmp_path / "check.py.exp").write_text("ready\n", encoding="utf-8")

    parser = TestOutputParser.create(tmp_path / "check.py", make_opts())
    output = parser.parse(FakeSerial([b"ready\n"]))

    assert type(parser) is ExpectedOutputParser
    assert output.outcome is TestOutcome.PASS


def test_create_selects_unity_parser_without_exp_file(tmp_path):
    parser = TestOutputParser.create(tmp_path / "check.py", make_opts())

    assert type(parser) is UnityOutputParser


def test_create_detects_unity_output_without_exp_file(tmp_path):
    parser = TestOutputParser.create(tmp_path / "check.py", make_opts())

    output = parser.parse(FakeSerial([b"6 Tests 0 Failures 0 Ignored\n", b"OK\n"]))

    assert output.outcome is TestOutcome.PASS


def test_create_leaves_other_output_unverified_without_exp_file(tmp_path):
    parser = TestOutputParser.create(tmp_path / "check.py", make_opts())

    output = parser.parse(FakeSerial([b"ready\n"]))

    assert output.outcome is TestOutcome.UNVERIFIED


def test_create_selects_unity_parser(tmp_path):
    parser = TestOutputParser.create(
        tmp_path / "check.py", make_opts(parser=OutputParserType.UNITY)
    )

    assert type(parser) is UnityOutputParser


def test_create_selects_unity_parser_even_with_exp_file(tmp_path):
    (tmp_path / "check.py.exp").write_text("ready\n", encoding="utf-8")

    parser = TestOutputParser.create(
        tmp_path / "check.py", make_opts(parser=OutputParserType.UNITY)
    )

    assert type(parser) is UnityOutputParser


def test_create_selects_expected_output_parser_explicitly(tmp_path):
    (tmp_path / "check.py.exp").write_text("ready\n", encoding="utf-8")

    parser = TestOutputParser.create(
        tmp_path / "check.py", make_opts(parser=OutputParserType.EXP_MATCH)
    )

    assert type(parser) is ExpectedOutputParser


def test_create_rejects_explicit_expected_match_without_exp_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="No expected-output file"):
        TestOutputParser.create(
            tmp_path / "check.py", make_opts(parser=OutputParserType.EXP_MATCH)
        )


def test_create_uses_default_options_without_options(tmp_path):
    parser = TestOutputParser.create(tmp_path / "check.py")

    assert type(parser) is UnityOutputParser
    assert parser.opts == TestOutputOpts()


def test_create_gives_each_default_parser_its_own_token(tmp_path):
    first = TestOutputParser.create(tmp_path / "check.py")
    second = TestOutputParser.create(tmp_path / "check.py")

    assert first.opts.framed_output_opts.token != second.opts.framed_output_opts.token


def test_test_output_has_no_outcome_by_default():
    assert TestOutput(("ready",)).outcome is None


def test_test_output_default_parser_decodes_invalid_bytes():
    connection = FakeSerial([b"ready\xff\n"])

    output = TestOutputParser(make_opts()).parse(connection)

    assert output.lines == ("ready\ufffd",)
    assert output.outcome is TestOutcome.UNVERIFIED


def test_test_output_waits_through_empty_reads():
    connection = FakeSerial([b"first\n", b"", b"second\n", b""])
    clock_values = iter((0.0, 0.0, 1.0, 1.0, 2.0, 6.0))

    output = TestOutputParser(
        TestOutputOpts(idle_timeout=5.0),
        clock=lambda: next(clock_values),
    ).parse(connection)

    assert output.lines == ("first", "second")


def test_test_output_propagates_reading_failure():
    connection = FakeSerial([])

    def fail_readline():
        raise RuntimeError("serial read failed")

    connection.readline = fail_readline

    with pytest.raises(RuntimeError, match="serial read failed"):
        TestOutputParser(make_opts()).parse(connection)
