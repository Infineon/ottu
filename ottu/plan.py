"""Load a test plan file, and select and build the suites of a test plan."""

from collections.abc import Sequence
from dataclasses import replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
)

from ottu.backend import Backend
from ottu.device import DeviceInput
from ottu.report import SuiteSkipNotifier, TestReportObserver
from ottu.suite import (
    InsufficientDevicesError,
    RoleCount,
    Suite,
    SuiteBuilder,
    SuiteCount,
    SuiteDeviceInput,
    SuiteInput,
)
from ottu.test_path import TestPathContext, TestPathInput


def _as_list(value: Any) -> Any:
    """Accept a single string or mapping as a one-element list."""
    return [value] if isinstance(value, (str, dict)) else value


class PlanTestInput(BaseModel):
    """A test assigned to one device role."""

    model_config = ConfigDict(extra="forbid", strict=True)

    role: str = Field(min_length=1)
    test: str = Field(min_length=1)
    count: int = Field(default=1, ge=1)


StringList = Annotated[list[str], BeforeValidator(_as_list)]
TestList = Annotated[list[str | PlanTestInput], BeforeValidator(_as_list)]
DeviceInputList = Annotated[list[SuiteDeviceInput], BeforeValidator(_as_list)]


class PlanSuiteRequires(BaseModel):
    """Requirements a suite needs in order to run."""

    model_config = ConfigDict(extra="forbid", strict=True)

    device: DeviceInputList = Field(default_factory=list)

    @field_validator("device")
    @classmethod
    def _reject_identifiers(
        cls, devices: list[SuiteDeviceInput]
    ) -> list[SuiteDeviceInput]:
        """Require every device to be described by its fields."""
        if any(device.device.identifier is not None for device in devices):
            raise ValueError("A required device cannot use 'identifier'.")
        return devices


class PlanSuiteInput(BaseModel):
    """A suite entry from a test plan file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = None
    tests: TestList = Field(default_factory=list)
    exclude: StringList = Field(default_factory=list)
    count: int | None = Field(default=None, ge=1)
    requires: PlanSuiteRequires = Field(default_factory=PlanSuiteRequires)


class PlanFile(BaseModel):
    """The validated contents of a test plan file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    suites: list[PlanSuiteInput] = Field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> "PlanFile":
        """Load and validate a test plan file."""
        with Path(path).open(encoding="utf-8") as plan_file:
            return cls.model_validate(yaml.safe_load(plan_file))


