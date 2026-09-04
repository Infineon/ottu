import os
from collections.abc import Sequence
from dataclasses import dataclass
from glob import glob, has_magic
from pathlib import Path


@dataclass(frozen=True)
class TestPath:
    """A resolved test path with its useful path representations."""

    # Prevent pytest from collecting this application class as a test class.
    __test__ = False

    absolute_path: Path
    working_dir_relative_path: Path
    project_root_relative_path: Path | None
    file_name: str


class TestPathResolver:
    """Validate and resolve test inputs into :class:`TestPath` objects.

    Relative inputs are searched in the working directory, the project root
    when available, and the default ``test`` or ``tests`` directories under
    those roots. A custom ``tests_dir`` can replace the default directories.
    Absolute inputs are used directly, and glob patterns resolve to all
    matching files. Every resolved result contains absolute, working-directory
    relative, and project-root relative path representations when available.
    """

    @staticmethod
    def resolve(
        test_input: str,
        working_dir: str | Path | None = None,
        project_root: str | Path | None = None,
        tests_dir: str | Path | None = None,
    ) -> list[TestPath]:
        """Resolve one test input into one or more concrete test entries."""
        working_path = Path(working_dir) if working_dir else Path.cwd()
        project_path = Path(project_root).resolve() if project_root else None

        if has_magic(test_input):
            matched_files = sorted(
                {
                    Path(match).resolve()
                    for candidate in TestPathResolver._candidate_paths(
                        test_input, working_path, project_path, tests_dir
                    )
                    for match in glob(str(candidate), recursive=True)
                    if Path(match).is_file()
                }
            )
            if not matched_files:
                raise ValueError(
                    f"Test pattern '{test_input}' did not match any files."
                )
            return [
                TestPathResolver._describe_path(Path(match), working_path, project_path)
                for match in matched_files
            ]

        resolved_path = TestPathResolver._find_input(
            test_input, working_path, project_path, tests_dir
        )
        if resolved_path is None:
            raise ValueError(f"Test path '{test_input}' does not exist.")
        return [
            TestPathResolver._describe_path(resolved_path, working_path, project_path)
        ]

    @staticmethod
    def discover(
        working_dir: str | Path | None = None,
        project_root: str | Path | None = None,
        tests_dir: str | Path | None = None,
        pattern: str = "**/*",
    ) -> list[TestPath]:
        """Discover test files in configured test directories.

        Discovery searches the configured test directory under the working
        directory and, when available, under the project root. It never
        searches either root directly. By default it searches ``test`` and
        ``tests`` recursively. ``tests_dir`` selects a custom directory, and
        ``pattern`` can restrict discovery by extension or any glob rule.
        """
        working_path = Path(working_dir) if working_dir else Path.cwd()
        project_path = Path(project_root).resolve() if project_root else None
        roots = [working_path]
        if project_path and project_path != working_path.resolve():
            roots.append(project_path)
        directory_names = (
            [Path(tests_dir)] if tests_dir else [Path("test"), Path("tests")]
        )

        matches = {
            Path(match).resolve()
            for root in roots
            for directory in directory_names
            for match in glob(str(root / directory / pattern), recursive=True)
            if Path(match).is_file()
        }
        return [
            TestPathResolver._describe_path(match, working_path, project_path)
            for match in sorted(matches)
        ]

    @staticmethod
    def _describe_path(
        test_path: Path, working_dir: Path, project_root: Path | None
    ) -> TestPath:
        absolute_path = test_path.resolve()
        project_relative = (
            absolute_path.relative_to(project_root)
            if project_root and absolute_path.is_relative_to(project_root)
            else None
        )
        return TestPath(
            absolute_path=absolute_path,
            working_dir_relative_path=Path(
                os.path.relpath(absolute_path, working_dir.resolve())
            ),
            project_root_relative_path=project_relative,
            file_name=absolute_path.name,
        )

    @staticmethod
    def validate_and_resolve_all(
        tests: Sequence[str],
        working_dir: str | Path | None = None,
        project_root: str | Path | None = None,
        tests_dir: str | Path | None = None,
        pattern: str = "**/*",
    ) -> list[TestPath]:
        """Validate explicit inputs or discover tests when none are provided."""
        if not tests:
            return TestPathResolver.discover(
                working_dir=working_dir,
                project_root=project_root,
                tests_dir=tests_dir,
                pattern=pattern,
            )

        resolved_tests: list[TestPath] = []
        for test_input in tests:
            resolved_tests.extend(
                TestPathResolver.resolve(
                    test_input, working_dir, project_root, tests_dir
                )
            )
        return resolved_tests

    @staticmethod
    def _candidate_paths(
        test_input: str,
        working_dir: Path,
        project_root: Path | None,
        tests_dir: str | Path | None,
    ) -> list[Path]:
        """Build candidate paths in test-input resolution order.

        Absolute inputs are used as-is. Relative inputs are checked from the
        working directory, the project root when available, and each root's
        ``test`` and ``tests`` directories. A custom ``tests_dir`` replaces
        the default directory names.
        """
        input_path = Path(test_input)
        if input_path.is_absolute():
            return [input_path]

        roots = [working_dir]
        if project_root:
            roots.append(project_root)
        directory_names = (
            [Path(tests_dir)] if tests_dir else [Path("test"), Path("tests")]
        )
        return [root / input_path for root in roots] + [
            root / directory / input_path
            for root in roots
            for directory in directory_names
        ]

    @staticmethod
    def _find_input(
        test_input: str,
        working_dir: Path,
        project_root: Path | None,
        tests_dir: str | Path | None,
    ) -> Path | None:
        """Return the first existing candidate that is a file or directory."""
        for candidate in TestPathResolver._candidate_paths(
            test_input, working_dir, project_root, tests_dir
        ):
            if candidate.exists() and (candidate.is_file() or candidate.is_dir()):
                return candidate
        return None
