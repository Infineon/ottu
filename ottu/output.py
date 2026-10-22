"""Capture and interpret the output a test produces on a device."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from re import Pattern, search, sub
from re import compile as compile_regex
from time import monotonic
from typing import ClassVar

from ottu.device import DeviceConnection


@dataclass(frozen=True)
class FramedOutputOpts:
    """Options for handling framed output.

    ``token`` is the unique value compiled into the target build and expected in
    the markers, which read ``=== ottu begin <token> ===`` and
    ``=== ottu end <token> ===`` (without a token, ``=== ottu begin ===``). Each
    instance generates its own; pass ``None`` to run without one. It only exists
    with the default markers, so custom markers drop it, and it must be a bare
    word (letters, digits, ``_``, ``.`` and ``-``) because it is passed to the
    compiler unquoted.
    """

    TOKEN_GROUP: ClassVar[str] = r"(?:\s+(\S+))?"
    TOKEN_FORMAT: ClassVar[Pattern[str]] = compile_regex(r"[\w.-]+")
    DEFAULT_BEGIN_MARKER: ClassVar[Pattern[str]] = compile_regex(
        rf"\s*=== ottu begin{TOKEN_GROUP}\s+===\s*"
    )
    DEFAULT_END_MARKER: ClassVar[Pattern[str]] = compile_regex(
        rf"\s*=== ottu end{TOKEN_GROUP}\s+===\s*"
    )

    begin_marker: Pattern[str] = DEFAULT_BEGIN_MARKER
    end_marker: Pattern[str] = DEFAULT_END_MARKER
    token: str | None = field(default_factory=lambda: str(uuid.uuid4()), compare=False)

    def __post_init__(self) -> None:
        if self.token is None:
            return
        if not self.default_markers:
            object.__setattr__(self, "token", None)
        elif not self.TOKEN_FORMAT.fullmatch(self.token):
            raise ValueError(f"Frame token must be a bare word: {self.token!r}")

    @property
    def default_markers(self) -> bool:
        """Whether both markers are the defaults, the only case tokens apply."""
        return (
            self.begin_marker.pattern == self.DEFAULT_BEGIN_MARKER.pattern
            and self.end_marker.pattern == self.DEFAULT_END_MARKER.pattern
        )

    @classmethod
    def target_build_args(cls, opts: FramedOutputOpts | None) -> list[str]:
        """Return the build defines for the given framing options.

        Framing is explicitly enabled or disabled, and the token and markers
        are only added when they differ from the defaults. The token is a bare
        word, as the target library expects; markers are C string literals.
        """
        if opts is None:
            return ["OTTU_FRAMED_OUTPUT_ENABLED=0"]
        args = ["OTTU_FRAMED_OUTPUT_ENABLED=1"]
        if opts.token is not None:
            args.append(f"OTTU_TEST_FRAME_TOKEN={opts.token}")
        for name, marker, default in (
            ("OTTU_TEST_FRAME_START", opts.begin_marker, cls.DEFAULT_BEGIN_MARKER),
            ("OTTU_TEST_FRAME_END", opts.end_marker, cls.DEFAULT_END_MARKER),
        ):
            if marker.pattern != default.pattern:
                args.append(f"{name}={cls._c_string(cls._marker_text(marker))}")
        return args

    @staticmethod
    def _c_string(value: str) -> str:
        """Wrap a value as an escaped C string literal."""
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @staticmethod
    def _marker_text(marker: Pattern[str]) -> str:
        """Return the literal text a marker pattern matches, without token or padding.

        Only plain-text patterns can become a define; anything else raises.
        """
        text = marker.pattern.removeprefix(r"\s*").removesuffix(r"\s*")
        text = text.removesuffix(FramedOutputOpts.TOKEN_GROUP)
        if search(r"(?<!\\)[.^$*+?{}\[\]|()]", text):
            raise ValueError(f"Marker pattern is not plain text: {marker.pattern}")
        return sub(r"\\(.)", r"\1", text)


@dataclass
class FramedOutput:
    """Track the optional ottu begin/end markers in streamed device output.

    A begin marker starts the valid output, discarding anything captured
    before it. An end marker finishes the test. Without markers, every line is
    kept and the caller decides when the output is complete.

    The options default to new ones, with their own token, and can be shared
    with the target build. With ``None`` the output is unframed: no markers are
    looked for and every line is kept.
    """

    opts: FramedOutputOpts | None = field(default_factory=FramedOutputOpts)
    captured_lines: list[str] = field(default_factory=list, init=False)
    begin_token: str | None = field(default=None, init=False)
    begun: bool = field(default=False, init=False)
    ended: bool = field(default=False, init=False)

    @property
    def lines(self) -> tuple[str, ...]:
        """Output enclosed by the markers, or all output when unframed."""
        return tuple(self.captured_lines)

    @property
    def truncated(self) -> bool:
        """Whether a begin marker was seen but the end marker never arrived."""
        return self.begun and not self.ended

    def feed(self, line: str) -> None:
        """Classify one line as a marker or as output."""
        if self.ended:
            return
        opts = self.opts
        if opts is None:
            self.captured_lines.append(line)
            return
        if not self.begun and (match := opts.begin_marker.fullmatch(line)) is not None:
            self.begun = True
            if opts.token is not None:
                self.begin_token = match.group(1)
                self._verify_token(self.begin_token, opts.token)
            self.captured_lines.clear()
        elif (match := opts.end_marker.fullmatch(line)) is not None:
            self.ended = True
            if opts.token is not None:
                self._verify_token(match.group(1), opts.token)
        else:
            self.captured_lines.append(line)

    @staticmethod
    def _verify_token(found: str | None, expected: str) -> None:
        """Reject a marker whose token differs from the expected one.

        A marker without a token is not checked. Since every token present must
        equal the expected one, the begin and end tokens agree as well.
        """
        if found is not None and found != expected:
            raise ValueError(
                "Test executable does not match the compiled tests: "
                f"ottu frame token {found} does not match {expected}."
            )


class OutputParserType(str, Enum):
    AUTO = "auto"
    UNITY = "unity"
    EXP_MATCH = "exp-match"


@dataclass(frozen=True)
class TestOutputOpts:
    """Options for capturing and interpreting the output of a test."""

    parser: OutputParserType = OutputParserType.AUTO
    framed_output_opts: FramedOutputOpts | None = field(
        default_factory=FramedOutputOpts
    )
    idle_timeout: float = 20.0

    def target_build_args(self) -> list[str]:
        """Return the build defines for this output's framing options."""
        return FramedOutputOpts.target_build_args(self.framed_output_opts)


