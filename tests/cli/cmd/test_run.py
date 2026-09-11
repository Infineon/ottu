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
    assert result.output == ""


def test_run_without_tests_reports_empty_resolved_tests(project):
    root, _ = project
    result = CliRunner().invoke(cli, ["--working-dir", str(root), "run"])
    assert result.exit_code == 0
    assert result.output == ""


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
    assert "check.py" in result.output
    assert "PASS" in result.output


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
    assert "check.py" in result.output
    assert "check.cpp" not in result.output


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
    assert "check.py" in result.output
    assert "app.py" not in result.output


def test_run_resolves_working_directory_test(project):
    root, _ = project
    test_file = root / "check.py"
    test_file.touch()
    result = CliRunner().invoke(
        cli,
        ["--project-root", str(root), "--working-dir", str(root), "run", "check.py"],
    )
    assert result.exit_code == 0
    assert "check.py" in result.output


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
    assert "check.py" in result.output


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
    assert "check.py" in result.output


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
    assert "first.py" in result.output
    assert "second.py" in result.output


def test_run_rejects_missing_test_path(project):
    root, _ = project
    result = CliRunner().invoke(
        cli,
        ["--project-root", str(root), "--working-dir", str(root), "run", "missing.py"],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "Test path 'missing.py' does not exist."


def test_run_excludes_valid_test_input(project):
    """Run validates exclusions and removes matching resolved tests."""
    root, _ = project
    included = root / "tests" / "included.py"
    excluded = root / "tests" / "excluded.py"
    included.parent.mkdir()
    included.touch()
    excluded.touch()

    result = CliRunner().invoke(
        cli,
        [
            "--project-root",
            str(root),
            "--working-dir",
            str(root),
            "run",
            "--pattern",
            "**/*.py",
            "--exclude",
            "excluded.py",
        ],
    )

    assert result.exit_code == 0
    assert "included.py" in result.output
    assert "excluded.py" not in result.output


def test_run_accepts_multiple_exclusions(project):
    """Run validates and applies every repeated exclude option."""
    root, _ = project
    tests_dir = root / "tests"
    tests_dir.mkdir()
    included = tests_dir / "included.py"
    excluded_first = tests_dir / "excluded_first.py"
    excluded_second = tests_dir / "excluded_second.py"
    included.touch()
    excluded_first.touch()
    excluded_second.touch()

    result = CliRunner().invoke(
        cli,
        [
            "--project-root",
            str(root),
            "--working-dir",
            str(root),
            "run",
            "--pattern",
            "**/*.py",
            "--exclude",
            "excluded_first.py",
            "--exclude",
            "excluded_second.py",
        ],
    )

    assert result.exit_code == 0
    assert "included.py" in result.output
    assert "excluded_first.py" not in result.output
    assert "excluded_second.py" not in result.output


def test_run_accepts_one_standard_count(project):
    """Run accepts a single non-repeated count option."""
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
            "--count",
            "3",
            "check.py",
        ],
    )

    assert result.exit_code == 0


def test_run_accepts_jobs_option(project):
    """Run accepts a positive concurrent job limit."""
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
            "--jobs",
            "2",
            "check.py",
        ],
    )

    assert result.exit_code == 0
    assert "check.py" in result.output


def test_run_rejects_non_positive_jobs(project):
    """Run rejects a job limit below one."""
    root, _ = project

    result = CliRunner().invoke(
        cli,
        [
            "--project-root",
            str(root),
            "--working-dir",
            str(root),
            "run",
            "--jobs",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid value for" in result.output
    assert "--jobs" in result.output
    assert "x>=1" in result.output


def test_run_accepts_comma_separated_role_counts(project):
    """Run accepts multiple role counts through one count option."""
    root, _ = project
    server_test = root / "server.py"
    client_test = root / "client.py"
    server_test.touch()
    client_test.touch()

    result = CliRunner().invoke(
        cli,
        [
            "--project-root",
            str(root),
            "--working-dir",
            str(root),
            "run",
            "--count",
            "server=2,client=3",
            "server=server.py",
            "client=client.py",
        ],
    )

    assert result.exit_code == 0


def test_run_accepts_repeated_devices(project):
    """Run accepts repeated device selectors in either supported form."""
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
            "--device",
            "board-1",
            "--device",
            "port=/dev/ttyUSB0,baud=9600",
            "check.py",
        ],
    )

    assert result.exit_code == 0


def test_run_rejects_missing_exclusion(project):
    """Run fails when an exclusion cannot be resolved."""
    root, _ = project
    result = CliRunner().invoke(
        cli,
        [
            "--project-root",
            str(root),
            "--working-dir",
            str(root),
            "run",
            "--exclude",
            "missing.py",
        ],
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "Test path 'missing.py' does not exist."
