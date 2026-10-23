"""Test report tests."""

from ottu.output import TestOutput, TestResult
from ottu.report import TestReport, TestStatus
from ottu.test_path import TestPath


def make_report(status, result=None):
    return TestReport(
        TestPath("check.py", "check.py", None, "check.py"),
        status,
        output=TestOutput((), result) if result is not None else None,
    )


def test_report_passes_only_with_passing_result():
    assert make_report(TestStatus.DONE, TestResult.PASS).passed
    assert not make_report(TestStatus.DONE, TestResult.FAIL).passed
    assert not make_report(TestStatus.DONE, TestResult.UNVERIFIED).passed


def test_report_without_result_has_not_passed():
    assert not make_report(TestStatus.EXECUTING).passed


def test_report_result_comes_from_its_output():
    assert make_report(TestStatus.DONE, TestResult.FAIL).result is TestResult.FAIL
    assert make_report(TestStatus.DONE, TestResult.UNVERIFIED).result is (
        TestResult.UNVERIFIED
    )


def test_report_has_no_result_before_it_has_output():
    assert make_report(TestStatus.EXECUTING).result is None


def test_report_has_no_result_while_its_output_is_not_judged():
    report = TestReport(
        TestPath("check.py", "check.py", None, "check.py"),
        TestStatus.EXECUTING,
        output=TestOutput(("partial",)),
    )

    assert report.result is None
    assert not report.passed
