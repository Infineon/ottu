"""Tests for suite inputs, device resolution and the suite builder."""

from pathlib import Path

import pytest
from ottu.device import (
    Device,
    DeviceAccessSerial,
    DeviceInput,
)
from ottu.suite import (
    RoleCount,
    SuiteBuilder,
    SuiteDeviceInput,
    SuiteDeviceResolver,
    SuiteDistributed,
    SuiteInput,
    SuiteInputValidator,
    SuiteOpts,
    SuiteReplicated,
    SuiteRole,
    SuiteRoleDeviceResolver,
    SuiteSequential,
)
from ottu.test import Test, TestOpts, TestPath
from ottu.test_path import TestPathContext, TestPathInput


def suite_device_input(role=None, **values):
    """Create a suite selector from its role and device fields."""
    return SuiteDeviceInput(role=role, device=DeviceInput(**values))


def from_inputs(
    tests,
    device_inputs=(),
    count=None,
    available_devices=(),
    jobs=1,
    *,
    name=None,
    observers=(),
):
    """Create a suite from resolved device candidates."""
    options = SuiteOpts(jobs=jobs, count=1 if count is None else count)
    resolver = (
        SuiteRoleDeviceResolver
        if any(test.options.role is not None for test in tests)
        else SuiteDeviceResolver
    )
    device_pool = resolver.resolve(
        tests,
        device_inputs,
        available_devices,
        options,
    )
    return SuiteBuilder._suite_class(tests, options)(
        name=name,
        tests=list(tests),
        device_pool=device_pool,
        options=options,
        observers=tuple(observers),
    )


def request_test(name, role=None):
    return Test(
        TestPath(Path(name), Path(name), None, name),
        options=TestOpts(role=role),
    )


def catalog_device(name, port):
    return Device(name=name, access=DeviceAccessSerial(address=port))


def test_suite_input_validator_rejects_empty_role_counts(tmp_path):
    with pytest.raises(ValueError, match="role counts must not be empty"):
        SuiteInputValidator.validate(
            TestPathContext(working_dir=tmp_path),
            SuiteInput(count_input=()),
        )


def test_suite_device_resolver_requires_a_request_or_available_devices():
    with pytest.raises(ValueError, match="At least one device is required"):
        SuiteDeviceResolver.resolve((), (), (), SuiteOpts())


def test_role_device_resolver_keeps_role_association_in_the_pool():
    pools = SuiteRoleDeviceResolver.resolve(
        [request_test("server.py", "server")],
        (suite_device_input("server", name="board-1"),),
        (),
        SuiteOpts(),
    )

    [device] = pools["server"]

    assert device.name == "board-1"


def test_suite_device_resolver_constructs_requested_identities_without_a_catalog():
    pool = SuiteDeviceResolver.resolve(
        (),
        (suite_device_input(identifier="not-in-a-catalog"),),
        (),
        SuiteOpts(),
    )

    assert [device.name for device in pool[None]] == ["not-in-a-catalog"]


def test_suite_device_resolver_requires_an_identity_without_a_catalog():
    with pytest.raises(ValueError, match="device identity is required"):
        SuiteDeviceResolver.resolve(
            (),
            (suite_device_input(features=["wifi"]),),
            (),
            SuiteOpts(),
        )


def test_suite_device_resolver_keeps_candidates_without_connectivity_checks(
    monkeypatch,
):
    monkeypatch.setattr(
        Device,
        "is_connected",
        lambda self: pytest.fail("the resolver must not check connectivity"),
    )
    available = tuple(
        catalog_device(name, f"/dev/ttyUSB{i}") for i, name in enumerate("abc")
    )

    pool = SuiteDeviceResolver.resolve((), (), available, SuiteOpts(jobs=2))

    assert [device.name for device in pool[None]] == ["a", "b", "c"]


def test_suite_device_resolver_rejects_insufficient_candidates():
    available = tuple(
        catalog_device(name, f"/dev/ttyUSB{i}") for i, name in enumerate("abc")
    )

    with pytest.raises(ValueError, match="Suite needs 4 devices, but only 3 matched"):
        SuiteDeviceResolver.resolve((), (), available, SuiteOpts(jobs=2, count=2))


