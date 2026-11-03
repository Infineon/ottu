from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from glob import has_magic
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ottu.backend import Backend
from ottu.device import (
    Device,
    DeviceInput,
    DeviceQuery,
)
from ottu.report import TestReportObserver
from ottu.suite.suite import (
    DevicePool,
    Suite,
    SuiteCount,
    SuiteDistributed,
    SuiteOpts,
    SuiteReplicated,
    SuiteRole,
    SuiteSequential,
)
from ottu.test import Test, TestOpts
from ottu.test_path import (
    TestPath,
    TestPathContext,
    TestPathInput,
    TestPathResolver,
)


class SuiteDeviceInput(BaseModel):
    """A device selector assigned to an optional test role."""

    model_config = ConfigDict(extra="forbid", strict=True)

    role: str | None = Field(default=None, min_length=1)
    device: DeviceInput = Field(default_factory=DeviceInput)

    @model_validator(mode="before")
    @classmethod
    def _from_flat_device_fields(cls, value: Any) -> Any:
        """Accept flat device fields in suite and plan inputs."""
        if not isinstance(value, dict) or "device" in value:
            return value
        values = dict(value)
        role = values.pop("role", None)
        return {"role": role, "device": values}


@dataclass(frozen=True)
class SuiteInput:
    """The typed inputs that describe a suite: its tests, counts and devices."""

    test_inputs: tuple[TestPathInput, ...] = ()
    exclude_test_inputs: tuple[TestPathInput, ...] = ()
    count_input: SuiteCount | None = None
    device_inputs: tuple[SuiteDeviceInput, ...] = ()

    def is_role_mode(self) -> bool:
        """Return whether any test input assigns a role."""
        return any(test_input.role is not None for test_input in self.test_inputs)

    def validator(self) -> type[SuiteInputValidator] | type[SuiteRoleInputValidator]:
        """Return the validator for this suite input's mode."""
        return SuiteRoleInputValidator if self.is_role_mode() else SuiteInputValidator

    def device_resolver(
        self,
    ) -> type[SuiteDeviceResolver] | type[SuiteRoleDeviceResolver]:
        """Return the device resolver for this suite input's mode."""
        return SuiteRoleDeviceResolver if self.is_role_mode() else SuiteDeviceResolver


class SuiteInputValidator:
    """Validate that standard suite inputs do not contain role-only values."""

    @classmethod
    def validate(
        cls,
        context: TestPathContext,
        suite_input: SuiteInput,
        jobs: int = 1,
    ) -> None:
        """Reject role-only inputs in a standard suite."""
        cls._reject_role_count_without_role_tests(suite_input.count_input)
        cls._reject_role_devices_without_role_tests(suite_input.device_inputs)
        cls._reject_role_qualified_excludes(suite_input.exclude_test_inputs)

    @staticmethod
    def _reject_role_count_without_role_tests(
        count_input: SuiteCount | None,
    ) -> None:
        """Reject role-specific counts when no test has a role."""
        if isinstance(count_input, tuple):
            if not count_input:
                raise ValueError("Suite role counts must not be empty.")
            raise ValueError(
                f"Count for role '{count_input[0].role}' needs role-qualified tests."
            )

    @staticmethod
    def _reject_role_devices_without_role_tests(
        device_inputs: Sequence[SuiteDeviceInput],
    ) -> None:
        """Reject role-qualified devices when no test has a role."""
        for device_input in device_inputs:
            if device_input.role is not None:
                raise ValueError(
                    f"Device for role '{device_input.role}' needs role-qualified tests."
                )

    @staticmethod
    def _reject_role_qualified_excludes(
        exclude_test_inputs: Sequence[TestPathInput],
    ) -> None:
        """Reject role-qualified exclusions, which have no role-based meaning."""
        if any(test_input.role is not None for test_input in exclude_test_inputs):
            raise ValueError("Excluded test inputs cannot be role-qualified.")


