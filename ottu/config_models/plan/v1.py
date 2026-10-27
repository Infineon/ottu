"""Pydantic models for version 1 of the test plan file."""

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)


def _as_list(value: Any) -> Any:
    """Accept a single string or mapping as a one-element list."""
    return [value] if isinstance(value, (str, dict)) else value


class RoleTest(BaseModel):
    """A test assigned to one device role."""

    model_config = ConfigDict(extra="forbid", strict=True)

    role: str = Field(min_length=1)
    test: str = Field(min_length=1)
    count: int = Field(default=1, ge=1)


StringList = Annotated[list[str], BeforeValidator(_as_list)]
TestList = Annotated[list[str | RoleTest], BeforeValidator(_as_list)]
DeviceFilterList = Annotated[list[dict[str, Any]], BeforeValidator(_as_list)]


class Requires(BaseModel):
    """Requirements a suite needs in order to run."""

    model_config = ConfigDict(extra="forbid", strict=True)

    device: DeviceFilterList = Field(default_factory=list)


class SuiteDefinition(BaseModel):
    """A suite entry from a version 1 test plan."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = None
    tests: TestList = Field(default_factory=list)
    exclude: StringList = Field(default_factory=list)
    count: int | None = Field(default=None, ge=1)
    requires: Requires = Field(default_factory=Requires)

    @model_validator(mode="after")
    def _validate_role_tests(self) -> "SuiteDefinition":
        """Check that role tests are not mixed and are consistent."""
        role_tests = [test for test in self.tests if isinstance(test, RoleTest)]
        if not role_tests:
            return self
        if len(role_tests) != len(self.tests):
            raise ValueError(
                "Role tests cannot be mixed with other tests; every entry "
                "must define 'role' and 'test'."
            )

        roles = [test.role for test in role_tests]
        if len(set(roles)) != len(roles):
            raise ValueError("Role tests must use unique roles.")

        if self.count is not None:
            raise ValueError("Use per-role 'count' instead of a suite 'count'.")
        if self.exclude:
            raise ValueError("'exclude' cannot be used with role tests.")

        # Without device entries the devices come from the command line.
        if self.requires.device:
            device_roles = {device.get("role") for device in self.requires.device}
            missing = [role for role in roles if role not in device_roles]
            if missing:
                raise ValueError(
                    f"Role tests have no matching requires.device role: {missing}"
                )
        return self


class Plan(BaseModel):
    """Validated contents of version 1 of a test plan file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    suites: list[SuiteDefinition] = Field(default_factory=list)


__all__ = ["Plan", "Requires", "RoleTest", "SuiteDefinition"]