class TestOutcome(str, Enum):
    """
    Verdict of a finished test.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class TestOutput:
    """
    Captured output and the outcome interpreted from it.

    The outcome is ``None`` while no verdict exists yet, and ``UNVERIFIED`` when
    the output was read but could not be judged.
    """

    lines: tuple[str, ...]
    outcome: TestOutcome | None = None


Clock = Callable[[], float]


@dataclass(frozen=True)
class TestOutputParser:
    """Read and interpret output from an open device connection."""

    opts: TestOutputOpts
    clock: Clock = field(default=monotonic, kw_only=True)

    @classmethod
    def create(
        cls,
        test_path: Path,
        opts: TestOutputOpts | None = None,
        *,
        clock: Clock = monotonic,
    ) -> TestOutputParser:
        """Select the parser for a test.

        Without options, new default ones are used. With the auto parser, a
        sibling .exp file selects expected-output matching; otherwise the output
        is checked as Unity output, and is unverified when it is not.
        """
        opts = opts if opts is not None else TestOutputOpts()
        expected_file = ExpectedOutputParser.expected_file_for(test_path)
        if opts.parser is OutputParserType.EXP_MATCH and expected_file is None:
            raise FileNotFoundError(f"No expected-output file for {test_path}.")
        if expected_file is not None and opts.parser is not OutputParserType.UNITY:
            return ExpectedOutputParser(opts, expected_file, clock=clock)
        return UnityOutputParser(opts, clock=clock)

    def parse(self, connection: DeviceConnection) -> TestOutput:
        """Read output until the frame ends or idle, and return the outcome.

        A delimited frame that never ends is a truncated run and fails.
        """
        idle_timeout = self.opts.idle_timeout
        idle_deadline = self.clock() + idle_timeout
        frame = FramedOutput(self.opts.framed_output_opts)
        pending = b""
        while not frame.ended:
            chunk = connection.readline()
            if not chunk:
                if self.clock() >= idle_deadline:
                    break
                continue
            idle_deadline = self.clock() + idle_timeout
            # A read timeout can return half a line; keep it until the newline arrives.
            pending += chunk
            if pending.endswith(b"\n"):
                frame.feed(self.line_parser(pending))
                pending = b""
        if pending and not frame.ended:
            frame.feed(self.line_parser(pending))
        if frame.truncated:
            return TestOutput(frame.lines, TestOutcome.FAIL)
        return self.all_lines_parser(list(frame.lines))

    def line_parser(self, line: bytes) -> str:
        """Parse a single output line."""
        return line.decode(errors="replace").rstrip("\r\n")

    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        """Parse captured lines into a test output that cannot be judged."""
        return TestOutput(tuple(lines), TestOutcome.UNVERIFIED)


@dataclass(frozen=True)
class ExpectedOutputParser(TestOutputParser):
    """Compare captured output with an expected-output file."""

    expected_output_path: Path

    @staticmethod
    def expected_file_for(test_path: Path) -> Path | None:
        """Return the .exp file that sits next to a test, or None if absent."""
        expected_file = test_path.with_name(f"{test_path.name}.exp")
        return expected_file if expected_file.is_file() else None

    def line_parser(self, line: bytes) -> str:
        """Decode output without removing its line ending."""
        return line.decode(errors="replace")

    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        """Pass only when captured lines match the expected-output lines."""
        expected_frame = FramedOutput(self.opts.framed_output_opts)
        with self.expected_output_path.open(newline="") as expected_output:
            for line in expected_output.read().splitlines(keepends=True):
                expected_frame.feed(line)
        output_lines = tuple(lines)
        outcome = (
            TestOutcome.PASS
            if output_lines == expected_frame.lines
            else TestOutcome.FAIL
        )
        return TestOutput(output_lines, outcome)


class UnityOutputParser(TestOutputParser):
    """Interpret Unity test-run summaries from device output."""

    _SUMMARY = compile_regex(
        r"\s*(\d+)\s+Tests?\s+(\d+)\s+Failures?\s+(\d+)\s+Ignored\s*"
    )

    def all_lines_parser(self, lines: list[str]) -> TestOutput:
        """Derive the outcome from the Unity summary line.

        Without a summary, output that was explicitly requested as Unity fails,
        while auto-detected output is unverified.
        """
        summaries = [
            match
            for line in lines
            if (match := self._SUMMARY.fullmatch(line)) is not None
        ]
        if not summaries:
            missing_summary = (
                TestOutcome.FAIL
                if self.opts.parser is OutputParserType.UNITY
                else TestOutcome.UNVERIFIED
            )
            return TestOutput(tuple(lines), missing_summary)
        outcome = (
            TestOutcome.FAIL if int(summaries[-1].group(2)) > 0 else TestOutcome.PASS
        )
        return TestOutput(tuple(lines), outcome)
