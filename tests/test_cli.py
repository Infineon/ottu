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
