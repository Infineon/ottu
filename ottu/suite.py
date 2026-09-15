from collections.abc import Sequence
from dataclasses import dataclass
from glob import has_magic
from multiprocessing import Process
from re import fullmatch

from ottu.backend import Backend
from ottu.result import TestResult, TestResultObserver
from ottu.test import Test, TestOpts, TestPathContext, TestPathResolver


@dataclass(frozen=True)
class SuiteOpts:
    """Validated suite execution options."""

    jobs: int = 1

    def __post_init__(self) -> None:
        self._validate_jobs(self.jobs)

    @staticmethod
    def _validate_jobs(jobs: int) -> None:
        """Reject non-integer and non-positive job limits."""
        if type(jobs) is not int or jobs < 1:
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
        devices: Sequence[str] = (),
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestResultObserver] = (),
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

    @staticmethod
    def _assign_devices(tests: Sequence[Test], devices: Sequence[str]) -> list[Test]:
        """Create one test for every test and device combination."""
        if not devices:
            return list(tests)

        return [
            Test(
                test.test_path,
                options=test.options,
                device=device,
                backend=test.backend,
                observers=test.observers,
            )
            for test in tests
            for device in devices
        ]


@dataclass(frozen=True)
class RoleSuiteInputs:
    """Validated role selectors and their optional execution counts."""

    selectors: dict[str, str]
    counts: dict[str, int]
    devices: dict[str, tuple[str, ...]]


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
        devices: Sequence[str] = (),
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestResultObserver] = (),
    ) -> "Suite":
        """Create a role-based suite with per-role test options."""
        parsed_inputs = cls._parse_inputs(
            test_inputs,
            context=context,
            exclude_test_selectors=exclude_test_selectors,
            count=count,
            devices=devices,
            jobs=jobs,
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
                backend=backend,
                observers=observers,
            )
            tests.extend(
                cls._assign_devices(role_tests, parsed_inputs.devices.get(role, ()))
            )
        return Suite(SuiteOpts(jobs), tests)

    @classmethod
    def _parse_role_devices(
        cls,
        devices: Sequence[str],
        roles: Sequence[str],
    ) -> dict[str, tuple[str, ...]]:
        """Route device queries to roles or broadcast one query to all roles."""
        if not devices:
            return {}
        device_roles = {device: cls._device_roles(device, roles) for device in devices}
        if len(devices) == 1 and not device_roles[devices[0]]:
            return {role: tuple(devices) for role in roles}

        role_devices: dict[str, str] = {}
        for device in devices:
            matching_roles = device_roles[device]
            if not matching_roles:
                raise ValueError(
                    "Role-qualified device queries cannot be mixed with unqualified "
                    "queries."
                )
            if len(matching_roles) > 1:
                roles_text = ", ".join(matching_roles)
                raise ValueError(
                    f"Device query matches more than one role: {roles_text}."
                )
            device_role = matching_roles[0]
            if device_role in role_devices:
                raise ValueError(
                    f"Device query for role '{device_role}' was provided "
                    "more than once."
                )
            if device_role not in roles:
                raise ValueError(f"Unknown role '{device_role}' in device query.")
            role_devices[device_role] = device

        missing_roles = set(roles) - set(role_devices)
        if missing_roles:
            missing = ", ".join(sorted(missing_roles))
            raise ValueError(f"Missing device query for role(s): {missing}.")
        return {role: (role_devices[role],) for role in roles}

    @classmethod
    def _device_roles(
        cls,
        device: str,
        roles: Sequence[str],
    ) -> tuple[str, ...]:
        """Extract the explicitly qualified role from a device query."""
        if "=" not in device:
            return ()

        device_parameters = cls._parse_unique_key_values(
            tuple(parameter.strip() for parameter in device.split(","))
        )
        device_role = device_parameters.get("role")
        return (device_role,) if device_role is not None else ()

    @classmethod
    def _parse_inputs(
        cls,
        test_inputs: Sequence[str],
        *,
        context: TestPathContext,
        exclude_test_selectors: Sequence[str],
        count: str | None,
        devices: Sequence[str],
        jobs: int,
    ) -> RoleSuiteInputs:
        """Parse and validate role selectors and optional counts."""
        cls._parse_invalid_ignore_arguments(exclude_test_selectors, jobs)
        role_inputs = cls._parse_role_selectors(test_inputs, context)
        role_counts = cls._parse_role_counts(count, list(role_inputs))
        role_devices = cls._parse_role_devices(devices, list(role_inputs))
        return RoleSuiteInputs(role_inputs, role_counts, role_devices)

    @staticmethod
    def _is_role_input(test_input: str) -> bool:
        """Return whether an input uses role-qualified syntax."""
        return "=" in test_input

    @staticmethod
    def _parse_invalid_ignore_arguments(
        exclude_test_selectors: Sequence[str],
        jobs: int,
    ) -> None:
        """Reject arguments that are unsupported for role-based tests."""
        if exclude_test_selectors:
            raise ValueError("Exclusions are not supported for role-based tests.")
        if jobs != 1:
            raise ValueError("Jobs are not supported for role-based tests.")

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
        devices: Sequence[str] = (),
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestResultObserver] = (),
    ) -> "Suite":
        """Create a sequential or replicated suite from normal selectors."""
        parsed_count = cls._parse_count(count) if count else 1
        tests = Test.from_inputs(
            test_inputs,
            options=TestOpts(count=parsed_count),
            context=context,
            exclude_test_selectors=exclude_test_selectors,
            backend=backend,
            observers=observers,
        )
        tests = cls._assign_devices(tests, devices)
        return Suite(SuiteOpts(jobs), tests)


