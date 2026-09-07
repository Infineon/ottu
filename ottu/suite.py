from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from glob import has_magic
from multiprocessing import Process
from pathlib import Path
from re import fullmatch

from ottu.test import Test


def _run_test_in_process(test: Test) -> None:
    """Run one test in a child process."""
    test.run()


class SuiteParallelism(Enum):
    """Supported test execution strategies across devices."""

    REPLICATED = "replicated"
    DISTRIBUTED = "distributed"
    ROLED = "roled"


@dataclass
class SuiteOpts:
    parallelism: SuiteParallelism | None = None


@dataclass
class Suite:
    """Run a collection of resolved tests in sequence."""

    options: SuiteOpts
    tests: Sequence[Test]

    @staticmethod
    def _classify_test_inputs(
        test_inputs: Sequence[str],
    ) -> tuple[SuiteParallelism | None, tuple[tuple[str | None, str], ...]]:
        """Classify role-qualified inputs and determine suite parallelism."""
        role_inputs: dict[str, str] = {}
        plain_inputs: list[str] = []

        for test_input in test_inputs:
            role_match = fullmatch(r"([^=]+)=(.+)", test_input)
            if role_match is None:
                plain_inputs.append(test_input)
                continue

            role, test_path = role_match.groups()
            if role in role_inputs:
                raise ValueError(f"Role '{role}' was provided more than once.")
            role_inputs[role] = test_path

        if role_inputs and plain_inputs:
            raise ValueError(
                "Multi-role inputs cannot be mixed with unqualified tests."
            )

        parallelism = SuiteParallelism.ROLED if role_inputs else None
        parsed_inputs = (
            tuple((role, test_path) for role, test_path in role_inputs.items())
            if role_inputs
            else tuple((None, test_path) for test_path in plain_inputs)
        )
        return parallelism, parsed_inputs

    @classmethod
    def _create_tests(
        cls,
        classified_inputs: tuple[tuple[str | None, str], ...],
        *,
        counts: Sequence[str] = (),
        working_dir: str | Path | None = None,
        project_root: str | Path | None = None,
        tests_dir: str | Path | None = None,
        pattern: str = "**/*",
        exclude: Sequence[str] = (),
    ) -> list[Test]:
        """Create role-aware tests from classified inputs."""
        count_by_role, replicated_count = cls._classify_counts(
            classified_inputs, counts
        )
        if not classified_inputs:
            return Test.from_inputs(
                (),
                count=replicated_count,
                working_dir=working_dir,
                project_root=project_root,
                tests_dir=tests_dir,
                pattern=pattern,
                exclude=exclude,
            )

        tests: list[Test] = []
        for role, test_input in classified_inputs:
            if role is not None and has_magic(test_input):
                raise ValueError(
                    f"Role '{role}' must reference one test file, not a pattern."
                )

            role_tests = Test.from_inputs(
                (test_input,),
                role=role,
                count=count_by_role.get(role, replicated_count),
                working_dir=working_dir,
                project_root=project_root,
                tests_dir=tests_dir,
                pattern=pattern,
                exclude=exclude,
            )
            if role is not None and (
                len(role_tests) != 1
                or not role_tests[0].test_path.absolute_path.is_file()
            ):
                raise ValueError(f"Role '{role}' must reference exactly one test file.")
            tests.extend(role_tests)
        return tests

    @classmethod
    def from_inputs(
        cls,
        test_inputs: Sequence[str],
        *,
        working_dir: str | Path | None = None,
        project_root: str | Path | None = None,
        tests_dir: str | Path | None = None,
        pattern: str = "**/*",
        exclude: Sequence[str] = (),
        counts: Sequence[str] = (),
    ) -> "Suite":
        """Resolve CLI test inputs and create an executable suite."""
        parallelism, classified_inputs = cls._classify_test_inputs(test_inputs)
        tests = cls._create_tests(
            classified_inputs,
            counts=counts,
            working_dir=working_dir,
            project_root=project_root,
            tests_dir=tests_dir,
            pattern=pattern,
            exclude=exclude,
        )
        if counts and (not classified_inputs or classified_inputs[0][0] is None):
            parallelism = SuiteParallelism.REPLICATED
        return cls(
            options=SuiteOpts(parallelism=parallelism),
            tests=tests,
        )

    @staticmethod
    def _classify_counts(
        classified_inputs: tuple[tuple[str | None, str], ...],
        counts: Sequence[str],
    ) -> tuple[dict[str | None, int], int]:
        """Validate count selectors and return role and replicated counts."""
        if not counts:
            return {}, 1

        has_roles = bool(classified_inputs and classified_inputs[0][0] is not None)
        if not has_roles:
            if len(counts) != 1 or "=" in counts[0]:
                raise ValueError(
                    "Only one numeric count is allowed for replicated tests."
                )
            try:
                replicated_count = int(counts[0])
            except ValueError as error:
                raise ValueError("Count must be a positive integer.") from error
            if replicated_count < 1:
                raise ValueError("Count must be a positive integer.")
            return {}, replicated_count

        count_by_role: dict[str | None, int] = {}
        roles = {role for role, _ in classified_inputs}
        for count_input in counts:
            if "=" not in count_input:
                raise ValueError("Role counts must use the role=count format.")
            role, raw_count = count_input.split("=", 1)
            if role not in roles:
                raise ValueError(f"Unknown role '{role}' in count.")
            if role in count_by_role:
                raise ValueError(f"Role '{role}' count was provided more than once.")
            try:
                count = int(raw_count)
            except ValueError as error:
                raise ValueError("Count must be a positive integer.") from error
            if count < 1:
                raise ValueError("Count must be a positive integer.")
            count_by_role[role] = count
        return count_by_role, 1

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
            SuiteParallelism.REPLICATED: self._run_replicated,
            SuiteParallelism.DISTRIBUTED: self._run_distributed,
            SuiteParallelism.ROLED: self._run_roled,
        }
        return runners[parallelism]

    def _run_sequential(self) -> None:
        """Run each collected test in input order."""
        for test in self.tests:
            test.run()

    def _run_replicated(self) -> None:
        """Run each test in one child process per requested replica."""
        processes = [
            Process(target=_run_test_in_process, args=(test,))
            for test in self.tests
            for _ in range(test.count)
        ]

        for process in processes:
            process.start()

        for process in processes:
            process.join()

        failed = [process for process in processes if process.exitcode != 0]
        if failed:
            raise RuntimeError("One or more replicated tests failed.")

    def _run_distributed(self) -> None:
        """Distribute tests across available devices."""
        pass

    def _run_roled(self) -> None:
        """Run each role-assigned test in its own child process."""
        processes = [
            Process(target=_run_test_in_process, args=(test,))
            for test in self.tests
            for _ in range(test.count)
        ]

        for process in processes:
            process.start()

        for process in processes:
            process.join()

        failed = [process for process in processes if process.exitcode != 0]
        if failed:
            raise RuntimeError("One or more role tests failed.")
