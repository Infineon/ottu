from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from multiprocessing import Process

from pydantic import BaseModel, ConfigDict, Field

from ottu.device import Device
from ottu.report import (
    QueueTestReportObserver,
    QueueTestReportRelay,
    SuiteReport,
    SuiteReportNotifier,
    TestReport,
    TestReportObserver,
)
from ottu.test import Test

DevicePool = dict[str | None, tuple[Device, ...]]


class RoleCount(BaseModel):
    """A repetition count for one test role."""

    model_config = ConfigDict(extra="forbid", strict=True)

    role: str = Field(min_length=1)
    count: int = Field(ge=1)


SuiteCount = int | tuple[RoleCount, ...]


@dataclass(frozen=True)
class SuiteOpts:
    """Validated suite execution options."""

    jobs: int = 1
    count: SuiteCount = 1

    def __post_init__(self) -> None:
        self._validate_jobs(self.jobs)
        self._validate_count(self.count)

    @property
    def suite_count(self) -> int:
        """The number of replicas of a test that has no role."""
        return self.count_for_role(None)

    def count_for_role(self, role: str | None) -> int:
        """Return the count for a role, falling back to one."""
        if isinstance(self.count, int):
            return self.count
        return next(
            (item.count for item in self.count if item.role == role),
            1,
        )

    @staticmethod
    def _validate_jobs(jobs: int) -> None:
        """Reject non-integer and non-positive job limits."""
        if type(jobs) is not int or jobs < 1:
            raise ValueError("Suite jobs must be a positive integer.")

    @staticmethod
    def _validate_count(count: SuiteCount) -> None:
        """Reject invalid suite-wide or role-specific counts."""
        if type(count) is int:
            if count < 1:
                raise ValueError("Suite count must be a positive integer.")
            return
        if not isinstance(count, tuple) or not count:
            raise ValueError("Suite count must be a positive integer or role counts.")
        if any(not isinstance(role_count, RoleCount) for role_count in count):
            raise TypeError("Suite role counts must be RoleCount values.")
        roles = [role_count.role for role_count in count]
        if len(roles) != len(set(roles)):
            raise ValueError("A role count was provided more than once.")


