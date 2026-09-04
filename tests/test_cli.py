"""Test suite for OTTU CLI."""

import dataclasses
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from ottu.cli import CliContext, cli


@pytest.fixture
def runner():
    """Provide a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def project(tmp_path):
    """Create a project tree with a .ottu marker at its root."""
    (tmp_path / ".ottu").touch()
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    return tmp_path, nested


def test_find_project_root_at_start(project):
    """Marker in the starting directory itself is found."""
    root, _ = project
    assert CliContext.find_project_root(root) == root


def test_find_project_root_walks_up(project):
    """Marker is found by walking up from a nested directory."""
    root, nested = project
    assert CliContext.find_project_root(nested) == root


def test_find_project_root_accepts_str_path(project):
    """A string start path is accepted."""
    root, nested = project
    assert CliContext.find_project_root(str(nested)) == root


def test_find_project_root_defaults_to_cwd(project, monkeypatch):
    """Without a start path the current working directory is used."""
    root, nested = project
    monkeypatch.chdir(nested)
    assert CliContext.find_project_root() == root


def test_find_project_root_not_found(tmp_path):
    """Reaching the filesystem root without a marker returns None."""
    assert CliContext.find_project_root(tmp_path) is None


def test_discover_defaults_working_dir_to_cwd(project, monkeypatch):
    """Without any path override working_dir falls back to the cwd."""
    root, nested = project
    monkeypatch.chdir(nested)
    ctx = CliContext.discover()
    assert ctx.project_root == root
    assert ctx.working_dir == nested


def test_discover_working_dir_defaults_to_cwd(project, monkeypatch):
    """When only start is given working_dir defaults to the cwd."""
    root, nested = project
    monkeypatch.chdir(root)
    ctx = CliContext.discover(nested)
    assert ctx.project_root == root
    assert ctx.working_dir == root


def test_discover_explicit_working_dir(project):
    """An explicit working_dir overrides the start path."""
    root, nested = project
    ctx = CliContext.discover(nested, working_dir=root)
    assert ctx.project_root == root
    assert ctx.working_dir == root


def test_discover_working_dir_accepts_str(project):
    """A string working_dir is coerced to Path."""
    root, nested = project
    ctx = CliContext.discover(nested, working_dir=str(nested))
    assert ctx.working_dir == Path(nested)


def test_cli_context_is_frozen(project):
    """CliContext is immutable."""
    root, _ = project
    ctx = CliContext.discover(root)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.project_root = Path("/tmp")


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


def test_cli_options_create_context(runner, project):
    """Project and working directory options are stored in the context."""
    root, nested = project
    with click.Context(cli) as context:
        cli.callback.__wrapped__(context, str(root), str(nested))

    assert context.obj == CliContext(project_root=root, working_dir=nested)
