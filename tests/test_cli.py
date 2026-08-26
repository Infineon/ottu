"""Test suite for OTTU CLI."""

import pytest
from click.testing import CliRunner
from ottu.cli import cli


@pytest.fixture
def runner():
    """Provide a CLI runner for testing."""
    return CliRunner()


def test_cli_version(runner):
    """Test CLI version option."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_cli_help(runner):
    """Test CLI help option."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "On-target testing utility" in result.output


def test_main(monkeypatch):
    """Test main entry point."""
    called = False

    def mock_cli():
        nonlocal called
        called = True

    monkeypatch.setattr("ottu.cli.cli", mock_cli)
    from ottu.cli import main

    main()
    assert called


def test_cli_group_function():
    """Test calling cli group callback function directly."""
    from ottu.cli import cli

    if cli.callback is not None:
        cli.callback()
