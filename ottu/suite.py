from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from glob import has_magic
from multiprocessing import Process
from re import fullmatch

from ottu.test import Test, TestOpts, TestPathContext, TestPathResolver


def _run_test_in_process(test: Test) -> None:
    """Run one test in a child process."""
    test.run()


class SuiteParallelism(Enum):
    """Supported test execution strategies across devices."""

    REPEATED = "repeated"
    DISTRIBUTED = "distributed"
    ROLED = "roled"


@dataclass(frozen=True)
class SuiteOpts:
    """Validated suite execution options."""

    parallelism: SuiteParallelism | None = None
    jobs: int = 1

    def __post_init__(self) -> None:
        if type(self.jobs) is not int or self.jobs < 1:
            raise ValueError("Suite jobs must be a positive integer.")


class SuiteInputStrategy:
    """Construct a suite from one family of raw CLI input values."""

    @classmethod
    def matches(cls, test_inputs: Sequence[str]) -> bool:
        """Return whether this strategy handles the supplied test inputs."""
        raise NotImplementedError

    @classmethod
    def from_inputs(
        cls,
        test_inputs: Sequence[str],
        *,
        context: TestPathContext,
        exclude_test_selectors: Sequence[str],
        count: str | None,
        jobs: int = 1,
    ) -> "Suite":
        """Parse, validate, and construct a suite from raw input values."""
        raise NotImplementedError

    @staticmethod
    def _parse_count(raw_count: str) -> int:
        """Parse and validate a suite count."""
        try:
            count = int(raw_count)
        except ValueError as error:
            raise ValueError("Count must be a positive integer.") from error
        TestOpts._validate_count(count)
        return count


@dataclass(frozen=True)
class RoleSuiteInputs:
    """Validated role selectors and their optional execution counts."""

    selectors: dict[str, str]
    counts: dict[str, int]


class RoleSuiteInputStrategy(SuiteInputStrategy):
    """Construct suites from role-qualified test inputs."""

    @classmethod
    def matches(cls, test_inputs: Sequence[str]) -> bool:
        """Identify role input attempts before normal selector processing."""
        return any(cls._is_role_input(test_input) for test_input in test_inputs)

    @classmethod
    def from_inputs(
        cls,
        test_inputs: Sequence[str],
        *,
        context: TestPathContext,
        exclude_test_selectors: Sequence[str],
        count: str | None,
        jobs: int = 1,
    ) -> "Suite":
        """Create a role-based suite with per-role test options."""
        parsed_inputs = cls._parse_inputs(
            test_inputs,
            context=context,
            exclude_test_selectors=exclude_test_selectors,
            count=count,
        )

        tests: list[Test] = []
        for role, test_selector in parsed_inputs.selectors.items():
            role_tests = Test.from_inputs(
                (test_selector,),
                options=TestOpts(
                    role=role,
                    count=parsed_inputs.counts.get(role, 1),
                ),
                context=context,
            )
            tests.extend(role_tests)
        return Suite(SuiteOpts(SuiteParallelism.ROLED, jobs), tests)

    @classmethod
    def _parse_inputs(
        cls,
        test_inputs: Sequence[str],
        *,
        context: TestPathContext,
        exclude_test_selectors: Sequence[str],
        count: str | None,
    ) -> RoleSuiteInputs:
        """Parse and validate role selectors and optional counts."""
        cls._parse_invalid_ignore_arguments(exclude_test_selectors)
        role_inputs = cls._parse_role_selectors(test_inputs, context)
        role_counts = cls._parse_role_counts(count, list(role_inputs))
        return RoleSuiteInputs(role_inputs, role_counts)

    @staticmethod
    def _is_role_input(test_input: str) -> bool:
        """Return whether an input uses role-qualified syntax."""
        return "=" in test_input

    @staticmethod
    def _parse_invalid_ignore_arguments(
        exclude_test_selectors: Sequence[str],
    ) -> None:
        """Reject exclusions, which are unsupported for role-based tests."""
        if exclude_test_selectors:
            raise ValueError("Exclusions are not supported for role-based tests.")

    @classmethod
    def _parse_role_selectors(
        cls,
        test_inputs: Sequence[str],
        context: TestPathContext,
    ) -> dict[str, str]:
        """Parse and validate role-qualified test selectors.

        Every input must use the role-qualified form, ``role=test_selector``.
        The parser rejects mixed qualified and unqualified inputs, malformed
        role assignments, duplicate roles, and selectors containing patterns.
        """
        cls._require_role_qualified_inputs(test_inputs)
        role_inputs = cls._parse_unique_key_values(test_inputs)
        cls._validate_role_test_files(role_inputs, context)
        return role_inputs

    @staticmethod
    def _validate_role_test_files(
        role_inputs: dict[str, str],
        context: TestPathContext,
    ) -> None:
        """Require every role selector to resolve to exactly one file."""
        for role, test_selector in role_inputs.items():
            if has_magic(test_selector):
                raise ValueError(
                    f"Role '{role}' must reference one test file, not a pattern."
                )
            resolved_paths = TestPathResolver.resolve(test_selector, context)
            if (
                len(resolved_paths) != 1
                or not resolved_paths[0].absolute_path.is_file()
            ):
                raise ValueError(f"Role '{role}' must reference exactly one test file.")

    @classmethod
    def _require_role_qualified_inputs(cls, test_inputs: Sequence[str]) -> None:
        """Reject input collections containing unqualified selectors."""
        if not all(cls._is_role_input(test_input) for test_input in test_inputs):
            raise ValueError("Role-qualified and unqualified tests cannot be mixed.")

    @classmethod
    def _parse_role_counts(
        cls,
        count: str | None,
        roles: Sequence[str],
    ) -> dict[str, int]:
        """Parse and validate role count input.

        A single integer applies to every role. Comma-separated ``role=count``
        entries apply explicitly to those roles, with omitted roles defaulting
        to one. Mixed integer and role-qualified count syntax is rejected.
        """
        if not count:
            return {}

        count_inputs = tuple(value.strip() for value in count.split(","))
        has_role_counts = any("=" in value for value in count_inputs)
        if not has_role_counts:
            cls._validate_single_role_count(count_inputs)
            return cls._parse_uniform_role_count(count_inputs[0], roles)

        return cls._parse_explicit_role_counts(count_inputs, roles)

    @staticmethod
    def _validate_single_role_count(count_inputs: Sequence[str]) -> None:
        """Require exactly one value for uniform role count syntax."""
        if len(count_inputs) != 1:
            raise ValueError("Role-qualified inputs must use key=value format.")

    @classmethod
    def _parse_uniform_role_count(
        cls,
        raw_count: str,
        roles: Sequence[str],
    ) -> dict[str, int]:
        """Apply one integer count to every role."""
        parsed_count = cls._parse_count(raw_count)
        return {role: parsed_count for role in roles}

    @classmethod
    def _parse_explicit_role_counts(
        cls,
        count_inputs: Sequence[str],
        roles: Sequence[str],
    ) -> dict[str, int]:
        """Parse explicit role counts and validate their role assignments."""
        if any("=" not in value for value in count_inputs):
            raise ValueError("Role counts cannot mix integer and role=count values.")

        parsed_counts = cls._parse_unique_key_values(count_inputs)
        role_counts: dict[str, int] = {}
        for role, raw_count in parsed_counts.items():
            if role not in roles:
                raise ValueError(f"Unknown role '{role}' in count.")
            role_counts[role] = cls._parse_count(raw_count)
        return role_counts

    @staticmethod
    def _parse_unique_key_values(
        values: Sequence[str],
    ) -> dict[str, str]:
        """Parse unique non-empty ``key=value`` arguments."""
        parsed_values: dict[str, str] = {}
        for value in values:
            match = fullmatch(r"([^=]+)=([^=]+)", value.strip())
            if match is None:
                raise ValueError("Role-qualified inputs must use key=value format.")
            key, parsed_value = match.groups()
            if key in parsed_values:
                raise ValueError(f"Role '{key}' was provided more than once.")
            parsed_values[key] = parsed_value
        return parsed_values