@dataclass(frozen=True)
class SuiteJob:
    """Run one group of tests within a suite job."""

    tests: Sequence[Test]

    def run(self) -> list[TestResult]:
        """Run each test, creating workers for role or repeated tests."""
        results: list[TestResult] = []
        for test in self.tests:
            if test.options.role is not None or test.options.count > 1:
                self._run_test_workers(test)
            else:
                results.append(test.run())
        return results

    @classmethod
    def split(cls, tests: Sequence[Test], jobs: int) -> list["SuiteJob"]:
        """Split tests into contiguous suite jobs."""
        if jobs == 1 or len(tests) <= 1:
            return [cls(list(tests))]

        job_count = min(jobs, len(tests))
        base_size, remainder = divmod(len(tests), job_count)
        suite_jobs: list[SuiteJob] = []
        start = 0
        for job_index in range(job_count):
            job_size = base_size + (job_index < remainder)
            suite_jobs.append(cls(list(tests[start : start + job_size])))
            start += job_size
        return suite_jobs

    @staticmethod
    def _run_test_in_process(test: Test) -> None:
        """Run one test in a child process."""
        test.run()

    @classmethod
    def _run_test_workers(cls, test: Test) -> None:
        """Run one worker per requested test replica."""
        processes = [
            Process(target=cls._run_test_in_process, args=(test,))
            for _ in range(test.options.count)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join()
        if any(process.exitcode != 0 for process in processes):
            raise RuntimeError("One or more test workers failed.")


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
        devices: Sequence[str] = (),
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestResultObserver] = (),
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
                    devices=devices,
                    jobs=jobs,
                    backend=backend,
                    observers=observers,
                )
        raise ValueError("No suite input strategy supports the supplied inputs.")

    def run(self) -> list[TestResult]:
        """Run the suite through the job and test worker layers."""
        suite_jobs = SuiteJob.split(self.tests, self.options.jobs)
        if len(suite_jobs) == 1:
            return suite_jobs[0].run()

        processes = [
            Process(target=SuiteJob.run, args=(suite_job,)) for suite_job in suite_jobs
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join()
        if any(process.exitcode != 0 for process in processes):
            raise RuntimeError("One or more jobs failed.")
        return []
