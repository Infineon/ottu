import os
from collections.abc import Sequence
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class TestPathContext:
    """Context used to resolve test selectors into paths."""

    __test__ = False

    working_dir: str | Path | None = None
    project_root: str | Path | None = None
    tests_dir: str | Path | None = None
    pattern: str = "**/*"


class TestPathResolver:
    """Validate and resolve test selectors into :class:`TestPath` objects.

    Relative selectors are searched in the working directory, the project root
    when available, and the default ``test`` or ``tests`` directories under
    those roots. A custom ``tests_dir`` can replace the default directories.
    Absolute selectors are used directly, and glob patterns resolve to all
    matching files. Every resolved result contains absolute, working-directory
    relative, and project-root relative path representations when available.
    """

    @staticmethod
    def resolve(
        test_selector: str,
        context: TestPathContext,
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
            if not matched_files:
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
        return [TestPathResolver._describe_path(resolved_path, context)]

    @staticmethod
    def discover(
        context: TestPathContext,
    ) -> list[TestPath]:
        """Discover test files in configured test directories.

        Discovery searches the configured test directory under the working
        directory and, when available, under the project root. It never
        searches either root directly. By default it searches ``test`` and
        ``tests`` recursively. ``tests_dir`` selects a custom directory, and
        ``pattern`` can restrict discovery by extension or any glob rule.
        """
        working_path = Path(context.working_dir) if context.working_dir else Path.cwd()
        project_path = (
            Path(context.project_root).resolve() if context.project_root else None
        )
        tests_dir = context.tests_dir
        pattern = context.pattern
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
            TestPathResolver._describe_path(match, context) for match in sorted(matches)
        ]

    @staticmethod
    def _describe_path(test_path: Path, context: TestPathContext) -> TestPath:
        working_dir = Path(context.working_dir) if context.working_dir else Path.cwd()
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

        excluded_paths = {
            path.absolute_path
            for exclude_test_selector in exclude_test_selectors
            for path in TestPathResolver.resolve(exclude_test_selector, context)
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
        ``test`` and ``tests`` directories. A custom ``tests_dir`` replaces
        the default directory names.
        """
        input_path = Path(test_selector)
        if input_path.is_absolute():
            return [input_path]

        working_dir = Path(context.working_dir) if context.working_dir else Path.cwd()
        project_root = (
            Path(context.project_root).resolve() if context.project_root else None
        )
        roots = [working_dir]
        if project_root:
            roots.append(project_root)
        directory_names = (
            [Path(context.tests_dir)]
            if context.tests_dir
            else [Path("test"), Path("tests")]
        )
        return [root / input_path for root in roots] + [
            root / directory / input_path
            for root in roots
            for directory in directory_names
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


@dataclass(frozen=True)
class TestOpts:
    """Execution options associated with one test."""

    __test__ = False

    role: str | None = None
    count: int = 1

    def __post_init__(self) -> None:
        self._validate_role(self.role)
        self._validate_count(self.count)

    @staticmethod
    def _validate_role(role: str | None) -> None:
        """Reject empty or whitespace-only role names."""
        if role is not None and not role.strip():
            raise ValueError("Role must not be empty.")

    @staticmethod
    def _validate_count(count: int) -> None:
        """Reject non-integer and non-positive counts."""
        if type(count) is not int or count < 1:
            raise ValueError("Test count must be a positive integer.")


@dataclass
class Test:
    # Prevent pytest from collecting this application class as a test class.
    __test__ = False

    test_path: TestPath
    options: TestOpts = field(default_factory=TestOpts)

    @classmethod
    def from_inputs(
        cls,
        test_selectors: Sequence[str],
        *,
        context: TestPathContext | None = None,
        exclude_test_selectors: Sequence[str] = (),
        options: TestOpts = TestOpts(),
    ) -> list["Test"]:
        """Resolve test selectors and create tests with supplied options."""
        context = context or TestPathContext()
        test_paths = TestPathResolver.resolve_all(
            test_selectors,
            context,
            exclude_test_selectors=exclude_test_selectors,
        )
        return [cls(test_path, options=options) for test_path in test_paths]

    def run(self) -> None:
        """Run one resolved test using the future framework backend."""
        print(f"Running test: {self.test_path.absolute_path}")
