"""Tests for test plan selection and suite building."""

import pytest
from ottu.cli.parse import parse_suite_count, parse_suite_device_input
from ottu.plan import Plan, PlanSuiteInput, PlanTestInput
from ottu.report import TestReport
from ottu.suite import RoleCount, Suite, SuiteReplicated, SuiteRole
from ottu.test_path import TestPathContext


class RecordingObserver:
    def __init__(self):
        self.skipped = []

    def report_changed(self, report: TestReport) -> None:
        pass

    def suite_skipped(self, name: str) -> None:
        self.skipped.append(name)


def named(name, **values):
    return PlanSuiteInput(name=name, **values)


def build_suites(plan, selectors=(), exclude=(), *, context, devices=(), dev_list=None):
    return plan.build_suites(
        context,
        selectors,
        exclude,
        device_inputs=[parse_suite_device_input(value) for value in devices],
        dev_list=dev_list,
    )


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
    plan = Plan([named("a"), PlanSuiteInput(), named("b")])

    assert plan._select() == list(plan.suites)


def test_plan_select_matches_names_with_globs_in_plan_order():
    plan = Plan([named("smoke-a"), named("link"), named("smoke-b")])

    selected = plan._select(["smoke-*"])

    assert [suite.name for suite in selected] == ["smoke-a", "smoke-b"]


def test_plan_select_never_selects_unnamed_suites_by_name():
    plan = Plan([PlanSuiteInput(), named("a")])

    assert [suite.name for suite in plan._select(["*"])] == ["a"]


def test_plan_select_rejects_selector_without_match():
    with pytest.raises(ValueError, match="No suite in the plan matches 'nope'"):
        Plan([named("a")])._select(["nope"])


def test_plan_select_applies_exclusions():
    plan = Plan([named("a"), named("b"), PlanSuiteInput()])

    selected = plan._select(exclude=["b"])

    assert [suite.name for suite in selected] == ["a", None]


def test_plan_select_applies_exclusions_after_selectors():
    plan = Plan([named("smoke-a"), named("smoke-b"), named("link")])

    selected = plan._select(["smoke-*"], ["smoke-b"])

    assert [suite.name for suite in selected] == ["smoke-a"]


def test_plan_build_suites_creates_standard_suite(tmp_path, context):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", count=2)])

    (suite,) = build_suites(plan, context=context, devices=["uno", "nano"])

    assert isinstance(suite, Suite)
    assert suite.options.count == 2
    assert isinstance(suite, SuiteReplicated)
    assert [test.test_path.file_name for test in suite.tests] == ["check.py"]


