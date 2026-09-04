"""Tests for executing collected test objects."""

from ottu.test import Test, TestPath, TestSuite


def test_test_run_reports_resolved_test(capsys, tmp_path):
    """A test object runs its resolved test path."""
    test_path = TestPath(tmp_path / "check.py", tmp_path / "check.py", None, "check.py")

    Test(test_path).run()

    assert f"Running test: {tmp_path / 'check.py'}\n" == capsys.readouterr().out


def test_test_suite_runs_each_test_in_order(capsys, tmp_path):
    """A suite iterates over all collected tests in order."""
    first = TestPath(tmp_path / "first.py", tmp_path / "first.py", None, "first.py")
    second = TestPath(tmp_path / "second.py", tmp_path / "second.py", None, "second.py")

    TestSuite([first, second]).run()

    assert capsys.readouterr().out == (
        f"Running test: {tmp_path / 'first.py'}\n"
        f"Running test: {tmp_path / 'second.py'}\n"
    )