def test_role_device_resolver_rejects_insufficient_candidates():
    with pytest.raises(
        ValueError, match="Role 'client' needs 2 devices, but only 1 matched"
    ):
        SuiteRoleDeviceResolver.resolve(
            [request_test("client.py", "client")],
            (suite_device_input("client", name="board"),),
            (),
            SuiteOpts(count=(RoleCount(role="client", count=2),)),
        )


def test_suite_builder_defers_connectivity_checks_until_execution(
    tmp_path, monkeypatch
):
    (tmp_path / "a.py").touch()
    dev_list = tmp_path / "devices.yaml"
    dev_list.write_text(
        "version: 1\ndevices:\n  - name: board\n    uid: abc123\n",
        encoding="utf-8",
    )
    checked = []
    monkeypatch.setattr(
        Device,
        "is_connected",
        lambda self: checked.append(self.name) or False,
    )
    monkeypatch.setattr(SuiteSequential, "_runner", lambda self: [])

    suite = SuiteBuilder.build(
        TestPathContext(working_dir=tmp_path),
        SuiteInput(test_inputs=(TestPathInput(test_selector="a.py"),)),
        dev_list=dev_list,
    )

    assert checked == []
    assert [device.name for device in suite.device_pool[None]] == ["board"]
    with pytest.raises(ValueError, match="needs 1 connected devices"):
        suite.run()
    assert checked == ["board"]


@pytest.mark.parametrize(
    ("options", "role", "expected_class"),
    [
        (SuiteOpts(), None, SuiteSequential),
        (SuiteOpts(jobs=2), None, SuiteDistributed),
        (SuiteOpts(jobs=2), "server", SuiteRole),
        (SuiteOpts(count=2), None, SuiteReplicated),
        (SuiteOpts(count=(RoleCount(role="client", count=2),)), None, SuiteSequential),
    ],
)
def test_suite_builder_selects_the_suite_class(options, role, expected_class):
    suite_class = SuiteBuilder._suite_class([request_test("a.py", role)], options)

    assert suite_class is expected_class


def test_from_inputs_builds_a_sequential_suite_without_a_catalog():
    suite = from_inputs([request_test("a.py")], [suite_device_input(name="board-1")])

    assert isinstance(suite, SuiteSequential)
    assert suite.options == SuiteOpts(1)
    assert [device.name for device in suite.device_pool[None]] == ["board-1"]


def test_from_inputs_names_a_device_by_a_bare_identifier():
    suite = from_inputs(
        [request_test("a.py")],
        [suite_device_input(identifier="/dev/ttyUSB0")],
    )

    assert suite.device_pool[None][0].access == DeviceAccessSerial(
        address="/dev/ttyUSB0"
    )


def test_from_inputs_requires_a_device_without_a_catalog():
    with pytest.raises(ValueError, match="At least one device is required"):
        from_inputs([request_test("a.py")])


def test_from_inputs_takes_the_first_matches_of_the_filters(connected):
    available = [
        catalog_device("a", "/dev/ttyUSB0"),
        catalog_device("b", "/dev/ttyUSB1"),
        catalog_device("c", "/dev/ttyUSB2"),
    ]
    suite = from_inputs(
        [request_test("a.py")],
        [suite_device_input(name="c"), suite_device_input(name="a")],
        2,
        available,
    )

    assert [device.name for device in suite.device_pool[None]] == ["c", "a"]
    assert isinstance(suite, SuiteReplicated)
    assert suite.options.count == 2


def test_from_inputs_without_filters_takes_any_available_device(connected):
    available = [
        catalog_device("a", "/dev/ttyUSB0"),
        catalog_device("b", "/dev/ttyUSB1"),
    ]

    suite = from_inputs([request_test("a.py")], available_devices=available)

    assert [device.name for device in suite.device_pool[None]] == ["a", "b"]
    assert [device.name for device in suite._book_devices()] == ["a"]


