"""Tests for shared CLI context."""

import dataclasses
from pathlib import Path

import pytest
from ottu.cli.context import CliContext


@pytest.fixture
def project(tmp_path):
    """Create a project tree with a .ottu marker at its root."""
    (tmp_path / ".ottu").touch()
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    return tmp_path, nested


def test_find_project_root_at_start(project):
    root, _ = project
    assert CliContext.find_project_root(root) == root


def test_find_project_root_walks_up(project):
    root, nested = project
    assert CliContext.find_project_root(nested) == root


def test_find_project_root_accepts_str_path(project):
    root, nested = project
    assert CliContext.find_project_root(str(nested)) == root


def test_find_project_root_defaults_to_cwd(project, monkeypatch):
    root, nested = project
    monkeypatch.chdir(nested)
    assert CliContext.find_project_root() == root


def test_find_project_root_not_found(tmp_path):
    assert CliContext.find_project_root(tmp_path) is None


def test_discover_defaults_working_dir_to_cwd(project, monkeypatch):
    root, nested = project
    monkeypatch.chdir(nested)
    context = CliContext.discover()
    assert context.project_root == root
    assert context.working_dir == nested


def test_discover_working_dir_defaults_to_cwd(project, monkeypatch):
    root, nested = project
    monkeypatch.chdir(root)
    context = CliContext.discover(nested)
    assert context.project_root == root
    assert context.working_dir == root


def test_discover_explicit_working_dir(project):
    root, nested = project
    context = CliContext.discover(nested, working_dir=root)
    assert context.project_root == root
    assert context.working_dir == root


def test_discover_working_dir_accepts_str(project):
    root, nested = project
    context = CliContext.discover(nested, working_dir=str(nested))
    assert context.working_dir == Path(nested)


def test_cli_context_is_frozen(project):
    root, _ = project
    context = CliContext.discover(root)
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.project_root = Path("/tmp")
