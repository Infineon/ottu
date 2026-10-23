"""Test report tests."""

from ottu.output import TestOutcome, TestOutput
from ottu.report import TestReport, TestStatus
from ottu.test_path import TestPath


def make_report(status, outcome=None):
    return TestReport(
        TestPath("check.py", "check.py", None, "check.py"),
        status,
        output=TestOutput((), outcome) if outcome is not None else None,
    )


def test_report_passes_only_with_passing_outcome():
    assert make_report(TestStatus.DONE, TestOutcome.PASS).passed
    assert not make_report(TestStatus.DONE, TestOutcome.FAIL).passed
    assert not make_report(TestStatus.DONE, TestOutcome.UNVERIFIED).passed


def test_report_without_outcome_has_not_passed():
    assert not make_report(TestStatus.EXECUTING).passed


def test_report_outcome_comes_from_its_output():
    assert make_report(TestStatus.DONE, TestOutcome.FAIL).outcome is TestOutcome.FAIL
    assert make_report(TestStatus.DONE, TestOutcome.UNVERIFIED).outcome is (
        TestOutcome.UNVERIFIED
    )


def test_report_has_no_outcome_before_it_has_output():
    assert make_report(TestStatus.EXECUTING).outcome is None


def test_report_has_no_outcome_while_its_output_is_not_judged():
    report = TestReport(
        TestPath("check.py", "check.py", None, "check.py"),
        TestStatus.EXECUTING,
        output=TestOutput(("partial",)),
    )

    assert report.outcome is None
    assert not report.passed