def test_from_inputs_matches_a_bare_identifier_against_the_catalog(connected):
    available = [
        catalog_device("a", "/dev/ttyUSB0"),
        catalog_device("b", "/dev/ttyUSB1"),
    ]
    suite = from_inputs(
        [request_test("a.py")],
        [suite_device_input(identifier="/dev/ttyUSB1")],
        available_devices=available,
    )

    assert [device.name for device in suite.device_pool[None]] == ["b"]


def test_from_inputs_ignores_the_devices_that_are_not_connected(monkeypatch):
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected", lambda self: False
    )
    available = [catalog_device("a", "/dev/ttyUSB0")]

    suite = from_inputs([request_test("a.py")], available_devices=available)

    assert [device.name for device in suite.device_pool[None]] == ["a"]
    with pytest.raises(ValueError, match="needs 1 connected devices"):
        suite._book_devices()


def test_from_inputs_distributes_jobs_with_the_devices_they_need(connected):
    available = [
        catalog_device(name, f"/dev/ttyUSB{i}") for i, name in enumerate("abcd")
    ]

    suite = from_inputs(
        [request_test("a.py")],
        count=2,
        available_devices=available,
        jobs=2,
    )

    assert isinstance(suite, SuiteDistributed)
    assert [device.name for device in suite.device_pool[None]] == ["a", "b", "c", "d"]


def test_from_inputs_builds_a_role_suite_with_reserved_devices(connected):
    available = [
        catalog_device("a", "/dev/ttyUSB0"),
        catalog_device("b", "/dev/ttyUSB1"),
    ]
    suite = from_inputs(
        [request_test("s.py", "server"), request_test("c.py", "client")],
        [suite_device_input("server"), suite_device_input("client")],
        available_devices=available,
    )
    booked = suite._book_devices()

    assert isinstance(suite, SuiteRole)
    assert [device.name for device in booked] == ["a", "b"]


def test_from_inputs_books_a_role_device_for_each_count(connected):
    available = [
        catalog_device(name, f"/dev/ttyUSB{i}") for i, name in enumerate("abc")
    ]
    suite = from_inputs(
        [request_test("c.py", "client")],
        [suite_device_input("client")],
        (RoleCount(role="client", count=2),),
        available,
    )

    assert [device.name for device in suite._book_devices()] == ["a", "b"]


def test_from_inputs_assigns_connected_candidates_at_execution(monkeypatch):
    monkeypatch.setattr(
        "ottu.device.DeviceAccessSerial.is_connected",
        lambda self: self.address == "/dev/ttyUSB1",
    )
    available = [
        catalog_device("a", "/dev/ttyUSB0"),
        catalog_device("b", "/dev/ttyUSB1"),
    ]
    suite = from_inputs([request_test("a.py")], available_devices=available)

    assert [device.name for device in suite.device_pool[None]] == ["a", "b"]
    assert [device.name for device in suite._book_devices()] == ["b"]


def test_from_inputs_rejects_a_role_without_enough_devices(connected):
    available = [catalog_device("a", "/dev/ttyUSB0")]

    with pytest.raises(ValueError, match="Role 'client' needs 1 connected devices"):
        from_inputs(
            [request_test("s.py", "server"), request_test("c.py", "client")],
            [suite_device_input("server"), suite_device_input("client")],
            available_devices=available,
        )._book_devices()


def test_from_inputs_rejects_a_role_without_enough_given_devices():
    with pytest.raises(ValueError, match="device identity is required"):
        from_inputs(
            [request_test("c.py", "client")],
            [suite_device_input("client")],
            (RoleCount(role="client", count=2),),
        )


def test_from_inputs_names_the_suite_and_keeps_the_observers():
    observer = object()

    suite = from_inputs(
        [request_test("a.py")],
        [suite_device_input(name="a")],
        name="Smoke",
        observers=[observer],
    )

    assert suite.name == "Smoke"
    assert suite.observers == (observer,)
