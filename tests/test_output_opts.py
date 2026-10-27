"""Output options tests."""

from re import compile as compile_regex

import pytest
from ottu.output import (
    FramedOutput,
    FramedOutputOpts,
    TestOutputOpts,
)


def test_framed_output_opts_generate_a_token_by_default():
    opts = FramedOutputOpts()

    assert opts.token is not None
    assert opts.default_markers


def test_framed_output_opts_generate_a_different_token_each_time():
    assert FramedOutputOpts().token != FramedOutputOpts().token


def test_framed_output_opts_run_without_a_token_when_passed_none():
    opts = FramedOutputOpts(token=None)

    assert opts.token is None
    assert opts.default_markers


@pytest.mark.parametrize(
    "markers",
    [
        {"begin_marker": compile_regex(r"\s*<<< begin >>>\s*")},
        {"end_marker": compile_regex(r"\s*<<< end >>>\s*")},
    ],
)
def test_framed_output_opts_drop_token_with_custom_markers(markers):
    opts = FramedOutputOpts(token="abc", **markers)

    assert not opts.default_markers
    assert opts.token is None


def test_framed_output_opts_keep_token_with_default_markers():
    assert FramedOutputOpts(token="abc").token == "abc"


def test_default_markers_are_detected():
    assert FramedOutputOpts().default_markers


def test_token_does_not_affect_framed_output_opts_equality():
    assert FramedOutputOpts(token="a") == FramedOutputOpts(token="b")


def test_test_output_opts_with_default_values_are_equal():
    assert TestOutputOpts() == TestOutputOpts()


def test_test_output_opts_default_idle_timeout():
    assert TestOutputOpts().idle_timeout == 60.0


def test_framed_output_uses_given_options():
    opts = FramedOutputOpts()

    assert FramedOutput(opts).opts is opts


def test_framed_output_defaults_to_new_options_with_their_own_token():
    first = FramedOutput().opts
    second = FramedOutput().opts

    assert first is not second
    assert first.token is not None
    assert second.token is not None
    assert first.token != second.token


def test_framed_output_has_no_options_when_unframed():
    assert FramedOutput(None).opts is None


def feed_all(frame, lines):
    for line in lines:
        frame.feed(line)
    return frame


def token_frame(token="abc"):
    return FramedOutput(FramedOutputOpts(token=token))


def test_framed_output_reads_token_from_begin_marker():
    frame = feed_all(token_frame("abc-123"), ["=== ottu begin abc-123 ===", "ready"])

    assert frame.begin_token == "abc-123"
    assert frame.lines == ("ready",)


def test_framed_output_accepts_matching_end_token():
    frame = feed_all(
        token_frame(),
        ["=== ottu begin abc ===", "ready", "=== ottu end abc ==="],
    )

    assert frame.ended
    assert frame.lines == ("ready",)


def test_framed_output_rejects_end_token_different_from_begin_token():
    frame = token_frame("abc")

    with pytest.raises(ValueError, match="does not match the compiled tests"):
        feed_all(frame, ["=== ottu begin abc ===", "=== ottu end xyz ==="])


def test_framed_output_rejects_begin_token_different_from_options_token():
    frame = token_frame("abc")

    with pytest.raises(ValueError, match="does not match the compiled tests"):
        frame.feed("=== ottu begin other ===")


def test_framed_output_rejects_matching_markers_with_wrong_options_token():
    frame = token_frame("abc")

    with pytest.raises(ValueError, match="does not match the compiled tests"):
        feed_all(frame, ["=== ottu begin xyz ===", "=== ottu end xyz ==="])


def test_framed_output_rejects_end_token_without_begin_token():
    frame = token_frame("abc")

    with pytest.raises(ValueError, match="does not match the compiled tests"):
        feed_all(frame, ["=== ottu begin ===", "ready", "=== ottu end xyz ==="])


def test_framed_output_accepts_token_on_only_one_marker():
    frame = feed_all(
        token_frame(), ["=== ottu begin abc ===", "ready", "=== ottu end ==="]
    )

    assert frame.ended


def test_framed_output_accepts_markers_without_tokens():
    frame = feed_all(token_frame(), ["=== ottu begin ===", "ok", "=== ottu end ==="])

    assert frame.begin_token is None
    assert frame.ended


def test_framed_output_skips_token_checks_without_a_token():
    frame = feed_all(
        FramedOutput(FramedOutputOpts(token=None)),
        ["=== ottu begin abc ===", "=== ottu end xyz ==="],
    )

    assert frame.begin_token is None
    assert frame.ended


def test_framed_output_does_not_recognize_a_token_after_the_closing_equals():
    """The target library puts the token before the closing ===."""
    frame = feed_all(token_frame(), ["=== ottu begin === abc", "ready"])

    assert not frame.begun
    assert frame.lines == ("=== ottu begin === abc", "ready")


@pytest.mark.parametrize(
    "line",
    [
        "=== ottu begin ===",
        "=== ottu begin abc ===",
        "  === ottu begin  abc  ===  ",
        "=== ottu begin 77f0a375-0f49-4949-98ec-2194c1335022 ===",
    ],
)
def test_default_begin_marker_accepts_the_library_format(line):
    assert FramedOutputOpts.DEFAULT_BEGIN_MARKER.fullmatch(line) is not None


