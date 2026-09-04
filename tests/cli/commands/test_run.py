"""Tests for the ``ottu run`` command."""

import pytest
from click.testing import CliRunner
from ottu.cli import cli


@pytest.fixture
def project(tmp_path):
    """Create a project tree with a .ottu marker at its root."""
    (tmp_path / ".ottu").touch()
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    return tmp_path, nested


def test_run_without_project_marker_reports_none(tmp_path):
    result = CliRunner().invoke(cli, ["--working-dir", str(tmp_path), "run"])
    assert result.exit_code == 0
    assert f"Project root: None\nWorking directory: {tmp_path}\n" in result.output
    assert "Tests: ()\nResolved tests: []\n" in result.output


def test_run_without_tests_reports_empty_resolved_tests(project):
    root, _ = project
    result = CliRunner().invoke(cli, ["--working-dir", str(root), "run"])
    assert result.exit_code == 0
    assert "Tests: ()\nResolved tests: []\n" in result.output


def test_run_discovers_default_test_directory(project):
    root, _ = project
    test_file = root / "tests" / "nested" / "check.py"
    test_file.parent.mkdir(parents=True)
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        ["--project-root", str(root), "--working-dir", str(root), "run"],
    )
    assert result.exit_code == 0
    assert str(test_file) in result.output


def test_run_discovery_accepts_custom_directory_and_pattern(project):
    root, _ = project
    custom_dir = root / "fixtures"
    custom_dir.mkdir()
    python_test = custom_dir / "check.py"
    cpp_test = custom_dir / "check.cpp"
    python_test.touch()
    cpp_test.touch()
    result = CliRunner().invoke(
        cli,
        [
            "--project-root",
            str(root),
            "--working-dir",
            str(root),
            "run",
            "--tests-dir",
            "fixtures",
            "--pattern",
            "**/*.py",
        ],
    )
    assert result.exit_code == 0
    assert str(python_test) in result.output
    assert str(cpp_test) not in result.output


def test_run_pattern_ignores_shell_expanded_paths(project):
    root, _ = project
    application_file = root / "app.py"
    test_file = root / "tests" / "check.py"
    test_file.parent.mkdir()
    application_file.touch()
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        [
            "--working-dir",
            str(root),
            "run",
            "--pattern",
            "**/*.py",
            str(application_file),
            str(test_file),
        ],
    )
    assert result.exit_code == 0
    assert "Tests: ()" in result.output
    assert str(test_file) in result.output
    assert str(application_file) not in result.output


def test_run_resolves_working_directory_test(project):
    root, _ = project
    test_file = root / "check.py"
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        ["--project-root", str(root), "--working-dir", str(root), "run", "check.py"],
    )
    assert result.exit_code == 0
    assert "Tests: ('check.py',)" in result.output
    assert str(test_file) in result.output


def test_run_resolves_default_tests_directory_test(project):
    root, _ = project
    test_file = root / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        ["--project-root", str(root), "--working-dir", str(root), "run", "check.py"],
    )
    assert result.exit_code == 0
    assert str(test_file) in result.output


def test_run_resolves_absolute_test_path(project):
    root, _ = project
    test_file = root / "check.py"
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        [
            "--project-root",
            str(root),
            "--working-dir",
            str(root),
            "run",
            str(test_file),
        ],
    )
    assert result.exit_code == 0
    assert str(test_file) in result.output


def test_run_expands_test_glob(project):
    root, _ = project
    tests_dir = root / "tests"
    tests_dir.mkdir()
    first = tests_dir / "first.py"
    second = tests_dir / "second.py"
    first.touch()
    second.touch()
    result = CliRunner().invoke(
        cli,
        [
            "--project-root",
            str(root),
            "--working-dir",
            str(root),
            "run",
            "tests/*.py",
        ],
    )
    assert result.exit_code == 0
    assert str(first) in result.output
    assert str(second) in result.output


def test_run_rejects_missing_test_path(project):
    root, _ = project
    result = CliRunner().invoke(
        cli,
        ["--project-root", str(root), "--working-dir", str(root), "run", "missing.py"],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "Test path 'missing.py' does not exist."
