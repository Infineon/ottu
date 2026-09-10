"""Tests for user-facing terminal output."""

from ottu.output import Output


def test_test_result_prints_pass(capsys):
    Output.print_test_result("check.py", True)

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "PASS" in output


def test_test_result_prints_fail(capsys):
    Output.print_test_result("check.py", False)

    output = capsys.readouterr().out
    assert "check.py" in output
    assert "FAIL" in output
