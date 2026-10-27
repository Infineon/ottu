"""Select and build the suites of a test plan."""

from collections.abc import Mapping, Sequence
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from ottu.backend import Backend
from ottu.config_models.plan.plan import PlanConfig, RoleTest, SuiteDefinition
from ottu.device import DeviceFilter, DeviceQuery
from ottu.report import TestReportObserver
from ottu.suite import Suite
from ottu.test_path import TestPathContext


class Plan:
    """A loaded test plan whose suites can be selected and built."""

    def __init__(self, suites: Sequence[SuiteDefinition]) -> None:
        self.suites = tuple(suites)

    @classmethod
    def from_file(cls, path: str | Path) -> "Plan":
        """Load and validate a plan file."""
        return cls(PlanConfig.from_file(path).suites)

    def select(
        self,
        selectors: Sequence[str] = (),
        exclude: Sequence[str] = (),
    ) -> list[SuiteDefinition]:
        """Return the suites whose names match the selectors, in plan order.

        Selectors and exclusions are glob patterns matched against suite
        names. Without selectors every suite is selected, including unnamed
        ones. Unnamed suites never match a selector or an exclusion.
        """
        for selector in selectors:
            if not any(self._matches(suite, (selector,)) for suite in self.suites):
                raise ValueError(f"No suite in the plan matches '{selector}'.")
        return [
            suite
            for suite in self.suites
            if (not selectors or self._matches(suite, selectors))
            and not self._matches(suite, exclude)
        ]

    def build_suites(
        self,
        selected: Sequence[SuiteDefinition],
        *,
        context: TestPathContext,
        devices: Sequence[str] = (),
        dev_list: Path | None = None,
        backend: Backend | None = None,
        observers: Sequence[TestReportObserver] = (),
    ) -> list[Suite]:
        """Build one executable suite for every selected plan suite.

        ``devices`` are the ``--device`` values. With a device list they are
        queries combined (AND) with the suite's ``requires.device``; without
        one they are the devices to run on, as given.
        """
        return [
            self._build_suite(
                suite,
                context=context,
                devices=devices,
                dev_list=dev_list,
                backend=backend,
                observers=observers,
            )
            for suite in selected
        ]

    @classmethod
    def _build_suite(
        cls,
        suite: SuiteDefinition,
        *,
        context: TestPathContext,
        devices: Sequence[str],
        dev_list: Path | None,
        backend: Backend | None,
        observers: Sequence[TestReportObserver],
    ) -> Suite:
        """Translate one plan suite into an executable suite."""
        device_filters = cls._device_filters(suite.requires.device, devices, dev_list)
        role_tests = [test for test in suite.tests if isinstance(test, RoleTest)]
        if role_tests:
            return Suite.from_roles(
                {test.role: test.test for test in role_tests},
                counts={test.role: test.count for test in role_tests},
                devices=device_filters,
                context=context,
                dev_list=dev_list,
                backend=backend,
                observers=observers,
            )
        return Suite.from_inputs(
            [test for test in suite.tests if isinstance(test, str)],
            context=context,
            exclude=suite.exclude,
            count=str(suite.count) if suite.count is not None else None,
            devices=device_filters,
            dev_list=dev_list,
            backend=backend,
            observers=observers,
        )

    @staticmethod
    def _matches(suite: SuiteDefinition, patterns: Sequence[str]) -> bool:
        """Return whether the suite name matches any of the glob patterns."""
        return suite.name is not None and any(
            fnmatchcase(suite.name, pattern) for pattern in patterns
        )

    @staticmethod
    def _device_filters(
        required: Sequence[Mapping[str, Any]],
        devices: Sequence[str],
        dev_list: Path | None,
    ) -> list[DeviceFilter]:
        """Return the device filters of a suite.

        Without ``--device`` values these are the suite's ``requires.device``
        entries. With a device list, every ``--device`` query is combined (AND)
        with every entry; contradicting pairs are dropped and at least one
        pair must remain. Without a device list, or without entries, the
        ``--device`` values are used as given.
        """
        if not devices:
            return [*required]
        if dev_list is None or not required:
            return [*devices]

        queries = [
            filter_ for device in devices for filter_ in DeviceQuery.parse(device)
        ]
        combined_filters: list[DeviceFilter] = [
            combined
            for entry in required
            for query in queries
            if (combined := DeviceQuery.combine(entry, query)) is not None
        ]
        if not combined_filters:
            raise ValueError("The --device queries conflict with requires.device.")
        return combined_filters


__all__ = ["Plan"]
