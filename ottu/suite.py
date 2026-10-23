from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from glob import has_magic
from multiprocessing import Process
from pathlib import Path
from re import fullmatch
from typing import cast

from ottu.backend import Backend
from ottu.device import Device, DeviceQuery
from ottu.report import (
    QueueTestReportObserver,
    QueueTestReportRelay,
    TestReport,
    TestReportObserver,
)
from ottu.test import Test, TestOpts
from ottu.test_path import TestPathContext, TestPathResolver


@dataclass(frozen=True)
class SuiteOpts:
    """Validated suite execution options."""

    jobs: int = 1
    count: int = 1

    def __post_init__(self) -> None:
        self._validate_jobs(self.jobs)
        self._validate_count(self.count)

    @staticmethod
    def _validate_jobs(jobs: int) -> None:
        """Reject non-integer and non-positive job limits."""
        if type(jobs) is not int or jobs < 1:
            raise ValueError("Suite jobs must be a positive integer.")

    @staticmethod
    def _validate_count(count: int) -> None:
        """Reject non-integer and non-positive counts."""
        if type(count) is not int or count < 1:
            raise ValueError("Suite count must be a positive integer.")


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
        dev_list: Path | None = None,
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestReportObserver] = (),
    ) -> Suite:
        """Parse, validate, and construct a suite from raw input values."""
        raise NotImplementedError

    @staticmethod
    def _parse_count(raw_count: str) -> int:
        """Parse and validate a suite count."""
        try:
            count = int(raw_count)
        except ValueError as error:
            raise ValueError("Count must be a positive integer.") from error
        SuiteOpts._validate_count(count)
        return count

    @staticmethod
    def _assign_devices(
        base_tests: Sequence[Test],
        available_resolved_devices: Sequence[Device],
        required_count: int = 1,
    ) -> list[Test]:
        """Create one test for every test and device combination.

        A test that needs more than one replica is paired one-to-one with
        distinct devices when enough are supplied, so replicas never share
        a device.
        """
        tests: list[Test] = []
        available_resolved_devices = list(available_resolved_devices)

        for test in base_tests:
            if len(available_resolved_devices) < required_count:
                raise ValueError(
                    f"'{test.test_path.file_name}' needs {required_count} "
                    "devices for its count, but only "
                    f"{len(available_resolved_devices)} were provided."
                )

            for _ in range(required_count):
                device = (
                    available_resolved_devices.pop(0)
                    if available_resolved_devices
                    else None
                )
                tests.append(
                    Test(
                        test.test_path,
                        options=test.options,
                        device=device,
                        backend=test.backend,
                        observers=test.observers,
                    )
                )
        return tests

    @staticmethod
    def _resolve_devices(
        device_inputs: Sequence[str],
        available_devices: Path | Sequence[Device] | None,
    ) -> tuple[Device, ...]:
        """Resolve device definitions or queries from the supplied input.

        ``available_devices`` may be a path to a YAML device list or an already-loaded
        sequence of devices. The latter lets role suites resolve and reserve
        devices incrementally without reloading the full list for each role.
        When it is ``None``, each query is resolved directly with
        :meth:`Device.from_string`.
        """
        if available_devices is None:
            return SuiteInputStrategy._resolve_devices_from_definitions(device_inputs)

        available_resolved_devices = (
            Device.from_file(available_devices)
            if isinstance(available_devices, Path)
            else available_devices
        )
        return SuiteInputStrategy._resolve_devices_from_queries(
            device_inputs, available_resolved_devices
        )

    @staticmethod
    def _resolve_devices_from_definitions(
        device_definitions: Sequence[str],
    ) -> tuple[Device, ...]:
        """Resolve devices directly from their definitions."""
        if not device_definitions:
            # TODO: Resolve a default device supplied by the backend.
            raise ValueError("At least one device is required.")
        resolved_devices = tuple(
            Device.from_string(definition) for definition in device_definitions
        )
        return resolved_devices

    @staticmethod
    def _resolve_devices_from_queries(
        device_queries: Sequence[str],
        available_devices: Sequence[Device],
    ) -> tuple[Device, ...]:
        """Resolve queries by matching them against available devices."""
        matching_devices: list[Device] = []
        query_inputs = device_queries or (None,)
        for query in query_inputs:
            for device in DeviceQuery.find(available_devices, query):
                if device not in matching_devices:
                    matching_devices.append(device)
        return tuple(matching_devices)


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
        dev_list: Path | None = None,
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestReportObserver] = (),
    ) -> Suite:
        """Create a role-based suite with per-role test options."""
        parsed_inputs = cls._parse_inputs(
            test_inputs,
            context=context,
            exclude_test_selectors=exclude_test_selectors,
            count=count,
            devices=devices,
            jobs=jobs,
        )
        available_devices = (
            list(Device.from_file(dev_list)) if dev_list is not None else None
        )

        tests: list[Test] = []
        for role, test_selector in parsed_inputs.selectors.items():
            role_tests = Test.from_inputs(
                (test_selector,),
                options=TestOpts(role=role),
                context=context,
                backend=backend,
                observers=observers,
            )
            role_queries = parsed_inputs.devices.get(role, ())
            required_count = parsed_inputs.counts.get(role, 1)
            assigned_tests, available_devices = cls._resolve_and_assign_devices(
                role,
                role_tests[0],
                role_queries,
                available_devices,
                required_count,
            )
            tests.extend(assigned_tests)
        return Suite(
            SuiteOpts(jobs),
            tests,
            runner="runner_parallel",
        )

    @classmethod
    def _resolve_and_assign_devices(
        cls,
        role: str,
        role_test: Test,
        device_queries: Sequence[str],
        available_devices: Sequence[Device] | None,
        required_count: int,
    ) -> tuple[list[Test], list[Device] | None]:
        """Resolve, reserve, and assign the devices for one role."""
        role_devices = cls._resolve_device(
            role,
            device_queries,
            available_devices,
            required_count,
        )
        assigned_devices = role_devices[:required_count]
        remaining_devices = (
            [device for device in available_devices if device not in assigned_devices]
            if available_devices is not None
            else None
        )
        assigned_tests = cls._assign_devices(
            (role_test,),
            assigned_devices,
            required_count,
        )
        return assigned_tests, remaining_devices

    @classmethod
    def _resolve_device(
        cls,
        role: str,
        device_queries: Sequence[str],
        available_devices: Sequence[Device] | None,
        required_count: int,
    ) -> tuple[Device, ...]:
        """Resolve and validate the devices assigned to one role.

        Role qualifiers are removed before delegating to the shared resolver.
        ``available_devices`` contains only devices still available to this role;
        callers remove the returned devices afterward to prevent reuse by later
        roles.
        """
        if not device_queries:
            if available_devices is None:
                raise ValueError(f"Role '{role}' requires a device.")
            raise ValueError(
                f"Role '{role}' needs {required_count} connected devices, "
                "but only 0 matched."
            )

        normalized_queries = tuple(
            cls._remove_role(query, role) or "" for query in device_queries
        )
        if available_devices is None and len(normalized_queries) < required_count:
            raise ValueError(
                f"Role '{role}' needs {required_count} devices, "
                f"but only {len(normalized_queries)} were provided."
            )
        return SuiteInputStrategy._resolve_devices(
            normalized_queries,
            available_devices,
        )

    @staticmethod
    def _remove_role(device: str, role: str) -> str | None:
        """Remove the role qualifier before matching a device definition."""
        parameters = [part.strip() for part in device.split(",")]
        parameters = [part for part in parameters if part != f"role={role}"]
        return ",".join(parameters) or None

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
        dev_list: Path | None = None,
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestReportObserver] = (),
    ) -> Suite:
        """Create a sequential, repeated, or distributed suite from selectors."""
        parsed_count = cls._parse_count(count) if count else 1
        tests = Test.from_inputs(
            test_inputs,
            context=context,
            exclude_test_selectors=exclude_test_selectors,
            backend=backend,
            observers=observers,
        )
        options = SuiteOpts(jobs, parsed_count)
        resolved_devices = cls._resolve_devices(devices, dev_list)
        return Suite(
            options,
            tests,
            runner=cls._select_runner(options),
            resolved_devices=resolved_devices,
        )

    @staticmethod
    def _select_runner(options: SuiteOpts) -> str:
        """Pick the runner name for the given execution options."""
        if options.jobs > 1:
            return "runner_distributed"
        if options.count > 1:
            return "runner_repeated"
        return "runner_sequential"