def test_plan_build_suites_applies_exclude(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan([named("a", tests=["a.py", "b.py"], exclude="b.py")])

    (suite,) = build_suites(plan, context=context, devices=["uno"])

    assert [test.test_path.file_name for test in suite.tests] == ["a.py"]


def test_plan_build_suites_creates_one_suite_per_selection(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan([named("a", tests="a.py"), named("b", tests="b.py")])

    suites = build_suites(plan, context=context, devices=["uno"])

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
                    PlanTestInput(role="server", test="server.py"),
                    PlanTestInput(role="client", test="client.py", count=2),
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

    (suite,) = build_suites(plan, context=context, dev_list=tmp_path / "roles.yaml")

    assert isinstance(suite, SuiteRole)
    assert {
        role: [device.name for device in pool]
        for role, pool in suite.device_pool.items()
    } == {"server": ["srv"], "client": ["cl1", "cl2"]}


def test_plan_build_suites_without_cli_devices_uses_requires(
    tmp_path, context, dev_list
):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", requires={"device": [{"name": "nano"}]})])

    (suite,) = build_suites(plan, context=context, dev_list=dev_list)

    assert [device.name for device in suite.device_pool[None]] == ["nano"]


def test_plan_build_suites_requires_a_device(tmp_path, context):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py")])

    with pytest.raises(ValueError, match="At least one device is required"):
        build_suites(plan, context=context)


def test_plan_build_suites_combines_cli_devices_with_requires(
    tmp_path, context, dev_list
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [
            named(
                "a",
                tests="check.py",
                requires={"device": [{"features": ["ble"]}, {"name": "uno"}]},
            )
        ]
    )

    (suite,) = build_suites(
        plan, context=context, devices=["name=nano"], dev_list=dev_list
    )

    assert [device.name for device in suite.device_pool[None]] == ["nano"]


def test_plan_build_suites_skips_suites_that_conflict_with_cli_devices(
    tmp_path, context, dev_list
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [
            named("wifi", tests="check.py", requires={"device": [{"name": "uno"}]}),
            named("ble", tests="check.py", requires={"device": [{"name": "nano"}]}),
            named("any", tests="check.py"),
        ]
    )

    suites = build_suites(
        plan, context=context, devices=["name=uno"], dev_list=dev_list
    )

    assert [suite.name for suite in suites] == ["wifi", "any"]
    assert [
        [device.name for device in suite.device_pool[None]] for suite in suites
    ] == [
        ["uno"],
        ["uno"],
    ]


def test_plan_build_suites_skips_every_suite_when_no_cli_device_applies(
    tmp_path, context
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [named("a", tests="check.py", requires={"device": [{"name": "other"}]})]
    )
    observer = RecordingObserver()

    assert (
        plan.build_suites(
            context,
            device_inputs=[parse_suite_device_input("name=uno")],
            observers=[observer],
        )
        == []
    )
    assert observer.skipped == ["a"]


def test_plan_build_suites_keeps_the_position_of_skipped_suites_in_default_names(
    tmp_path, context
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [
            PlanSuiteInput(tests="check.py", requires={"device": [{"name": "a"}]}),
            PlanSuiteInput(tests="check.py", requires={"device": [{"name": "b"}]}),
        ]
    )

    (suite,) = build_suites(plan, context=context, devices=["name=b"])

    assert suite.name == "Suite 2"


def test_plan_build_suites_matches_requires_with_list_values(
    tmp_path, context, dev_list
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [
            named(
                "a",
                tests="check.py",
                requires={"device": [{"features": ["wifi"]}]},
            ),
            named(
                "b",
                tests="check.py",
                requires={"device": [{"features": ["wifi", "ble"]}]},
            ),
        ]
    )

    (wifi,) = build_suites(plan, ["a"], context=context, dev_list=dev_list)

    assert [device.name for device in wifi.device_pool[None]] == ["uno"]
    assert build_suites(plan, ["b"], context=context, dev_list=dev_list) == []


@pytest.mark.parametrize("value", ["a,b", "[x]", "{x}"])
def test_plan_build_suites_accepts_any_character_in_requires_values(
    tmp_path, context, value
):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", requires={"device": [{"name": value}]})])

    (suite,) = build_suites(plan, context=context)

    assert [device.name for device in suite.device_pool[None]] == [value]


def test_plan_build_suites_requires_a_device_list_for_feature_requirements(
    tmp_path, context
):
    (tmp_path / "check.py").touch()
    plan = Plan(
        [named("a", tests="check.py", requires={"device": [{"features": ["wifi"]}]})]
    )

    with pytest.raises(ValueError, match="device identity is required"):
        build_suites(plan, context=context)


@pytest.fixture
def role_plan(tmp_path):
    (tmp_path / "server.py").touch()
    (tmp_path / "client.py").touch()
    return Plan(
        [
            named(
                "roles",
                tests=[
                    PlanTestInput(role="server", test="server.py"),
                    PlanTestInput(role="client", test="client.py"),
                ],
            )
        ]
    )


def test_plan_build_suites_gives_each_role_any_device_without_requires(
    role_plan, context, dev_list
):
    (suite,) = build_suites(role_plan, context=context, dev_list=dev_list)

    assert {
        role: [device.name for device in devices]
        for role, devices in suite.device_pool.items()
    } == {"server": ["uno", "nano"], "client": ["uno", "nano"]}


def test_plan_build_suites_accepts_role_only_device_queries(
    role_plan, context, dev_list
):
    (suite,) = build_suites(
        role_plan,
        context=context,
        devices=["role=server", "role=client"],
        dev_list=dev_list,
    )

    assert {
        role: [device.name for device in devices]
        for role, devices in suite.device_pool.items()
    } == {"server": ["uno", "nano"], "client": ["uno", "nano"]}


def test_plan_build_suites_role_without_device_source_requires_a_device(
    role_plan, context
):
    with pytest.raises(ValueError, match="device identity is required"):
        build_suites(role_plan, context=context)


def test_plan_build_suites_command_count_replaces_the_count_of_a_suite(
    tmp_path, context
):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", count=2)])

    (suite,) = plan.build_suites(
        context,
        count=parse_suite_count("3"),
        device_inputs=[
            parse_suite_device_input("uno"),
            parse_suite_device_input("dos"),
            parse_suite_device_input("tres"),
        ],
    )

    assert suite.options.count == 3


def test_plan_build_suites_keeps_the_count_of_a_suite_without_command_count(
    tmp_path, context
):
    (tmp_path / "check.py").touch()
    plan = Plan([named("a", tests="check.py", count=2)])

    (suite,) = build_suites(plan, context=context, devices=["uno", "nano"])

    assert suite.options.count == 2


def test_plan_build_suites_gives_the_jobs_to_every_suite(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan([named("a", tests="a.py"), named("b", tests="b.py")])

    suites = plan.build_suites(
        context,
        device_inputs=[
            parse_suite_device_input("uno"),
            parse_suite_device_input("dos"),
        ],
        jobs=2,
    )

    assert [suite.options.jobs for suite in suites] == [2, 2]


def test_plan_build_suites_rejects_jobs_for_a_role_suite(role_plan, context):
    with pytest.raises(ValueError, match="Jobs are not supported"):
        role_plan.build_suites(
            context, device_inputs=[parse_suite_device_input("uno")], jobs=2
        )


def test_override_count_replaces_role_counts_with_a_suite_count():
    plan = (
        RoleCount(role="server", count=1),
        RoleCount(role="c", count=4),
    )

    assert Plan._override_count(plan, 2) == 2


def test_override_count_replaces_only_the_given_roles():
    server = RoleCount(role="server", count=1)
    client = RoleCount(role="client", count=4)
    command = (RoleCount(role="client", count=2),)

    assert Plan._override_count((server, client), command) == (
        server,
        RoleCount(role="client", count=2),
    )


def test_override_count_keeps_the_plan_count_without_a_command_count():
    plan = (RoleCount(role="client", count=2),)

    assert Plan._override_count(plan, None) == plan


def test_override_count_rejects_mixed_suite_and_role_counts():
    with pytest.raises(ValueError, match="cannot mix integer and role=count"):
        Plan._override_count(2, (RoleCount(role="server", count=1),))


def test_override_count_uses_the_command_role_counts_when_the_plan_has_none():
    command = (RoleCount(role="server", count=1),)

    assert Plan._override_count(None, command) == command


def test_plan_build_suites_rejects_role_tests_mixed_with_plain_tests(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan([named("a", tests=["a.py", PlanTestInput(role="server", test="b.py")])])

    with pytest.raises(ValueError, match="cannot be mixed"):
        build_suites(plan, context=context)


def test_plan_build_suites_rejects_duplicate_roles(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan(
        [
            named(
                "a",
                tests=[
                    PlanTestInput(role="server", test="a.py"),
                    PlanTestInput(role="server", test="b.py"),
                ],
            )
        ]
    )

    with pytest.raises(ValueError, match="'server' was provided more than once"):
        build_suites(plan, context=context)


def test_plan_build_suites_rejects_a_suite_count_with_role_tests(tmp_path, context):
    (tmp_path / "a.py").touch()
    plan = Plan(
        [named("a", count=2, tests=[PlanTestInput(role="server", test="a.py")])]
    )

    with pytest.raises(ValueError, match="cannot mix integer and role=count"):
        build_suites(plan, context=context)


def test_plan_build_suites_rejects_exclude_with_role_tests(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan(
        [
            named(
                "a",
                exclude="b.py",
                tests=[PlanTestInput(role="server", test="a.py")],
            )
        ]
    )

    with pytest.raises(ValueError, match="Exclusions are not supported"):
        build_suites(plan, context=context)


def test_plan_build_suites_rejects_a_role_without_a_required_device(tmp_path, context):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan(
        [
            named(
                "a",
                tests=[
                    PlanTestInput(role="server", test="a.py"),
                    PlanTestInput(role="client", test="b.py"),
                ],
                requires={"device": [{"role": "server"}]},
            )
        ]
    )

    with pytest.raises(ValueError, match="Missing device input for role"):
        build_suites(plan, context=context)


def test_plan_build_suites_selects_the_suites_by_name(tmp_path, context):
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).touch()
    plan = Plan(
        [
            named("smoke_a", tests="a.py"),
            named("smoke_b", tests="b.py"),
            named("slow", tests="c.py"),
        ]
    )

    selected = build_suites(plan, ["smoke_*"], context=context, devices=["uno"])
    excluded = build_suites(plan, exclude=["smoke_*"], context=context, devices=["uno"])
    both = build_suites(
        plan, ["smoke_*"], ["smoke_b"], context=context, devices=["uno"]
    )

    assert [suite.name for suite in selected] == ["smoke_a", "smoke_b"]
    assert [suite.name for suite in excluded] == ["slow"]
    assert [suite.name for suite in both] == ["smoke_a"]


def test_plan_build_suites_numbers_the_unnamed_suites_among_the_selected(
    tmp_path, context
):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    plan = Plan([named("first", tests="a.py"), named(None, tests="b.py")])

    suites = build_suites(plan, context=context, devices=["uno"])

    assert [suite.name for suite in suites] == ["first", "Suite 2"]


def test_plan_build_suites_rejects_an_unknown_suite_name(tmp_path, context):
    plan = Plan([named("a", tests="check.py")])

    with pytest.raises(ValueError, match="No suite in the plan matches 'missing'"):
        build_suites(plan, ["missing"], context=context, devices=["uno"])


def device_inputs(*values):
    return tuple(parse_suite_device_input(value) for value in values)


def test_combine_device_inputs_without_requested_devices_keeps_the_required():
    required = device_inputs("name=uno")

    assert Plan._combine_device_inputs(required, ()) == (True, required)


def test_combine_device_inputs_without_required_devices_uses_the_requested():
    requested = device_inputs("name=uno")

    assert Plan._combine_device_inputs((), requested) == (True, requested)


def test_combine_device_inputs_without_any_device_is_applicable():
    assert Plan._combine_device_inputs((), ()) == (True, ())


def test_combine_device_inputs_merges_the_values_of_a_pair():
    applicable, combined = Plan._combine_device_inputs(
        device_inputs('features=["ble"]'), device_inputs('name=nano,features=["gpio"]')
    )

    assert applicable
    (item,) = combined
    assert item.device.name == "nano"
    assert item.device.features == ["ble", "gpio"]


def test_combine_device_inputs_is_not_applicable_on_a_conflicting_key():
    assert Plan._combine_device_inputs(
        device_inputs("name=uno"), device_inputs("name=nano")
    ) == (False, ())


def test_combine_device_inputs_keeps_the_pairs_without_conflict():
    applicable, combined = Plan._combine_device_inputs(
        device_inputs("name=uno", 'features=["ble"]'),
        device_inputs("name=nano", "name=dos"),
    )

    assert applicable
    assert [(item.device.name, item.device.features) for item in combined] == [
        ("nano", ["ble"]),
        ("dos", ["ble"]),
    ]


def test_combine_device_inputs_combines_inputs_of_the_same_role():
    applicable, combined = Plan._combine_device_inputs(
        device_inputs('role=server,features=["hub"]', 'role=client,features=["leaf"]'),
        device_inputs("role=server,name=srv"),
    )

    assert applicable
    assert [
        (item.role, item.device.name, item.device.features) for item in combined
    ] == [("server", "srv", ["hub"]), ("client", None, ["leaf"])]


def test_combine_device_inputs_is_not_applicable_when_one_role_conflicts():
    assert Plan._combine_device_inputs(
        device_inputs("role=server,name=srv", "role=client,name=cl1"),
        device_inputs("role=server,name=other", "role=client,name=cl1"),
    ) == (False, ())


def test_combine_device_inputs_applies_a_requested_device_to_every_role():
    applicable, combined = Plan._combine_device_inputs(
        device_inputs("role=server,name=srv", "role=client,name=cl1"),
        device_inputs('features=["wifi"]'),
    )

    assert applicable
    assert [
        (item.role, item.device.name, item.device.features) for item in combined
    ] == [("server", "srv", ["wifi"]), ("client", "cl1", ["wifi"])]


@pytest.mark.parametrize("key", ["identifier", "name", "uid", "address"])
def test_combine_device_inputs_is_not_applicable_on_each_conflicting_key(key):
    assert Plan._combine_device_inputs(
        device_inputs(f"{key}=first"), device_inputs(f"{key}=second")
    ) == (False, ())


@pytest.mark.parametrize("key", ["identifier", "name", "uid", "address"])
def test_combine_device_inputs_accepts_equal_values_of_a_key(key):
    applicable, combined = Plan._combine_device_inputs(
        device_inputs(f"{key}=same"), device_inputs(f"{key}=same")
    )

    assert applicable
    (item,) = combined
    assert getattr(item.device, key) == "same"


def test_combine_device_inputs_combines_different_keys_of_a_pair():
    applicable, combined = Plan._combine_device_inputs(
        device_inputs("name=uno"), device_inputs("uid=abcdef01")
    )

    assert applicable
    (item,) = combined
    assert (item.device.name, item.device.uid) == ("uno", "abcdef01")


def test_combine_device_inputs_does_not_repeat_a_shared_feature():
    _, combined = Plan._combine_device_inputs(
        device_inputs('features=["wifi","ble"]'),
        device_inputs('features=["ble","gpio"]'),
    )

    assert combined[0].device.features == ["wifi", "ble", "gpio"]


def test_combine_device_inputs_keeps_unqualified_inputs_without_roles():
    applicable, combined = Plan._combine_device_inputs(
        device_inputs("name=uno"), device_inputs("name=uno")
    )

    assert applicable
    assert [item.role for item in combined] == [None]


def test_combine_device_inputs_keeps_a_role_that_only_the_request_names():
    applicable, combined = Plan._combine_device_inputs(
        device_inputs("role=server,name=srv"),
        device_inputs("role=client,name=cl1"),
    )

    assert applicable
    assert [(item.role, item.device.name) for item in combined] == [
        ("server", "srv"),
        ("client", "cl1"),
    ]


def test_plan_build_suites_combines_cli_devices_with_role_requirements(
    role_plan, context, dev_list
):
    plan = Plan(
        [
            named(
                "roles",
                tests=role_plan.suites[0].tests,
                requires={
                    "device": [
                        {"role": "server", "features": ["wifi"]},
                        {"role": "client", "features": ["ble"]},
                    ]
                },
            )
        ]
    )

    (suite,) = build_suites(
        plan,
        context=context,
        devices=["role=server,name=uno", "role=client,name=nano"],
        dev_list=dev_list,
    )

    assert {
        role: [device.name for device in devices]
        for role, devices in suite.device_pool.items()
    } == {"server": ["uno"], "client": ["nano"]}


def test_plan_build_suites_skips_a_role_suite_when_one_role_conflicts(
    role_plan, context, dev_list
):
    plan = Plan(
        [
            named(
                "roles",
                tests=role_plan.suites[0].tests,
                requires={
                    "device": [
                        {"role": "server", "name": "uno"},
                        {"role": "client", "name": "nano"},
                    ]
                },
            )
        ]
    )

    suites = build_suites(
        plan,
        context=context,
        devices=["role=server,name=uno", "role=client,name=uno"],
        dev_list=dev_list,
    )

    assert suites == []


def test_plan_build_suites_skips_a_role_suite_when_a_role_has_no_matching_device(
    role_plan, context, dev_list
):
    plan = Plan(
        [
            named(
                "roles",
                tests=role_plan.suites[0].tests,
                requires={
                    "device": [
                        {"role": "server", "name": "uno"},
                        {"role": "client", "features": ["missing"]},
                    ]
                },
            )
        ]
    )

    assert build_suites(plan, context=context, dev_list=dev_list) == []