class SuiteRoleInputValidator:
    """Validate the additional constraints on a role-based suite."""

    @classmethod
    def validate(
        cls,
        context: TestPathContext,
        suite_input: SuiteInput,
        jobs: int = 1,
    ) -> None:
        """Validate role assignments, counts, devices, and execution options."""
        test_inputs = suite_input.test_inputs
        role_values = [test_input.role for test_input in test_inputs]
        cls._require_roles_on_all_tests(test_inputs)
        roles = [role for role in role_values if role is not None]
        cls._require_unique_roles(roles)
        cls._require_one_file_per_role(test_inputs, context)
        cls._reject_exclusions_and_jobs(suite_input.exclude_test_inputs, jobs)
        cls._validate_role_counts(suite_input.count_input, roles)
        cls._validate_role_devices(suite_input.device_inputs, roles)

    @staticmethod
    def _require_roles_on_all_tests(test_inputs: Sequence[TestPathInput]) -> None:
        """Reject role-qualified tests mixed with tests without a role."""
        if any(test_input.role is None for test_input in test_inputs):
            raise ValueError("Role-qualified and unqualified tests cannot be mixed.")

    @staticmethod
    def _require_unique_roles(roles: Sequence[str]) -> None:
        """Reject a role that is given to more than one test."""
        for role in roles:
            if roles.count(role) > 1:
                raise ValueError(f"Role '{role}' was provided more than once.")

    @staticmethod
    def _require_one_file_per_role(
        test_inputs: Sequence[TestPathInput],
        context: TestPathContext,
    ) -> None:
        """Require every role selector to name one included file."""
        for test_input in test_inputs:
            if has_magic(test_input.test_selector):
                raise ValueError(
                    f"Role '{test_input.role}' must reference one test file, "
                    "not a pattern."
                )
            if not TestPathResolver.is_single_file(test_input.test_selector, context):
                raise ValueError(
                    f"Role '{test_input.role}' must reference exactly one test file."
                )

    @staticmethod
    def _reject_exclusions_and_jobs(
        exclude_test_inputs: Sequence[TestPathInput], jobs: int
    ) -> None:
        """Reject exclusions and several jobs, which role tests do not support."""
        if exclude_test_inputs:
            raise ValueError("Exclusions are not supported for role-based tests.")
        if jobs != 1:
            raise ValueError("Jobs are not supported for role-based tests.")

    @staticmethod
    def _validate_role_counts(
        count_input: SuiteCount | None, roles: Sequence[str]
    ) -> None:
        """Require role counts to name known roles."""
        if isinstance(count_input, tuple):
            count_roles = [role_count.role for role_count in count_input]
            for role in count_roles:
                if count_roles.count(role) > 1:
                    raise ValueError(
                        f"Role count for '{role}' was provided more than once."
                    )
            for role_count in count_input:
                if role_count.role not in roles:
                    raise ValueError(f"Unknown role '{role_count.role}' in count.")

    @staticmethod
    def _validate_role_devices(
        device_inputs: Sequence[SuiteDeviceInput], roles: Sequence[str]
    ) -> None:
        """Require one device for all roles, or exactly one device for each role."""
        qualified = [device for device in device_inputs if device.role is not None]
        if not qualified:
            if len(device_inputs) > 1:
                raise ValueError(
                    "Several device inputs need a role to say which role each "
                    "one is for."
                )
            return
        if len(qualified) != len(device_inputs):
            raise ValueError(
                "Role-qualified device inputs cannot be mixed with unqualified inputs."
            )
        device_roles = [
            role for device in qualified if (role := device.role) is not None
        ]
        for role in device_roles:
            if role not in roles:
                raise ValueError(f"Unknown role '{role}' in device input.")
            if device_roles.count(role) > 1:
                raise ValueError(
                    f"Device input for role '{role}' was provided more than once."
                )
        missing = [role for role in roles if role not in device_roles]
        if missing:
            raise ValueError(f"Missing device input for role(s): {', '.join(missing)}.")


class SuiteDeviceResolver:
    """Resolve standard suite selectors into an ordered device pool."""

    @classmethod
    def resolve(
        cls,
        tests: Sequence[Test],
        device_inputs: Sequence[SuiteDeviceInput],
        available_devices: Sequence[Device],
        options: SuiteOpts,
    ) -> DevicePool:
        """Resolve matching candidates without checking their connectivity."""
        del tests
        if not device_inputs and not available_devices:
            raise ValueError("At least one device is required.")

        selectors = tuple(
            device_input.device
            for device_input in device_inputs
            if device_input.role is None
        )
        devices = cls._matching_devices(selectors, available_devices)
        required_count = options.suite_count * options.jobs
        if len(devices) < required_count:
            raise ValueError(
                f"Suite needs {required_count} devices, but only "
                f"{len(devices)} matched."
            )
        return {None: tuple(devices)}

    @classmethod
    def _matching_devices(
        cls,
        selectors: Sequence[DeviceInput],
        available_devices: Sequence[Device],
    ) -> list[Device]:
        """Return all matching candidates without filtering connectivity."""
        if available_devices:
            matches: list[Device] = []
            for selector in selectors or (DeviceInput(),):
                matches.extend(
                    device
                    for device in DeviceQuery.find(
                        available_devices,
                        (selector,),
                        check_connected=False,
                    )
                    if device not in matches
                )
        else:
            matches = [cls._device_from_input(selector) for selector in selectors]
        unique_matches: list[Device] = []
        for device in matches:
            if device not in unique_matches:
                unique_matches.append(device)
        return unique_matches

    @staticmethod
    def _device_from_input(device_input: DeviceInput) -> Device:
        """Resolve an input without a catalog, requiring an identifying value."""
        if not any(
            value is not None
            for value in (
                device_input.identifier,
                device_input.name,
                device_input.uid,
                device_input.address,
            )
        ):
            raise ValueError(
                "A device identity is required when no device catalog is available."
            )
        return Device.from_input(device_input)


