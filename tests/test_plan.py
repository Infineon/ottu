"""Tests for test plan selection and suite building."""

import pytest
from ottu.config_models.plan.plan import RoleTest, SuiteDefinition
from ottu.plan import Plan
from ottu.suite import Suite
from ottu.test_path import TestPathContext


def named(name, **values):
    return SuiteDefinition(name=name, **values)


@pytest.fixture
def context(tmp_path):
    return TestPathContext(working_dir=tmp_path)


@pytest.fixture
def dev_list(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected", lambda self: True
    )
    path = tmp_path / "devs.yaml"
    path.write_text(
        "version: 1\n"
        "devices:\n"
        "  - name: uno\n"
        "    uid: abcdef01\n"
        "    features: [wifi]\n"
        "  - name: nano\n"
        "    uid: abcdef02\n"
        "    features: [ble]\n",
        encoding="utf-8",
    )
    return path


def test_plan_from_file_loads_suites(tmp_path):
    path = tmp_path / "plan.yml"
    path.write_text("version: 1\nsuites:\n  - name: a\n  - name: b\n", encoding="utf-8")

    assert [suite.name for suite in Plan.from_file(path).suites] == ["a", "b"]


def test_plan_select_without_selectors_returns_all_suites():
    plan = Plan([named("a"), SuiteDefinition(), named("b")])

    assert plan.select() == list(plan.suites)


def test_plan_select_matches_names_with_globs_in_plan_order():
    plan = Plan([named("smoke-a"), named("link"), named("smoke-b")])

    selected = plan.select(["smoke-*"])

    assert [suite.name for suite in selected] == ["smoke-a", "smoke-b"]


def test_plan_select_never_selects_unnamed_suites_by_name():
    plan = Plan([SuiteDefinition(), named("a")])

    assert [suite.name for suite in plan.select(["*"])] == ["a"]


def test_plan_select_rejects_selector_without_match():
    with pytest.raises(ValueError, match="No suite in the plan matches 'nope'"):
        Plan([named("a")]).select(["nope"])


def test_plan_select_applies_exclusions():
    plan = Plan([named("a"), named("b"), SuiteDefinition()])

    selected = plan.select(exclude=["b"])

    assert [suite.name for suite in selected] == ["a", None]


def test_plan_select_applies_exclusions_after_selectors():
    plan = Plan([named("smoke-a"), named("smoke-b"), named("link")])

    selected = plan.select(["smoke-*"], ["smoke-b"])

    assert [suite.name for suite in selected] == ["smoke-a"]


def test_plan_build_suites_creates_standard_suite(tmp_path, context):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", count=2)])

    (suite,) = plan.build_suites(plan.suites, context=context, devices=["uno"])

    assert isinstance(suite, Suite)
    assert suite.options.count == 2
    assert suite.runner == "runner_repeated"
    assert [test.test_path.file_name for test in suite.tests] == ["check.py"]


def test_plan_build_suites_applies_exclude(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan([named("a", tests=["a.py", "b.py"], exclude="b.py")])

    (suite,) = plan.build_suites(plan.suites, context=context, devices=["uno"])

    assert [test.test_path.file_name for test in suite.tests] == ["a.py"]


def test_plan_build_suites_creates_one_suite_per_selection(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan([named("a", tests="a.py"), named("b", tests="b.py")])

    suites = plan.build_suites(plan.suites, context=context, devices=["uno"])

    assert [suite.tests[0].test_path.file_name for suite in suites] == ["a.py", "b.py"]


def test_plan_build_suites_creates_role_suite(tmp_path, context, monkeypatch):
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected", lambda self: True
    )
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()
    (tmp_path / "roles.yaml").write_text(
        "version: 1\n"
        "devices:\n"
        "  - {name: srv, uid: abcdef01, features: [hub]}\n"
        "  - {name: cl1, uid: abcdef02, features: [leaf]}\n"
        "  - {name: cl2, uid: abcdef03, features: [leaf]}\n",
        encoding="utf-8",
    )
    plan = Plan(
        [
            named(
                "roles",
                tests=[
                    RoleTest(role="server", test="server.py"),
                    RoleTest(role="client", test="client.py", count=2),
                ],
                requires={
                    "device": [
                        {"role": "server", "features": ["hub"]},
                        {"role": "client", "features": ["leaf"]},
                    ]
                },
            )
        ]
    )

    (suite,) = plan.build_suites(
        plan.suites, context=context, dev_list=tmp_path / "roles.yaml"
    )

    assert suite.runner == "runner_parallel"
    assert [(test.options.role, test.device.name) for test in suite.tests] == [
        ("server", "srv"),
        ("client", "cl1"),
        ("client", "cl2"),
    ]


def test_plan_build_suites_uses_cli_devices_as_given_without_device_list(
    tmp_path, context
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [named("a", tests="check.py", requires={"device": [{"name": "other"}]})]
    )

    (suite,) = plan.build_suites(plan.suites, context=context, devices=["uno"])

    assert [device.name for device in suite.resolved_devices] == ["uno"]


def test_plan_build_suites_without_cli_devices_uses_requires(
    tmp_path, context, dev_list
):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", requires={"device": [{"name": "nano"}]})])

    (suite,) = plan.build_suites(plan.suites, context=context, dev_list=dev_list)

    assert [device.name for device in suite.resolved_devices] == ["nano"]


def test_plan_build_suites_requires_a_device(tmp_path, context):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py")])

    with pytest.raises(ValueError, match="At least one device is required"):
        plan.build_suites(plan.suites, context=context)


def test_plan_build_suites_ands_cli_query_with_requires(tmp_path, context, dev_list):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [
            named(
                "a",
                tests="check.py",
                requires={"device": [{"features": ["wifi"]}, {"features": ["ble"]}]},
            )
        ]
    )

    (suite,) = plan.build_suites(
        plan.suites, context=context, devices=["name=nano"], dev_list=dev_list
    )

    assert [device.name for device in suite.resolved_devices] == ["nano"]


