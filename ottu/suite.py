from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from glob import has_magic
from multiprocessing import Process
from pathlib import Path
from re import fullmatch

from ottu.test import Test, TestOpts


def _run_test_in_process(test: Test) -> None:
    """Run one test in a child process."""
    test.run()


class SuiteParallelism(Enum):
    """Supported test execution strategies across devices."""

    REPLICATED = "replicated"
    DISTRIBUTED = "distributed"
    ROLED = "roled"


@dataclass(frozen=True)
class SuiteOpts:
    """Validated suite options and input-specific test options."""

    parallelism: SuiteParallelism | None = None
    inputs: tuple[tuple[str, TestOpts], ...] = ()
    default_test_options: TestOpts = TestOpts()

    @classmethod
    def from_inputs(
        cls,
        test_inputs: Sequence[str],
        counts: Sequence[str] = (),
    ) -> "SuiteOpts":
        """Parse and validate suite inputs and their test options."""
        role_inputs: dict[str, str] = {}
        plain_inputs: list[str] = []

        for test_input in test_inputs:
            role_match = fullmatch(r"([^=]+)=([^=]+)", test_input)
            if role_match is None:
                if "=" in test_input:
                    raise ValueError("Role-qualified inputs must use key=value format.")
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

        if role_inputs:
            role_counts = cls._classify_role_counts(role_inputs, counts)
            inputs = tuple(
                (
                    test_path,
                    TestOpts(role=role, count=role_counts.get(role, 1)),
                )
                for role, test_path in role_inputs.items()
            )
            return cls(SuiteParallelism.ROLED, inputs)

        count = cls._classify_replicated_count(counts)
        test_options = TestOpts(count=count)
        inputs = tuple((test_input, test_options) for test_input in plain_inputs)
        parallelism = SuiteParallelism.REPLICATED if counts else None
        return cls(parallelism, inputs, test_options)

    @staticmethod
    def _classify_replicated_count(counts: Sequence[str]) -> int:
        """Validate the single count allowed for replicated inputs."""
        if not counts:
            return 1
        if len(counts) != 1 or "=" in counts[0]:
            raise ValueError("Only one numeric count is allowed for replicated tests.")
        try:
            count = int(counts[0])
        except ValueError as error:
            raise ValueError("Count must be a positive integer.") from error
        if count < 1:
            raise ValueError("Count must be a positive integer.")
        return count

    @staticmethod
    def _classify_role_counts(
        role_inputs: dict[str, str], counts: Sequence[str]
    ) -> dict[str, int]:
        """Validate counts assigned to role-qualified inputs."""
        role_counts: dict[str, int] = {}
        for count_input in counts:
            count_match = fullmatch(r"([^=]+)=([^=]+)", count_input)
            if count_match is None:
                raise ValueError("Role counts must use the role=count format.")
            role, raw_count = count_match.groups()
            if role not in role_inputs:
                raise ValueError(f"Unknown role '{role}' in count.")
            if role in role_counts:
                raise ValueError(f"Role '{role}' count was provided more than once.")
            try:
                count = int(raw_count)
            except ValueError as error:
                raise ValueError("Count must be a positive integer.") from error
            if count < 1:
                raise ValueError("Count must be a positive integer.")
            role_counts[role] = count
        return role_counts


@dataclass
class Suite:
    """Run a collection of resolved tests in sequence."""

    options: SuiteOpts
    tests: Sequence[Test]

    @classmethod
    def _create_tests(
        cls,
        options: SuiteOpts,
        *,
        working_dir: str | Path | None = None,
        project_root: str | Path | None = None,
        tests_dir: str | Path | None = None,
        pattern: str = "**/*",
        exclude: Sequence[str] = (),
    ) -> list[Test]:
        """Resolve SuiteOpts inputs into tests."""
        if not options.inputs:
            return Test.from_inputs(
                (),
                options=options.default_test_options,
                working_dir=working_dir,
                project_root=project_root,
                tests_dir=tests_dir,
                pattern=pattern,
                exclude=exclude,
            )

        tests: list[Test] = []
        for test_input, test_options in options.inputs:
            if test_options.role is not None and has_magic(test_input):
                raise ValueError(
                    f"Role '{test_options.role}' must reference one test file, "
                    "not a pattern."
                )

            role_tests = Test.from_inputs(
                (test_input,),
                options=test_options,
                working_dir=working_dir,
                project_root=project_root,
                tests_dir=tests_dir,
                pattern=pattern,
                exclude=exclude,
            )
            if test_options.role is not None and (
                len(role_tests) != 1
                or not role_tests[0].test_path.absolute_path.is_file()
            ):
                raise ValueError(
                    f"Role '{test_options.role}' must reference exactly one test file."
                )
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
        """Resolve CLI inputs and create an executable suite."""
        options = SuiteOpts.from_inputs(test_inputs, counts)
        tests = cls._create_tests(
            options,
            working_dir=working_dir,
            project_root=project_root,
            tests_dir=tests_dir,
            pattern=pattern,
            exclude=exclude,
        )
        return cls(options=options, tests=tests)

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
            for _ in range(test.options.count)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join()
        if any(process.exitcode != 0 for process in processes):
            raise RuntimeError("One or more replicated tests failed.")

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