class Plan:
    """A loaded test plan whose suites can be selected and built."""

    def __init__(self, suites: Sequence[PlanSuiteInput]) -> None:
        self.suites = tuple(suites)

    @classmethod
    def from_file(cls, path: str | Path) -> "Plan":
        """Load and validate a plan file."""
        return cls(PlanFile.from_file(path).suites)

    def build_suites(
        self,
        context: TestPathContext,
        tests: Sequence[str] = (),
        exclude: Sequence[str] = (),
        count: SuiteCount | None = None,
        device_inputs: Sequence[SuiteDeviceInput] = (),
        dev_list: Path | None = None,
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestReportObserver] = (),
    ) -> list[Suite]:
        """Build one suite for each suite of the plan that the selection keeps.

        ``tests`` and ``exclude`` are glob patterns that select suites by name.
        The command overrides the plan counts, but not the devices.
        ``device_inputs`` filter the suites: each one is combined with every
        ``requires.device`` of a suite, and a suite that no command device can
        satisfy or that has too few matching available devices is skipped.
        ``count`` replaces the counts of a suite when one has no role; role
        counts replace only the counts of those roles. ``jobs`` is given to
        every suite. Observers that implement ``suite_skipped`` are notified
        when a suite is skipped.
        """
        suites = []
        skip_notifier = SuiteSkipNotifier(observers)
        for index, plan_suite in enumerate(self._select(tests, exclude), start=1):
            suite_input = self._suite_input(plan_suite)
            applicable, combined_inputs = self._combine_device_inputs(
                suite_input.device_inputs, device_inputs
            )
            suite_name = plan_suite.name or f"Suite {index}"
            if not applicable:
                skip_notifier.notify(suite_name)
                continue
            try:
                suite = SuiteBuilder.build(
                    context,
                    replace(
                        suite_input,
                        count_input=self._override_count(
                            suite_input.count_input, count
                        ),
                        device_inputs=combined_inputs,
                    ),
                    dev_list,
                    jobs,
                    backend=backend,
                    observers=observers,
                    name=suite_name,
                )
            except InsufficientDevicesError:
                skip_notifier.notify(suite_name)
                continue
            suites.append(suite)
        return suites

    @classmethod
    def _combine_device_inputs(
        cls,
        required: Sequence[SuiteDeviceInput],
        requested: Sequence[SuiteDeviceInput],
    ) -> tuple[bool, tuple[SuiteDeviceInput, ...]]:
        """Combine the devices a suite requires with the devices requested.

        The inputs of each list are alternatives (OR), and every requested
        input is combined (AND) with every required input of the same role. A
        pair whose values conflict is dropped. The suite is not applicable
        when a role is left with no pair. A list without inputs does not
        restrict, and an input without a role applies to every role that the
        other list names. Returns whether the suite is applicable, and the
        combined device inputs.
        """
        if not required or not requested:
            return True, tuple(required or requested)

        required = cls._expand_roles(required, requested)
        requested = cls._expand_roles(requested, required)
        combined: list[SuiteDeviceInput] = []
        for role in dict.fromkeys(item.role for item in (*required, *requested)):
            role_required = [item for item in required if item.role == role]
            role_requested = [item for item in requested if item.role == role]
            if not role_required or not role_requested:
                combined.extend(role_required or role_requested)
                continue
            merged = [
                SuiteDeviceInput(role=role, device=device)
                for required_item in role_required
                for requested_item in role_requested
                if (
                    device := cls._merge_devices(
                        required_item.device, requested_item.device
                    )
                )
                is not None
            ]
            if not merged:
                return False, ()
            combined.extend(merged)
        return True, tuple(combined)

    @staticmethod
    def _expand_roles(
        inputs: Sequence[SuiteDeviceInput],
        other: Sequence[SuiteDeviceInput],
    ) -> list[SuiteDeviceInput]:
        """Repeat the inputs without a role for each role the other list names."""
        roles = list(dict.fromkeys(item.role for item in other if item.role))
        return [
            replacement
            for item in inputs
            for replacement in (
                [SuiteDeviceInput(role=role, device=item.device) for role in roles]
                if item.role is None and roles
                else [item]
            )
        ]

    @staticmethod
    def _merge_devices(first: DeviceInput, second: DeviceInput) -> DeviceInput | None:
        """Return the device that satisfies both inputs, or None on a conflict."""
        values: dict[str, Any] = {}
        for key in DeviceInput.model_fields:
            first_value, second_value = getattr(first, key), getattr(second, key)
            if isinstance(first_value, list):
                values[key] = [
                    *first_value,
                    *(item for item in second_value if item not in first_value),
                ]
            elif (
                None not in (first_value, second_value) and first_value != second_value
            ):
                return None
            else:
                values[key] = first_value if first_value is not None else second_value
        return DeviceInput(**values)

    def _select(
        self,
        selectors: Sequence[str] = (),
        exclude: Sequence[str] = (),
    ) -> list[PlanSuiteInput]:
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

    @staticmethod
    def _override_count(
        plan_count: SuiteCount | None,
        command_count: SuiteCount | None,
    ) -> SuiteCount | None:
        """Return the plan count after applying the command count."""
        if command_count is None:
            return plan_count
        if isinstance(command_count, int):
            return command_count
        if isinstance(plan_count, int):
            raise ValueError("Role counts cannot mix integer and role=count values.")
        if plan_count is None:
            return command_count

        command_roles = {role_count.role for role_count in command_count}
        return (
            *(
                role_count
                for role_count in plan_count
                if role_count.role not in command_roles
            ),
            *command_count,
        )

    @staticmethod
    def _suite_input(plan_suite: PlanSuiteInput) -> SuiteInput:
        """Convert a suite of the plan into the typed input of a suite."""
        test_inputs = []
        role_counts = []
        for test in plan_suite.tests:
            if isinstance(test, PlanTestInput):
                test_inputs.append(
                    TestPathInput(role=test.role, test_selector=test.test)
                )
                role_counts.append(RoleCount(role=test.role, count=test.count))
            else:
                test_inputs.append(TestPathInput(test_selector=test))
        if plan_suite.count is not None:
            if role_counts:
                raise ValueError(
                    "Role counts cannot mix integer and role=count values."
                )
            count: SuiteCount | None = plan_suite.count
        else:
            count = tuple(role_counts) if role_counts else None
        return SuiteInput(
            test_inputs=tuple(test_inputs),
            exclude_test_inputs=tuple(
                TestPathInput(test_selector=exclude) for exclude in plan_suite.exclude
            ),
            count_input=count,
            device_inputs=tuple(plan_suite.requires.device),
        )

    @staticmethod
    def _matches(suite: PlanSuiteInput, patterns: Sequence[str]) -> bool:
        """Return whether the suite name matches any of the glob patterns."""
        return suite.name is not None and any(
            fnmatchcase(suite.name, pattern) for pattern in patterns
        )


__all__ = ["Plan"]
