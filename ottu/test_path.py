"""Test path models, configuration, and selector resolution."""

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from glob import glob, has_magic
from pathlib import Path, PureWindowsPath

from ottu.config_models.project.config import ProjectConfig


@dataclass(frozen=True)
class TestPath:
    """A resolved test path with its useful path representations."""

    # Prevent pytest from collecting this application class as a test class.
    __test__ = False

    absolute_path: Path
    working_dir_relative_path: Path
    project_root_relative_path: Path | None
    file_name: str


@dataclass(frozen=True)
class TestPathContext:
    """Context used to resolve test selectors into paths."""

    __test__ = False

    working_dir: str | Path = field(default_factory=Path.cwd)
    project_root: str | Path | None = None
    test_dirs: tuple[str | Path, ...] = ("test", "tests")
    test_include_patterns: list[str] = field(default_factory=lambda: ["**/*"])
    test_exclude_patterns: list[str] = field(default_factory=list)

    @classmethod
    def load(
        cls,
        working_dir: str | Path = Path.cwd(),
        project_root: str | Path | None = None,
    ) -> "TestPathContext":
        project_config = ProjectConfig.from_project_root(project_root)
        return cls(
            working_dir=working_dir,
            project_root=project_root,
            test_dirs=tuple(project_config.test_dirs),
            test_include_patterns=project_config.test_include_patterns,
            test_exclude_patterns=project_config.test_exclude_patterns,
        )

    def __post_init__(self) -> None:
        """Validate context arguments and normalize configured test directories."""
        self._validate_working_dir()
        self._validate_project_root()
        self._validate_test_dirs()
        self._validate_test_include_patterns()
        self._validate_test_exclude_patterns()

    def _validate_working_dir(self) -> None:
        """Validate that the working directory is a directory when provided."""
        if not Path(self.working_dir).is_dir():
            raise ValueError(f"Working directory does not exist: {self.working_dir}")

    def _validate_project_root(self) -> None:
        """Validate that the project root is a directory when provided."""
        if self.project_root is not None and not Path(self.project_root).is_dir():
            raise ValueError(f"Project root does not exist: {self.project_root}")

    def _validate_test_dirs(self) -> None:
        """Validate and normalize configured test directories."""
        if not self.test_dirs or any(
            not str(test_dir).strip() for test_dir in self.test_dirs
        ):
            raise ValueError("Test directories must contain non-empty paths.")

        roots = [Path(self.working_dir)]
        if self.project_root:
            project_root = Path(self.project_root).resolve()
            if project_root != roots[0].resolve():
                roots.append(project_root)
        existing_dirs = tuple(
            test_dir
            for test_dir in self.test_dirs
            if any((root / test_dir).is_dir() for root in roots)
        )
        object.__setattr__(self, "test_dirs", existing_dirs)

    def _validate_test_include_patterns(self) -> None:
        """Validate include patterns and require at least one pattern."""
        self._validate_patterns(
            self.test_include_patterns,
            "Test include patterns",
            allow_empty=False,
        )

    def _validate_test_exclude_patterns(self) -> None:
        """Validate optional exclude patterns."""
        self._validate_patterns(
            self.test_exclude_patterns,
            "Test exclude patterns",
            allow_empty=True,
        )

    @staticmethod
    def _validate_patterns(
        patterns: list[str], name: str, *, allow_empty: bool
    ) -> None:
        """Validate that patterns are non-empty relative glob patterns."""
        if not allow_empty and not patterns:
            raise ValueError(f"{name} must contain at least one pattern.")
        for pattern in patterns:
            if not isinstance(pattern, str) or not pattern.strip():
                raise ValueError(f"{name} must contain non-empty strings.")
            if Path(pattern).is_absolute() or PureWindowsPath(pattern).is_absolute():
                raise ValueError(f"{name} must contain relative patterns: {pattern}")
            if ".." in Path(pattern).parts:
                raise ValueError(
                    f"{name} must not escape its test directory: {pattern}"
                )