class SuiteRoleDeviceResolver(SuiteDeviceResolver):
    """Resolve device candidates into pools associated with test roles."""

    @classmethod
    def resolve(
        cls,
        tests: Sequence[Test],
        device_inputs: Sequence[SuiteDeviceInput],
        available_devices: Sequence[Device],
        options: SuiteOpts,
    ) -> DevicePool:
        """Resolve one candidate pool per role without checking connectivity."""
        role_values = [
            test.options.role for test in tests if test.options.role is not None
        ]
        roles = tuple(dict.fromkeys(role_values))
        pools: DevicePool = {}
        for role in roles:
            role_inputs = tuple(
                device_input.device
                for device_input in device_inputs
                if device_input.role == role
            )
            selectors = role_inputs or tuple(
                device_input.device
                for device_input in device_inputs
                if device_input.role is None
            )
            if not selectors:
                selectors = (DeviceInput(),)
            devices = cls._matching_devices(selectors, available_devices)
            required_count = options.count_for_role(role) * options.jobs
            if len(devices) < required_count:
                raise ValueError(
                    f"Role '{role}' needs {required_count} devices, but only "
                    f"{len(devices)} matched."
                )
            pools[role] = tuple(devices)
        return pools


class SuiteBuilder:
    """Build a suite from the typed inputs of its tests, counts and devices."""

    @classmethod
    def build(
        cls,
        context: TestPathContext,
        suite_input: SuiteInput,
        dev_list: Path | None = None,
        jobs: int = 1,
        backend: Backend | None = None,
        observers: Sequence[TestReportObserver] = (),
        name: str | None = None,
    ) -> Suite:
        """Resolve the tests and devices of the input, and build the suite.

        Without test inputs, the tests are discovered. The excluded tests are
        removed after inputs are validated and their paths are resolved.
        """
        suite_input.validator().validate(
            context,
            suite_input,
            jobs,
        )
        test_paths = cls._resolve_test_paths(
            suite_input.test_inputs, suite_input.exclude_test_inputs, context
        )
        available_devices = Device.from_file(dev_list) if dev_list else []
        tests = cls._create_tests(test_paths, backend, observers)
        options = SuiteOpts(
            jobs=jobs,
            count=1 if suite_input.count_input is None else suite_input.count_input,
        )
        device_pool = suite_input.device_resolver().resolve(
            tests,
            suite_input.device_inputs,
            available_devices,
            options,
        )
        return cls._suite_class(tests, options)(
            name=name,
            tests=tests,
            device_pool=device_pool,
            options=options,
            observers=tuple(observers),
        )

    @staticmethod
    def _suite_class(tests: Sequence[Test], options: SuiteOpts) -> type[Suite]:
        """Return the suite class of the execution mode that the inputs need.

        Role tests run together as one group; otherwise several jobs are
        distributed, several replicas are replicated, and anything else runs
        sequentially.
        """
        if any(test.options.role is not None for test in tests):
            return SuiteRole
        if options.jobs > 1:
            return SuiteDistributed
        if options.suite_count > 1:
            return SuiteReplicated
        return SuiteSequential

    @staticmethod
    def _resolve_test_paths(
        test_inputs: Sequence[TestPathInput],
        exclude_test_inputs: Sequence[TestPathInput],
        context: TestPathContext,
    ) -> list[tuple[str | None, TestPath]]:
        """Resolve the test inputs into the test paths, with their roles.

        The excluded tests, and the tests that the context excludes, are not
        kept.
        """
        if test_inputs:
            test_paths = [
                (test_input.role, test_path)
                for test_input in test_inputs
                for test_path in TestPath.from_input(test_input, context)
            ]
        else:
            test_paths = [
                (None, test_path) for test_path in TestPathResolver.discover(context)
            ]
        exclude_test_paths = [
            test_path
            for test_input in exclude_test_inputs
            for test_path in TestPath.from_input(test_input, context)
        ]
        kept_paths = TestPathResolver.exclude(
            [test_path for _, test_path in test_paths], exclude_test_paths, context
        )
        return [
            (role, test_path)
            for role, test_path in test_paths
            if test_path in kept_paths
        ]

    @staticmethod
    def _create_tests(
        test_paths: Sequence[tuple[str | None, TestPath]],
        backend: Backend | None,
        observers: Sequence[TestReportObserver],
    ) -> list[Test]:
        """Create a test for every test path, with the role in its options."""
        return [
            Test(
                test_path,
                options=TestOpts(role=role),
                backend=backend,
                observers=tuple(observers),
            )
            for role, test_path in test_paths
        ]
