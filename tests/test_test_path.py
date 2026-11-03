"""Test path resolution tests."""

from pathlib import Path

import pytest
from ottu.test_path import (
    TestPath,
    TestPathContext,
    TestPathInput,
    TestPathResolver,
)


def test_test_path_from_input_returns_the_paths_of_the_input(tmp_path):
    test_file = tmp_path / "check.py"
    test_file.touch()

    result = TestPath.from_input(
        TestPathInput(test_selector="check.py"),
        TestPathContext(working_dir=tmp_path),
    )

    assert result == [
        TestPath(test_file, test_file.relative_to(tmp_path), None, "check.py")
    ]


def test_test_path_from_input_expands_a_pattern_and_ignores_the_role(tmp_path):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()

    result = TestPath.from_input(
        TestPathInput(role="server", test_selector="*.py"),
        TestPathContext(working_dir=tmp_path),
    )

    assert [path.file_name for path in result] == ["a.py", "b.py"]


def test_test_path_from_input_rejects_an_unknown_test(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        TestPath.from_input(
            TestPathInput(test_selector="missing.py"),
            TestPathContext(working_dir=tmp_path),
        )


def test_resolve_relative_path_from_working_directory(tmp_path):
    test_file = tmp_path / "check.py"
    test_file.touch()

    result = TestPathResolver.resolve("check.py", TestPathContext(working_dir=tmp_path))

    assert result == [
        TestPath(test_file, test_file.relative_to(tmp_path), None, "check.py")
    ]


def test_resolve_path_from_default_tests_directory(tmp_path):
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()

    result = TestPathResolver.resolve("check.py", TestPathContext(working_dir=tmp_path))

    assert result[0].absolute_path == test_file


def test_test_path_context_defaults_to_existing_test_directories(tmp_path):
    (tmp_path / "tests").mkdir()

    context = TestPathContext(working_dir=tmp_path)

    assert context.test_dirs == ("tests",)


def test_test_path_context_defaults_to_all_files():
    assert TestPathContext().test_include_patterns == ["**/*"]


def test_test_path_context_defaults_to_no_exclude_patterns():
    assert TestPathContext().test_exclude_patterns == []


def test_test_path_context_loads_project_config(tmp_path):
    (tmp_path / "checks").mkdir()
    (tmp_path / ".ottu").write_text(
        "version: 1\n"
        "test_dirs: [checks]\n"
        "test_include_patterns: ['**/*.py']\n"
        "test_exclude_patterns: ['**/generated/**']\n"
        "backend: debug\n",
        encoding="utf-8",
    )

    context = TestPathContext.load(project_root=tmp_path)

    assert context.test_dirs == ("checks",)
    assert context.test_include_patterns == ["**/*.py"]
    assert context.test_exclude_patterns == ["**/generated/**"]


def test_test_path_context_defaults_working_directory_to_current_directory():
    assert TestPathContext().working_dir == Path.cwd()


def test_test_path_context_rejects_missing_working_directory(tmp_path):
    with pytest.raises(ValueError, match="Working directory does not exist"):
        TestPathContext(working_dir=tmp_path / "missing")


def test_test_path_context_rejects_missing_project_root(tmp_path):
    with pytest.raises(ValueError, match="Project root does not exist"):
        TestPathContext(project_root=tmp_path / "missing")


@pytest.mark.parametrize("test_dirs", [(), ("",)])
def test_test_path_context_rejects_empty_test_directories(test_dirs):
    with pytest.raises(ValueError, match="Test directories"):
        TestPathContext(test_dirs=test_dirs)


@pytest.mark.parametrize("patterns", [[], ["  "]])
def test_test_path_context_rejects_empty_include_patterns(patterns):
    with pytest.raises(ValueError, match="Test include patterns"):
        TestPathContext(test_include_patterns=patterns)


@pytest.mark.parametrize("patterns", [[""], ["/tmp/*.ino"], ["../*.ino"]])
def test_test_path_context_rejects_invalid_include_patterns(patterns):
    with pytest.raises(ValueError, match="Test include patterns"):
        TestPathContext(test_include_patterns=patterns)


@pytest.mark.parametrize("patterns", [[""], ["/tmp/*.ino"], ["../*.ino"]])
def test_test_path_context_rejects_invalid_exclude_patterns(patterns):
    with pytest.raises(ValueError, match="Test exclude patterns"):
        TestPathContext(test_exclude_patterns=patterns)


def test_test_path_context_keeps_directory_existing_under_project_root(tmp_path):
    project_root = tmp_path / "project"
    working_dir = project_root / "work"
    (project_root / "tests").mkdir(parents=True)
    working_dir.mkdir()

    context = TestPathContext(working_dir=working_dir, project_root=project_root)

    assert context.test_dirs == ("tests",)


def test_existing_test_dirs_returns_empty_for_missing_root(tmp_path):
    context = TestPathContext(working_dir=tmp_path)

    assert TestPathResolver._existing_test_dirs(context, None) == []


def test_resolve_path_with_project_relative_form(tmp_path):
    test_file = tmp_path / "tests" / "check.py"
    test_file.parent.mkdir()
    test_file.touch()
    working_dir = tmp_path / "work"
    working_dir.mkdir()

    result = TestPathResolver.resolve(
        "check.py",
        TestPathContext(working_dir=working_dir, project_root=tmp_path),
    )

    assert result[0].project_root_relative_path == test_file.relative_to(tmp_path)


def test_resolve_absolute_path(tmp_path):
    test_file = tmp_path / "check.py"
    test_file.touch()

    result = TestPathResolver.resolve(
        str(test_file), TestPathContext(working_dir=tmp_path)
    )

    assert result[0].absolute_path == test_file


def test_resolve_directory_expands_child_test_files(tmp_path):
    test_directory = tmp_path / "hello-universe"
    test_directory.mkdir()
    test_file = test_directory / "hello-universe.ino"
    test_file.touch()
    (test_directory / "hello-universe.ino.exp").touch()

    result = TestPathResolver.resolve(
        "hello-universe", TestPathContext(working_dir=tmp_path)
    )

    assert [entry.absolute_path for entry in result] == [
        test_file,
        test_file.with_suffix(".ino.exp"),
    ]


def test_resolve_empty_directory_raises(tmp_path):
    (tmp_path / "empty").mkdir()

    with pytest.raises(ValueError, match="contains no test files"):
        TestPathResolver.resolve("empty", TestPathContext(working_dir=tmp_path))


def test_resolve_unmatched_glob_raises(tmp_path):
    """A glob with no file matches is rejected."""
    with pytest.raises(ValueError, match="did not match any files"):
        TestPathResolver.resolve("*.py", TestPathContext(working_dir=tmp_path))


def test_resolve_missing_path_raises(tmp_path):
    """A non-glob input with no candidates is rejected."""
    with pytest.raises(ValueError, match="does not exist"):
        TestPathResolver.resolve("missing.py", TestPathContext(working_dir=tmp_path))


def test_is_single_file_finds_files_in_test_directories(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "check.py").touch()

    assert TestPathResolver.is_single_file(
        "check.py", TestPathContext(working_dir=tmp_path)
    )


@pytest.mark.parametrize("selector", ["*.py", "suite", "missing.py"])
def test_is_single_file_rejects_non_file_selectors(tmp_path, selector):
    (tmp_path / "suite").mkdir()

    assert not TestPathResolver.is_single_file(
        selector, TestPathContext(working_dir=tmp_path)
    )


def test_is_single_file_rejects_a_context_excluded_file(tmp_path):
    test_file = tmp_path / "skip_server.py"
    test_file.touch()
    context = TestPathContext(
        working_dir=tmp_path,
        test_exclude_patterns=["skip_*.py"],
    )

    assert not TestPathResolver.is_single_file("skip_server.py", context)


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

    result = TestPathResolver.discover(TestPathContext(working_dir=tmp_path))

    assert [entry.absolute_path for entry in result] == [first, second]


def test_discover_includes_all_files(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "check.py"
    expected_file = tests_dir / "check.py.exp"
    test_file.touch()
    expected_file.touch()

    result = TestPathResolver.discover(
        TestPathContext(working_dir=tmp_path, test_include_patterns=["**/*"])
    )

    assert [entry.absolute_path for entry in result] == [test_file, expected_file]


def test_discover_applies_custom_pattern_and_directory(tmp_path):
    """Discovery supports custom directories and extension patterns."""
    custom_dir = tmp_path / "fixtures"
    custom_dir.mkdir()
    python_test = custom_dir / "check.py"
    cpp_test = custom_dir / "check.cpp"
    python_test.touch()
    cpp_test.touch()

    result = TestPathResolver.discover(
        TestPathContext(
            working_dir=tmp_path,
            test_dirs=("fixtures",),
            test_include_patterns=["**/*.py"],
        )
    )

    assert [entry.absolute_path for entry in result] == [python_test]


def test_discover_applies_multiple_include_patterns(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    python_test = tests_dir / "check.py"
    cpp_test = tests_dir / "check.cpp"
    python_test.touch()
    cpp_test.touch()

    result = TestPathResolver.discover(
        TestPathContext(
            working_dir=tmp_path,
            test_include_patterns=["**/*.py", "**/*.cpp"],
        )
    )

    assert [entry.absolute_path for entry in result] == [cpp_test, python_test]


def test_discover_includes_project_root_tests(tmp_path):
    """Discovery searches project-root test directories as well."""
    project_tests = tmp_path / "project" / "tests"
    work_dir = tmp_path / "project" / "work"
    project_tests.mkdir(parents=True)
    work_dir.mkdir()
    test_file = project_tests / "check.py"
    test_file.touch()

    result = TestPathResolver.discover(
        TestPathContext(
            working_dir=work_dir,
            project_root=tmp_path / "project",
            test_include_patterns=["*.py"],
        )
    )

    assert [entry.absolute_path for entry in result] == [test_file]


def names(test_paths):
    return [test_path.file_name for test_path in test_paths]


def test_exclude_removes_the_given_paths_and_keeps_the_order(tmp_path):
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).touch()
    context = TestPathContext(working_dir=tmp_path)
    test_paths = TestPathResolver.resolve("*.py", context)
    exclude = TestPathResolver.resolve("b.py", context)

    result = TestPathResolver.exclude(test_paths, exclude, context)

    assert names(result) == ["a.py", "c.py"]


def test_exclude_removes_the_paths_matching_the_context_patterns(tmp_path):
    for name in ("a.py", "skip_b.py", "skip_c.py"):
        (tmp_path / name).touch()
    context = TestPathContext(working_dir=tmp_path, test_exclude_patterns=["skip_*.py"])
    test_paths = TestPathResolver.resolve("*.py", context)

    result = TestPathResolver.exclude(test_paths, [], context)

    assert names(result) == ["a.py"]


def test_exclude_ignores_a_pattern_without_matches(tmp_path):
    (tmp_path / "a.py").touch()
    context = TestPathContext(working_dir=tmp_path, test_exclude_patterns=["none_*.py"])
    test_paths = TestPathResolver.resolve("a.py", context)

    assert TestPathResolver.exclude(test_paths, [], context) == test_paths