class TestPathResolver:
    """Validate and resolve test selectors into :class:`TestPath` objects.

    Relative selectors are searched in the working directory, the project root
    when available, and the default ``test`` or ``tests`` directories under
    those roots. Custom ``test_dirs`` can replace the default directories.
    Absolute selectors are used directly, and glob patterns resolve to all
    matching files. Every resolved result contains absolute, working-directory
    relative, and project-root relative path representations when available.
    """

    @staticmethod
    def resolve(
        test_selector: str,
        context: TestPathContext,
        *,
        allow_no_matches: bool = False,
    ) -> list[TestPath]:
        """Resolve one selector into one or more concrete test paths."""
        if has_magic(test_selector):
            matched_files = sorted(
                {
                    Path(match).resolve()
                    for candidate in TestPathResolver._candidate_paths(
                        test_selector, context
                    )
                    for match in glob(str(candidate), recursive=True)
                    if Path(match).is_file()
                }
            )
            if not matched_files and not allow_no_matches:
                raise ValueError(
                    f"Test pattern '{test_selector}' did not match any files."
                )
            return [
                TestPathResolver._describe_path(Path(match), context)
                for match in matched_files
            ]

        resolved_path = TestPathResolver._find_input(test_selector, context)
        if resolved_path is None:
            raise ValueError(f"Test path '{test_selector}' does not exist.")
        if resolved_path.is_dir():
            test_files = sorted(
                path for path in resolved_path.iterdir() if path.is_file()
            )
            if not test_files:
                raise ValueError(
                    f"Test directory '{test_selector}' contains no test files."
                )
            return [
                TestPathResolver._describe_path(path, context) for path in test_files
            ]
        return [TestPathResolver._describe_path(resolved_path, context)]

    @staticmethod
    def discover(
        context: TestPathContext,
    ) -> list[TestPath]:
        """Discover test files in configured test directories.

        Discovery searches the configured test directory under the working
        directory and, when available, under the project root. It never
        searches either root directly. By default it searches ``test`` and
        ``tests`` recursively. ``test_dirs`` selects custom directories, and
        ``test_include_patterns`` can restrict discovery by extension or any
        glob rule.
        """
        working_path = Path(context.working_dir)
        project_path = (
            Path(context.project_root).resolve() if context.project_root else None
        )
        roots = [working_path]
        if project_path and project_path != working_path.resolve():
            roots.append(project_path)
        matches = {
            Path(match).resolve()
            for root in roots
            for directory in TestPathResolver._existing_test_dirs(context, root)
            for pattern in context.test_include_patterns
            for match in glob(str(root / directory / pattern), recursive=True)
            if Path(match).is_file()
        }
        return [
            TestPathResolver._describe_path(match, context) for match in sorted(matches)
        ]

    @staticmethod
    def _describe_path(test_path: Path, context: TestPathContext) -> TestPath:
        working_dir = Path(context.working_dir)
        project_root = (
            Path(context.project_root).resolve() if context.project_root else None
        )
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
    def resolve_all(
        test_selectors: Sequence[str],
        context: TestPathContext,
        exclude_test_selectors: Sequence[str] = (),
    ) -> list[TestPath]:
        """Resolve test selectors, then remove excluded test selectors."""
        if not test_selectors:
            resolved_tests = TestPathResolver.discover(context)
        else:
            resolved_tests = []
            for test_selector in test_selectors:
                resolved_tests.extend(TestPathResolver.resolve(test_selector, context))

        exclude_selectors = (*context.test_exclude_patterns, *exclude_test_selectors)
        excluded_paths = {
            path.absolute_path
            for exclude_test_selector in exclude_selectors
            for path in TestPathResolver.resolve(
                exclude_test_selector,
                context,
                allow_no_matches=True,
            )
        }
        return [
            test_path
            for test_path in resolved_tests
            if test_path.absolute_path not in excluded_paths
        ]

    @staticmethod
    def _candidate_paths(
        test_selector: str,
        context: TestPathContext,
    ) -> list[Path]:
        """Build candidate paths in selector resolution order.

        Absolute selectors are used as-is. Relative selectors are checked from the
        working directory, the project root when available, and each root's
        ``test`` and ``tests`` directories. Custom ``test_dirs`` replace
        the default directory names.
        """
        input_path = Path(test_selector)
        if input_path.is_absolute():
            return [input_path]

        working_dir = Path(context.working_dir)
        project_root = (
            Path(context.project_root).resolve() if context.project_root else None
        )
        roots = [working_dir]
        if project_root:
            roots.append(project_root)
        directory_names = TestPathResolver._existing_test_dirs(context, working_dir)
        project_directories = (
            TestPathResolver._existing_test_dirs(context, project_root)
            if project_root
            else []
        )
        return [root / input_path for root in roots] + [
            root / directory / input_path
            for root, directories in zip(roots, [directory_names, project_directories])
            for directory in directories
        ]

    @staticmethod
    def _existing_test_dirs(context: TestPathContext, root: Path | None) -> list[Path]:
        """Return configured test directories that exist below a root."""
        if root is None:
            return []
        return [
            Path(test_dir)
            for test_dir in context.test_dirs
            if (root / test_dir).is_dir()
        ]

    @staticmethod
    def _find_input(
        test_selector: str,
        context: TestPathContext,
    ) -> Path | None:
        """Return the first existing candidate that is a file or directory."""
        for candidate in TestPathResolver._candidate_paths(test_selector, context):
            if candidate.exists() and (candidate.is_file() or candidate.is_dir()):
                return candidate
        return None