@pytest.mark.parametrize(
    "line",
    ["=== ottu begin", "=== ottu begin abc", "=== ottu end ===", "ottu begin ==="],
)
def test_default_begin_marker_rejects_other_lines(line):
    assert FramedOutputOpts.DEFAULT_BEGIN_MARKER.fullmatch(line) is None


def test_default_end_marker_reads_the_token():
    match = FramedOutputOpts.DEFAULT_END_MARKER.fullmatch("=== ottu end abc ===")

    assert match is not None
    assert match.group(1) == "abc"


def test_markers_built_from_the_build_define_are_recognized():
    """The token that goes into the build is the one the frame accepts."""
    opts = FramedOutputOpts()
    define = FramedOutputOpts.target_build_args(opts)[1]
    token = define.removeprefix("OTTU_TEST_FRAME_TOKEN=")

    frame = feed_all(
        FramedOutput(opts),
        [
            "boot noise",
            f"=== ottu begin {token} ===",
            "6 Tests 0 Failures 0 Ignored",
            f"=== ottu end {token} ===",
        ],
    )

    assert frame.begun
    assert frame.ended
    assert frame.begin_token == token
    assert frame.lines == ("6 Tests 0 Failures 0 Ignored",)


def test_framed_output_skips_token_checks_with_custom_markers():
    opts = FramedOutputOpts(
        begin_marker=compile_regex(r"\s*<<< begin (\S+)\s*"),
        end_marker=compile_regex(r"\s*<<< end (\S+)\s*"),
    )

    frame = feed_all(FramedOutput(opts), ["<<< begin a", "<<< end b"])

    assert frame.begin_token is None
    assert frame.ended


ENABLED = "OTTU_FRAMED_OUTPUT_ENABLED=1"
DISABLED = "OTTU_FRAMED_OUTPUT_ENABLED=0"


def test_target_build_args_disables_framing_without_framed_output_opts():
    assert FramedOutputOpts.target_build_args(None) == [DISABLED]
    assert TestOutputOpts(framed_output_opts=None).target_build_args() == [DISABLED]


def test_output_opts_include_their_token_in_the_build_args():
    opts = TestOutputOpts()
    token = opts.framed_output_opts.token

    assert opts.target_build_args() == [ENABLED, f"OTTU_TEST_FRAME_TOKEN={token}"]


def test_each_output_opts_has_its_own_token():
    assert (
        TestOutputOpts().framed_output_opts.token
        != TestOutputOpts().framed_output_opts.token
    )


def test_target_build_args_only_enables_without_a_token():
    assert FramedOutputOpts.target_build_args(FramedOutputOpts(token=None)) == [ENABLED]


def test_target_build_args_includes_token():
    assert FramedOutputOpts.target_build_args(FramedOutputOpts(token="abc-123")) == [
        ENABLED,
        "OTTU_TEST_FRAME_TOKEN=abc-123",
    ]


@pytest.mark.parametrize("token", ["42", "abc-123", "a_b.c", "77f0a375-0f49-4949"])
def test_framed_output_opts_accept_bare_word_tokens(token):
    assert FramedOutputOpts(token=token).token == token


@pytest.mark.parametrize("token", ["has space", 'a"b', "a;b", "$(x)", "", "a=b"])
def test_framed_output_opts_reject_tokens_that_are_not_bare_words(token):
    with pytest.raises(ValueError, match="bare word"):
        FramedOutputOpts(token=token)


def test_custom_markers_drop_a_token_without_validating_it():
    opts = FramedOutputOpts(
        begin_marker=compile_regex(r"\s*<<< begin >>>\s*"), token="has space"
    )

    assert opts.token is None


def test_target_build_args_includes_only_non_default_markers():
    opts = FramedOutputOpts(
        begin_marker=compile_regex(r"\s*<<< begin >>>(?:\s+(\S+))?\s*"),
    )

    assert FramedOutputOpts.target_build_args(opts) == [
        ENABLED,
        'OTTU_TEST_FRAME_START="<<< begin >>>"',
    ]


def test_target_build_args_omits_token_with_custom_markers():
    opts = FramedOutputOpts(
        begin_marker=compile_regex(r"\s*<<< begin >>>\s*"),
        end_marker=compile_regex(r"\s*<<< end >>>(?:\s+(\S+))?\s*"),
        token="t",
    )

    assert FramedOutputOpts.target_build_args(opts) == [
        ENABLED,
        'OTTU_TEST_FRAME_START="<<< begin >>>"',
        'OTTU_TEST_FRAME_END="<<< end >>>"',
    ]


def test_target_build_args_escapes_c_string_values():
    opts = FramedOutputOpts(end_marker=compile_regex(r"\s*say \"hi\"\s*"))

    assert FramedOutputOpts.target_build_args(opts) == [
        ENABLED,
        r'OTTU_TEST_FRAME_END="say \"hi\""',
    ]


def test_target_build_args_rejects_marker_that_is_not_plain_text():
    opts = FramedOutputOpts(begin_marker=compile_regex(r"=== \w+ ==="))

    with pytest.raises(ValueError, match="not plain text"):
        FramedOutputOpts.target_build_args(opts)