def test_plan_build_suites_ands_bare_cli_query_with_requires(
    tmp_path, context, dev_list
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [named("a", tests="check.py", requires={"device": [{"features": ["wifi"]}]})]
    )

    (suite,) = plan.build_suites(
        plan.suites, context=context, devices=["uno"], dev_list=dev_list
    )

    assert [device.name for device in suite.resolved_devices] == ["uno"]


def test_plan_build_suites_and_excludes_devices_outside_requires(
    tmp_path, context, dev_list
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [
            named(
                "a",
                tests="check.py",
                requires={"device": [{"features": ["wifi"]}, {"name": "uno"}]},
            )
        ]
    )

    (suite,) = plan.build_suites(
        plan.suites,
        context=context,
        devices=["name=uno,uid=abcdef01"],
        dev_list=dev_list,
    )

    assert [device.name for device in suite.resolved_devices] == ["uno"]


def test_plan_build_suites_rejects_conflicting_cli_query(tmp_path, context, dev_list):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", requires={"device": [{"name": "uno"}]})])

    with pytest.raises(ValueError, match="conflict with requires.device"):
        plan.build_suites(
            plan.suites, context=context, devices=["name=nano"], dev_list=dev_list
        )


def test_plan_build_suites_formats_requires_with_json_values(
    tmp_path, context, dev_list
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [
            named(
                "a",
                tests="check.py",
                requires={"device": [{"features": ["wifi", "ble"]}]},
            )
        ]
    )

    (suite,) = plan.build_suites(plan.suites, context=context, dev_list=dev_list)

    assert suite.resolved_devices == ()


@pytest.mark.parametrize("value", ["a,b", "[x]", "{x}"])
def test_plan_build_suites_rejects_values_that_cannot_be_a_query(
    tmp_path, context, value
):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", requires={"device": [{"name": value}]})])

    with pytest.raises(ValueError, match="cannot be expressed as a query"):
        plan.build_suites(plan.suites, context=context)


@pytest.fixture
def role_plan(tmp_path):
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()
    return Plan(
        [
            named(
                "roles",
                tests=[
                    RoleTest(role="server", test="server.py"),
                    RoleTest(role="client", test="client.py"),
                ],
            )
        ]
    )


def test_plan_build_suites_gives_each_role_any_device_without_requires(
    role_plan, context, dev_list
):
    (suite,) = role_plan.build_suites(
        role_plan.suites, context=context, dev_list=dev_list
    )

    assert [(test.options.role, test.device.name) for test in suite.tests] == [
        ("server", "uno"),
        ("client", "nano"),
    ]


def test_plan_build_suites_accepts_role_only_device_queries(
    role_plan, context, dev_list
):
    (suite,) = role_plan.build_suites(
        role_plan.suites,
        context=context,
        devices=["role=server", "role=client"],
        dev_list=dev_list,
    )

    assert [test.device.name for test in suite.tests] == ["uno", "nano"]


def test_plan_build_suites_role_without_device_source_requires_a_device(
    role_plan, context
):
    with pytest.raises(ValueError, match="Role 'server' requires a device"):
        role_plan.build_suites(role_plan.suites, context=context)
