"""Test result tests."""

from ottu.output import TestOutcome, TestOutput
from ottu.result import TestResult, TestStatus
from ottu.test_path import TestPath


def make_result(status, outcome=None):
    return TestResult(
        TestPath("check.py", "check.py", None, "check.py"),
        status,
        output=TestOutput((), outcome) if outcome is not None else None,
    )


def test_result_passes_only_with_passing_outcome():
    assert make_result(TestStatus.DONE, TestOutcome.PASS).passed
    assert not make_result(TestStatus.DONE, TestOutcome.FAIL).passed
    assert not make_result(TestStatus.DONE, TestOutcome.UNVERIFIED).passed


def test_result_without_outcome_has_not_passed():
    assert not make_result(TestStatus.EXECUTING).passed


def test_result_outcome_comes_from_its_output():
    assert make_result(TestStatus.DONE, TestOutcome.FAIL).outcome is TestOutcome.FAIL
    assert make_result(TestStatus.DONE, TestOutcome.UNVERIFIED).outcome is (
        TestOutcome.UNVERIFIED
    )


def test_result_has_no_outcome_before_it_has_output():
    assert make_result(TestStatus.EXECUTING).outcome is None


def test_result_has_no_outcome_while_its_output_is_not_judged():
    result = TestResult(
        TestPath("check.py", "check.py", None, "check.py"),
        TestStatus.EXECUTING,
        output=TestOutput(("partial",)),
    )

    assert result.outcome is None
    assert not result.passed
