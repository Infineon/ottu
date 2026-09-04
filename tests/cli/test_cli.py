"""Tests for CLI setup and entry-point behavior."""

import click
import pytest
from click.testing import CliRunner
from ottu.cli import cli


@pytest.fixture
def runner():
    """Provide a CLI runner for testing."""
    return CliRunner()


def test_cli_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_cli_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "On-target testing utility" in result.output


def test_main(monkeypatch):
    called = False

    def mock_cli():
        nonlocal called
        called = True

    monkeypatch.setattr("ottu.cli.cli", mock_cli)
    from ottu.cli import main

    main()
    assert called


def test_cli_options_create_context(tmp_path):
    project_root = tmp_path
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    (project_root / ".ottu").touch()

    with click.Context(cli) as context:
        cli.callback.__wrapped__(context, str(project_root), str(working_dir))

    assert context.obj.project_root == project_root
    assert context.obj.working_dir == working_dir
