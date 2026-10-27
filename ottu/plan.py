"""Select and build the suites of a test plan."""

import json
from collections.abc import Mapping, Sequence
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from ottu.backend import Backend
from ottu.config_models.plan.plan import PlanConfig, RoleTest, SuiteDefinition
from ottu.device import Device, DeviceQuery
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
        """Translate one plan suite into the inputs of ``Suite.from_inputs``."""
        role_tests = [test for test in suite.tests if isinstance(test, RoleTest)]
        count: str | None
        if role_tests:
            test_inputs = [f"{test.role}={test.test}" for test in role_tests]
            count = ",".join(f"{test.role}={test.count}" for test in role_tests)
        else:
            test_inputs = [test for test in suite.tests if isinstance(test, str)]
            count = str(suite.count) if suite.count is not None else None
        return Suite.from_inputs(
            test_inputs,
            context=context,
            exclude=suite.exclude,
            count=count,
            devices=cls._suite_devices(
                role_tests, suite.requires.device, devices, dev_list
            ),
            dev_list=dev_list,
            backend=backend,
            observers=observers,
        )

    @classmethod
    def _suite_devices(
        cls,
        role_tests: Sequence[RoleTest],
        required: Sequence[Mapping[str, Any]],
        devices: Sequence[str],
        dev_list: Path | None,
    ) -> list[str]:
        """Return the suite device inputs, defaulting roles to any device."""
        device_inputs = cls._device_inputs(required, devices, dev_list)
        if role_tests and not device_inputs and dev_list is not None:
            return [f"role={test.role}" for test in role_tests]
        return device_inputs

    @staticmethod
    def _matches(suite: SuiteDefinition, patterns: Sequence[str]) -> bool:
        """Return whether the suite name matches any of the glob patterns."""
        return suite.name is not None and any(
            fnmatchcase(suite.name, pattern) for pattern in patterns
        )

    @classmethod
    def _device_inputs(
        cls,
        required: Sequence[Mapping[str, Any]],
        devices: Sequence[str],
        dev_list: Path | None,
    ) -> list[str]:
        """Return the device inputs of a suite as CLI ``--device`` strings."""
        if not devices:
            return [cls._format_filter(entry) for entry in required]
        if dev_list is None or not required:
            return list(devices)

        merged = [
            cls._format_filter(combined)
            for entry in required
            for alternative in cls._query_filters(devices)
            if (combined := cls._combine(entry, alternative)) is not None
        ]
        if not merged:
            raise ValueError("The --device queries conflict with requires.device.")
        return merged

    @staticmethod
    def _query_filters(devices: Sequence[str]) -> list[Mapping[str, Any]]:
        """Parse ``--device`` queries into filter mappings."""
        filters: list[Mapping[str, Any]] = []
        for device in devices:
            if "=" in device:
                filters.append(DeviceQuery._parse_filter(device))
            else:
                filters.extend(Device.from_string(device).identity_filters())
        return filters

    @staticmethod
    def _combine(
        first: Mapping[str, Any], second: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """AND two filters, or return ``None`` when they contradict."""
        if any(key in first and first[key] != value for key, value in second.items()):
            return None
        return {**first, **second}

    @staticmethod
    def _format_filter(device_filter: Mapping[str, Any]) -> str:
        """Format a filter mapping as a comma-separated ``key=value`` string."""
        parts: list[str] = []
        for key, value in device_filter.items():
            if isinstance(value, (list, dict)):
                text = json.dumps(value)
            else:
                text = str(value)
                if "," in text or text.startswith(("{", "[")):
                    raise ValueError(
                        f"Device value for '{key}' cannot be expressed as a query."
                    )
            parts.append(f"{key}={text}")
        return ",".join(parts)


__all__ = ["Plan"]
