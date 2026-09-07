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
        working_dir: str | Path | None = None,
        project_root: str | Path | None = None,
        tests_dir: str | Path | None = None,
        pattern: str = "**/*",
        exclude: Sequence[str] = (),
    ) -> list[Test]:
        """Create role-aware tests from classified inputs."""
        if not classified_inputs:
            return Test.from_inputs(
                (),
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
    ) -> "Suite":
        """Resolve CLI test inputs and create an executable suite."""
        parallelism, classified_inputs = cls._classify_test_inputs(test_inputs)
        tests = cls._create_tests(
            classified_inputs,
            working_dir=working_dir,
            project_root=project_root,
            tests_dir=tests_dir,
            pattern=pattern,
            exclude=exclude,
        )
        return cls(
            options=SuiteOpts(parallelism=parallelism),
            tests=tests,
        )

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
        """Run the same tests on each available device."""
        pass

    def _run_distributed(self) -> None:
        """Distribute tests across available devices."""
        pass

    def _run_roled(self) -> None:
        """Run each role-assigned test in its own child process."""
        processes = [
            Process(target=_run_test_in_process, args=(test,)) for test in self.tests
        ]

        for process in processes:
            process.start()

        for process in processes:
            process.join()

        failed = [process for process in processes if process.exitcode != 0]
        if failed:
            raise RuntimeError("One or more role tests failed.")