@dataclass
class Suite(ABC):
    """Run a collection of resolved tests.

    A suite owns the shared lifecycle (``run()``): book devices from the
    pool, acquire them, notify the observers with them, then run. Each
    execution mode is a subclass that provides the two mode-specific steps:

    - ``_book_devices()``: select the connected devices from the pool that
      the suite needs to run.
    - ``_runner(devices)``: assign the acquired devices to the tests in the
      way the mode requires, run them, and return their reports.

    The modes are:

    - ``SuiteSequential``: run each test one at a time, in order.
    - ``SuiteReplicated``: run each test in order, but the ``count`` replicas
      of a test (each on its own device) run concurrently as one group.
    - ``SuiteRole``: run every test concurrently, as one group (role suites,
      where every role must run together).
    - ``SuiteDistributed``: split tests across ``--jobs`` processes, each
      running its own slice sequentially or replicated.
    """

    name: str | None = None
    tests: Sequence[Test] = ()
    device_pool: DevicePool = field(default_factory=dict)
    options: SuiteOpts = field(default_factory=SuiteOpts)
    observers: tuple[TestReportObserver, ...] = ()

    def run(self) -> list[TestReport]:
        """Book and acquire the devices, announce the suite, then run it.

        The suite observers are notified once the devices are acquired and
        before the first test starts.
        """
        devices = [device.acquire() for device in self._book_devices()]
        SuiteReportNotifier(self.observers).notify(
            SuiteReport(
                self.name,
                tuple(devices),
                tuple(test.test_path for test in self.tests),
            )
        )
        return self._runner(devices)

    @abstractmethod
    def _book_devices(self) -> list[Device]:
        """Select the connected devices from the pool that this suite needs."""

    @abstractmethod
    def _runner(
        self,
        devices: Sequence[Device],
        observer: QueueTestReportObserver | None = None,
    ) -> list[TestReport]:
        """Assign the devices to the tests, run them, and return the reports."""

    @staticmethod
    def _run_test(
        test: Test, observer: QueueTestReportObserver | None = None
    ) -> TestReport:
        """Run one test, publishing its report through the observer if given."""
        if observer is not None:
            test = replace(test, observers=(observer,))
        return test.run()

    def _run_concurrently(
        self,
        tests: Sequence[Test],
        observer: QueueTestReportObserver | None = None,
    ) -> list[TestReport]:
        """Run every given test concurrently, as one group."""
        report_observers = tuple(
            dict.fromkeys(o for test in tests for o in test.observers)
        )
        event_queue = None if observer is None else observer.event_queue
        relay = QueueTestReportRelay(report_observers, event_queue=event_queue)
        processes = [
            Process(
                target=self._run_test,
                args=(test, QueueTestReportObserver(relay.event_queue)),
            )
            for test in tests
        ]
        return self._run_parallel_processes(
            processes,
            relay,
            live_drain=observer is None,
            failure_message="One or more test workers failed.",
        )

    @staticmethod
    def _run_parallel_processes(
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

    def _connected_candidates(
        self, role: str | None = None, excluded: Sequence[Device] = ()
    ) -> list[Device]:
        """Return the pool devices of a role that are free and connected."""
        return [
            device
            for device in self.device_pool.get(role, ())
            if device not in excluded and device.is_connected()
        ]

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


@dataclass
class SuiteSequential(Suite):
    """Run each test one at a time, in order, on a single device."""

    def _book_devices(self) -> list[Device]:
        """Select the first connected device of the pool."""
        candidates = self._connected_candidates()
        if not candidates:
            raise ValueError("Suite needs 1 connected devices, but only 0 matched.")
        return candidates[:1]

    def _runner(
        self,
        devices: Sequence[Device],
        observer: QueueTestReportObserver | None = None,
    ) -> list[TestReport]:
        """Run every test directly, in order, on the first device."""
        return [
            self._run_test(
                replace(test, device=devices[0]) if devices else test, observer
            )
            for test in self.tests
        ]


@dataclass
class SuiteReplicated(Suite):
    """Run each test in order, with its replicas concurrent on distinct devices.

    Every test expands into ``count`` replicas, each assigned its own device.
    The replicas of one test run together as a group, and the groups run one
    after another.
    """

    def _book_devices(self) -> list[Device]:
        """Select ``count`` connected devices of the pool."""
        count = self.options.suite_count
        candidates = self._connected_candidates()
        if len(candidates) < count:
            raise ValueError(
                f"Suite needs {count} connected devices, but only "
                f"{len(candidates)} matched."
            )
        return candidates[:count]

    def _runner(
        self,
        devices: Sequence[Device],
        observer: QueueTestReportObserver | None = None,
    ) -> list[TestReport]:
        """Run the replicas of each test concurrently, one test after another."""
        count = self.options.suite_count
        reports: list[TestReport] = []
        for test in self.tests:
            replicas = self._assign_devices((test,), devices, count)
            reports.extend(self._run_concurrently(replicas, observer))
        return reports


@dataclass
class SuiteRole(Suite):
    """Run every test concurrently, one group of devices per role.

    Each role gets its own ``count`` of connected devices, never shared with
    another role, and every test replica runs together as one group.
    """

    def _book_devices(self) -> list[Device]:
        """Select the connected devices of each role, never sharing them.

        The devices are listed role after role, in order of first appearance,
        so that ``_runner()`` can hand each role its own slice.
        """
        booked: list[Device] = []
        for role, count in self._role_counts().items():
            candidates = self._connected_candidates(role, booked)
            if len(candidates) < count:
                raise ValueError(
                    f"Role '{role}' needs {count} connected devices, "
                    f"but only {len(candidates)} matched."
                )
            booked.extend(candidates[:count])
        return booked

    def _runner(
        self,
        devices: Sequence[Device],
        observer: QueueTestReportObserver | None = None,
    ) -> list[TestReport]:
        """Pair each role's devices with its replicas and run them all together."""
        role_counts = self._role_counts()
        role_devices: dict[str, Sequence[Device]] = {}
        start = 0
        for role, count in role_counts.items():
            role_devices[role] = devices[start : start + count]
            start += count

        replicas = [
            replica
            for role, test in self._role_tests()
            for replica in self._assign_devices(
                (test,), role_devices[role], role_counts[role]
            )
        ]
        return self._run_concurrently(replicas, observer)

    def _role_tests(self) -> list[tuple[str, Test]]:
        """Pair each test with its role, requiring every test to have one."""
        pairs: list[tuple[str, Test]] = []
        for test in self.tests:
            role = test.options.role
            if role is None:
                raise ValueError("Role-based suite tests must have a role.")
            pairs.append((role, test))
        return pairs

    def _role_counts(self) -> dict[str, int]:
        """Return the device count of each role, in order of first appearance."""
        return {
            role: self.options.count_for_role(role) for role, _ in self._role_tests()
        }


@dataclass
class SuiteDistributed(Suite):
    """Split the tests across ``--jobs`` processes, each with its own devices.

    A job runs its slice sequentially, or replicated when ``count`` is above
    one. Each job reserves a disjoint group of ``count`` devices.
    """

    def _book_devices(self) -> list[Device]:
        """Select the connected devices that the jobs will share out."""
        required_count = self.options.suite_count * min(
            self.options.jobs, len(self.tests)
        )
        candidates = self._connected_candidates()
        if len(candidates) < required_count:
            raise ValueError(
                f"Suite needs {required_count} connected devices, but only "
                f"{len(candidates)} matched."
            )
        return candidates[:required_count]

    def _runner(
        self,
        devices: Sequence[Device],
        observer: QueueTestReportObserver | None = None,
    ) -> list[TestReport]:
        """Run each job in its own process, with its own group of devices."""
        suite_jobs = self._split(self.options.jobs, devices)
        if len(suite_jobs) == 1:
            suite_job, job_devices = suite_jobs[0]
            return suite_job._runner(job_devices, observer)

        observers = tuple(
            observer for test in self.tests for observer in test.observers
        )
        relay = QueueTestReportRelay(observers)
        job_observer = QueueTestReportObserver(relay.event_queue)
        processes = [
            Process(target=suite_job._runner, args=(job_devices, job_observer))
            for suite_job, job_devices in suite_jobs
        ]
        return self._run_parallel_processes(processes, relay)

    def _split(
        self, jobs: int, devices: Sequence[Device]
    ) -> list[tuple[Suite, Sequence[Device]]]:
        """Split tests and reserve a disjoint device group for each job."""
        if jobs == 1 or len(self.tests) <= 1:
            return [(self._job(list(self.tests)), devices)]

        job_count = min(jobs, len(self.tests))
        devices_per_job = self.options.suite_count
        required_devices = job_count * devices_per_job
        if len(devices) < required_devices and (
            devices or self.options.suite_count > 1
        ):
            raise ValueError(
                f"Distributed execution needs {required_devices} devices for "
                f"{job_count} jobs, but only {len(devices)} were "
                "provided."
            )

        base_size, remainder = divmod(len(self.tests), job_count)
        suite_jobs: list[tuple[Suite, Sequence[Device]]] = []
        start = 0
        for job_index in range(job_count):
            job_size = base_size + (job_index < remainder)
            chunk = list(self.tests[start : start + job_size])
            device_start = job_index * devices_per_job
            device_end = device_start + devices_per_job
            suite_jobs.append((self._job(chunk), devices[device_start:device_end]))
            start += job_size
        return suite_jobs

    def _job(self, tests: Sequence[Test]) -> Suite:
        """Return the part of this suite that one job runs."""
        suite_class = (
            SuiteReplicated if self.options.suite_count > 1 else SuiteSequential
        )
        return suite_class(tests=tests, options=self.options)