class StandardSuiteInputStrategy(SuiteInputStrategy):
    """Construct suites from ordinary test selector inputs."""

    @classmethod
    def matches(cls, test_inputs: Sequence[str]) -> bool:
        """Provide the fallback strategy for ordinary selector inputs."""
        return True

    @classmethod
    def from_inputs(
        cls,
        test_inputs: Sequence[str],
        *,
        context: TestPathContext,
        exclude_test_selectors: Sequence[str],
        count: str | None,
        jobs: int = 1,
    ) -> "Suite":
        """Create a sequential or replicated suite from normal selectors."""
        parsed_count = cls._parse_count(count) if count else 1
        tests = Test.from_inputs(
            test_inputs,
            options=TestOpts(count=parsed_count),
            context=context,
            exclude_test_selectors=exclude_test_selectors,
        )
        parallelism = SuiteParallelism.REPEATED if parsed_count > 1 else None
        return Suite(SuiteOpts(parallelism, jobs), tests)


@dataclass
class Suite:
    """Run a collection of resolved tests in sequence."""

    options: SuiteOpts
    tests: Sequence[Test]

    @classmethod
    def from_inputs(
        cls,
        test_inputs: Sequence[str],
        *,
        context: TestPathContext | None = None,
        exclude: Sequence[str] = (),
        count: str | None = None,
        jobs: int = 1,
    ) -> "Suite":
        """Select an input strategy and construct an executable suite."""
        context = context or TestPathContext()
        for strategy in (RoleSuiteInputStrategy, StandardSuiteInputStrategy):
            if strategy.matches(test_inputs):
                return strategy.from_inputs(
                    test_inputs,
                    context=context,
                    exclude_test_selectors=exclude,
                    count=count,
                    jobs=jobs,
                )
        raise ValueError("No suite input strategy supports the supplied inputs.")

    def run(self) -> None:
        """Run the suite using the configured execution strategy."""
        self._runner_for(self.options.parallelism)()

    def _runner_for(
        self,
        parallelism: SuiteParallelism | None,
    ) -> Callable[[], None]:
        """Return the runner for a suite parallelism strategy."""
        runners = {
            None: self._run_sequential,
            SuiteParallelism.REPEATED: self._run_repeated,
            SuiteParallelism.DISTRIBUTED: self._run_distributed,
            SuiteParallelism.ROLED: self._run_roled,
        }
        return runners[parallelism]

    def _run_sequential(self) -> None:
        """Run each collected test in input order."""
        for test in self.tests:
            test.run()

    def _run_repeated(self) -> None:
        """Run each test in one child process per requested repeat."""
        processes = [
            Process(target=_run_test_in_process, args=(test,))
            for test in self.tests
            for _ in range(test.options.count)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join()
        if any(process.exitcode != 0 for process in processes):
            raise RuntimeError("One or more repeated tests failed.")

    def _run_distributed(self) -> None:
        """Distribute tests across available devices."""
        pass

    def _run_roled(self) -> None:
        """Run each role-assigned test in its own child process."""
        processes = [
            Process(target=_run_test_in_process, args=(test,))
            for test in self.tests
            for _ in range(test.options.count)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join()
        if any(process.exitcode != 0 for process in processes):
            raise RuntimeError("One or more role tests failed.")