@dataclass
class Suite:
    """Run a collection of resolved tests.

    ``runner`` names the method ``run()`` dispatches to:

    - ``runner_sequential``: run each test one at a time, in order.
    - ``runner_repeated``: run each test in order, but tests sharing a
      file (a repeated ``--count``, or replicas paired with devices) run
      concurrently as one group.
    - ``runner_parallel``: run every test in this suite concurrently, as
      one group (role suites, where every role must run together).
    - ``runner_distributed``: split tests across ``--jobs`` processes,
      each running its own slice sequentially or repeated.
    """

    options: SuiteOpts
    tests: Sequence[Test]
    runner: str = ""
    resolved_devices: Sequence[Device] = ()

    @classmethod
    def from_inputs(
        cls,
        test_inputs: Sequence[str],
        *,
        context: TestPathContext | None = None,
        exclude: Sequence[str] = (),
        count: str | None = None,
        devices: Sequence[str] = (),
        dev_list: Path | None = None,
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestReportObserver] = (),
    ) -> Suite:
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
                    dev_list=dev_list,
                    jobs=jobs,
                    backend=backend,
                    observers=observers,
                )
        raise ValueError("No suite input strategy supports the supplied inputs.")

    def run(self) -> list[TestReport]:
        """Run the suite using whichever runner its strategy selected."""
        runner = cast(Callable[[], list[TestReport]], getattr(self, self.runner))
        return runner()

    def runner_sequential(
        self, observer: QueueTestReportObserver | None = None
    ) -> list[TestReport]:
        """Run each test directly, one at a time, in order.

        The first resolved device is assigned to every test in this process.
        """
        device = self.resolved_devices[0] if self.resolved_devices else None
        return [
            self._run_test(
                replace(test, device=device) if device is not None else test,
                observer,
            )
            for test in self.tests
        ]

    def runner_repeated(
        self, observer: QueueTestReportObserver | None = None
    ) -> list[TestReport]:
        """Expand and run each base test's ``count`` replicas in parallel."""
        reports: list[TestReport] = []
        for test in self.tests:
            repeated_tests = SuiteInputStrategy._assign_devices(
                (test,),
                self.resolved_devices,
                self.options.count,
            )
            reports.extend(
                Suite(
                    self.options,
                    repeated_tests,
                    runner="runner_parallel",
                ).runner_parallel(observer)
            )
        return reports

    def runner_parallel(
        self, observer: QueueTestReportObserver | None = None
    ) -> list[TestReport]:
        """Run every test in this suite concurrently, as one group."""
        report_observers = tuple(
            dict.fromkeys(o for test in self.tests for o in test.observers)
        )
        event_queue = None if observer is None else observer.event_queue
        relay = QueueTestReportRelay(report_observers, event_queue=event_queue)
        processes = [
            Process(
                target=self._run_test,
                args=(
                    test,
                    QueueTestReportObserver(relay.event_queue, job_id),
                ),
            )
            for test, job_id in self._replica_targets(self.tests)
        ]
        return self.run_parallel_processes(
            processes,
            relay,
            live_drain=observer is None,
            failure_message="One or more test workers failed.",
        )

    def runner_distributed(self) -> list[TestReport]:
        """Split this suite across jobs, each running in its own process."""
        distributed_suites = self.split(self.options.jobs)
        if len(distributed_suites) == 1:
            return distributed_suites[0].run()

        observers = tuple(
            observer for test in self.tests for observer in test.observers
        )
        relay = QueueTestReportRelay(observers)
        observer = QueueTestReportObserver(relay.event_queue)
        processes = [
            Process(target=getattr(suite_job, suite_job.runner), args=(observer,))
            for suite_job in distributed_suites
        ]
        return self.run_parallel_processes(processes, relay)

    @staticmethod
    def _run_test(
        test: Test, observer: QueueTestReportObserver | None = None
    ) -> TestReport:
        """Run one test, publishing its report through the observer if given."""
        if observer is not None:
            test = replace(test, observers=(observer,))
        return test.run()

    @staticmethod
    def _replica_targets(tests: Sequence[Test]) -> list[tuple[Test, str]]:
        """Pair each test in a group with its job id."""
        counters: dict[str, int] = {}
        targets: list[tuple[Test, str]] = []
        for test in tests:
            file_name = test.test_path.file_name
            counters[file_name] = counters.get(file_name, 0) + 1
            targets.append((test, str(counters[file_name])))
        return targets

    def split(self, jobs: int) -> list[Suite]:
        """Split tests and reserve a disjoint device group for each job."""
        runner = StandardSuiteInputStrategy._select_runner(
            replace(self.options, jobs=1)
        )
        if jobs == 1 or len(self.tests) <= 1:
            return [
                Suite(
                    self.options,
                    list(self.tests),
                    runner=runner,
                    resolved_devices=self.resolved_devices,
                )
            ]

        job_count = min(jobs, len(self.tests))
        devices_per_job = self.options.count
        required_devices = job_count * devices_per_job
        if len(self.resolved_devices) < required_devices and (
            self.resolved_devices or self.options.count > 1
        ):
            raise ValueError(
                f"Distributed execution needs {required_devices} devices for "
                f"{job_count} jobs, but only {len(self.resolved_devices)} were "
                "provided."
            )

        base_size, remainder = divmod(len(self.tests), job_count)
        suite_jobs: list[Suite] = []
        start = 0
        for job_index in range(job_count):
            job_size = base_size + (job_index < remainder)
            chunk = list(self.tests[start : start + job_size])
            device_start = job_index * devices_per_job
            device_end = device_start + devices_per_job
            suite_jobs.append(
                Suite(
                    self.options,
                    chunk,
                    runner=runner,
                    resolved_devices=self.resolved_devices[device_start:device_end],
                )
            )
            start += job_size
        return suite_jobs

    @staticmethod
    def run_parallel_processes(
        processes: list[Process],
        relay: QueueTestReportRelay,
        *,
        live_drain: bool = True,
        failure_message: str = "One or more jobs failed.",
    ) -> list[TestReport]:
        reports: list[TestReport] = []
        for process in processes:
            relay.register_process(process)
        for process in processes:
            process.start()
        if live_drain:
            while relay.processes_running:
                reports.extend(relay.forward())
        for process in processes:
            process.join()
        # Nested workers must not forward: the queue is shared with an
        # ancestor that owns it and is already draining it.
        if live_drain:
            reports.extend(relay.forward())
        if any(process.exitcode != 0 for process in processes):
            raise RuntimeError(failure_message)
        return reports
