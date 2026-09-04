"""Test path resolution tests."""

import pytest
from ottu.test import TestPath, TestPathResolver


def test_resolve_relative_path_from_working_directory(tmp_path):
    test_file = tmp_path / "check.py"
    test_file.touch()

    result = TestPathResolver.resolve("check.py", working_dir=tmp_path)

    assert result == [
        TestPath(test_file, test_file.relative_to(tmp_path), None, "check.py")
    ]


def test_resolve_path_from_default_tests_directory(tmp_path):
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = TestPathResolver.resolve("check.py", working_dir=tmp_path)

    assert result[0].absolute_path == test_file


def test_resolve_path_with_project_relative_form(tmp_path):
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = TestPathResolver.resolve(
        "check.py", working_dir=tmp_path / "work", project_root=tmp_path
    )

    assert result[0].project_root_relative_path == test_file.relative_to(tmp_path)


def test_resolve_absolute_path(tmp_path):
    test_file = tmp_path / "check.py"
    test_file.touch()

    result = TestPathResolver.resolve(str(test_file), working_dir=tmp_path)

    assert result[0].absolute_path == test_file


def test_resolve_all_expands_glob(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "b.py").touch()
    (tests_dir / "a.py").touch()

    result = TestPathResolver.validate_and_resolve_all(
        ["*.py"], working_dir=tmp_path, tests_dir="tests"
    )

    assert [entry.file_name for entry in result] == ["a.py", "b.py"]


def test_resolve_unmatched_glob_raises(tmp_path):
    """A glob with no file matches is rejected."""
    with pytest.raises(ValueError, match="did not match any files"):
        TestPathResolver.resolve("*.py", working_dir=tmp_path)


def test_resolve_missing_path_raises(tmp_path):
    """A non-glob input with no candidates is rejected."""
    with pytest.raises(ValueError, match="does not exist"):
        TestPathResolver.resolve("missing.py", working_dir=tmp_path)


def test_validate_and_resolve_all_combines_inputs(tmp_path):
    """All inputs are resolved into one ordered result list."""
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.touch()
    second.touch()

    result = TestPathResolver.validate_and_resolve_all(
        ["first.py", "second.py"], working_dir=tmp_path
    )

    assert [entry.absolute_path for entry in result] == [first, second]


def test_validate_and_resolve_all_discovers_when_inputs_are_empty(tmp_path):
    """An empty input list delegates to automatic discovery."""
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = TestPathResolver.validate_and_resolve_all(
        [], working_dir=tmp_path, pattern="**/*.py"
    )

    assert [entry.absolute_path for entry in result] == [test_file]


def test_discover_finds_files_recursively_in_default_tests_directory(tmp_path):
    """Discovery finds all files under the default test directory."""
    application_file = tmp_path / "app.py"
    tests_dir = tmp_path / "tests" / "nested"
    tests_dir.mkdir(parents=True)
    first = tests_dir / "first.py"
    second = tests_dir / "second.cpp"
    application_file.touch()
    first.touch()
    second.touch()

    result = TestPathResolver.discover(working_dir=tmp_path)

    assert [entry.absolute_path for entry in result] == [first, second]


def test_discover_applies_custom_pattern_and_directory(tmp_path):
    """Discovery supports custom directories and extension patterns."""
    custom_dir = tmp_path / "fixtures"
    custom_dir.mkdir()
    python_test = custom_dir / "check.py"
    cpp_test = custom_dir / "check.cpp"
    python_test.touch()
    cpp_test.touch()

    result = TestPathResolver.discover(
        working_dir=tmp_path, tests_dir="fixtures", pattern="**/*.py"
    )

    assert [entry.absolute_path for entry in result] == [python_test]


def test_discover_includes_project_root_tests(tmp_path):
    """Discovery searches project-root test directories as well."""
    project_tests = tmp_path / "project" / "tests"
    work_dir = tmp_path / "project" / "work"
    project_tests.mkdir(parents=True)
    work_dir.mkdir()
    test_file = project_tests / "check.py"
    test_file.touch()

    result = TestPathResolver.discover(
        working_dir=work_dir, project_root=tmp_path / "project", pattern="*.py"
    )

    assert [entry.absolute_path for entry in result] == [test_file]
