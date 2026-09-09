# Suite Modes

A suite mode describes how tests are assigned to devices and how they execute.
The CLI infers the mode from the user-provided test selectors and device options
before resolving devices or starting tests.

The six suite modes are `single`, `multi-sequential`, `single-repeated`,
`multi-repeated`, `multi-role`, and `multi-shared-load`.

This classification separates mode-specific argument parsing and validation
from execution. Each mode can select its own runner through a shared suite-runner
interface, allowing new modes to be added without changing existing runners.

## 1. Single

**Tests:** one test

**Devices:** one device

The test runs once on the selected device. This is the default mode for a
single test selector and one device. This mode is named `single`.

### CLI Criteria

- The positional test arguments contain exactly one argument.
- The argument is a file path.
- `count` is `1`, either explicitly or by default.

### Incompatible Arguments

None.

### Ignored Arguments

- `jobs`

### Option Combination Validation

- `exclude` is valid for this mode.

## 2. Multi-Sequential

**Tests:** several tests

**Devices:** one device

Tests run one after another on the same device, in input order. This mode is
named `multi-sequential`.

### CLI Criteria

- The positional test arguments resolve into a list of tests.
- `count` is `1`, either explicitly or by default.

### Incompatible Arguments

None.

### Ignored Arguments

- `jobs`

## 3. Single-Repeated

**Tests:** one test

**Devices:** several devices

The same test runs concurrently on each selected device. Every device receives
one independent execution of the test. This mode is named `single-repeated`.

### CLI Criteria

- The positional test arguments resolve into exactly one test.
- `count` is greater than `1`.

### Incompatible Arguments

None.

### Ignored Arguments

- `jobs`

### Option Validation

- `failed_only` selects the test only when it is marked as failed for the
    corresponding device from a previous run.
- `retry` applies independently to each device's execution of the repeated
    test.
- `exclude` is applied before replication. If it excludes the only selected
    test, the suite has no test to repeat and should report that condition
    explicitly.

## 4. Multi-Repeated

**Tests:** several tests

**Devices:** several devices

Each test runs concurrently across the requested devices, but tests execute in
sequential phases. The next test starts only after every replica of the current
test completes. This mode is named `multi-repeated`.

### CLI Criteria

- The positional test arguments resolve into several tests.
- `count` is greater than `1`.
- `jobs` is `1`, either explicitly or by default.

### Incompatible Arguments

None.

### Option Validation

- `jobs > 1` selects `multi-shared-load` instead of this mode.
- `failed_only` is evaluated per test and device from previous results.
- `retry` applies independently to each device replica in the current phase.
- `exclude` is applied before the tests are divided into sequential phases.

## 5. Multi-Role

**Tests:** several tests

**Devices:** several devices

Each test is a named participant in a coordinated scenario. A role test can
specify its own device requirements, device count, and start sequence. The
runner assigns compatible devices to each role and starts the role tests in
parallel, subject to their configured sequence.

Examples of roles include `server`, `client`, and `sniffer`. This mode is named
`multi-role`.

### CLI Criteria

- Every positional test argument resolves to a single test file.
- Every positional test argument uses the `key=value` format, where the key is
    the role and the value is the test selector.
- `count` may be one direct integer applied to every role.
- When keyed counts are used, each count that is customized for a role uses the
    `role=count` format; roles without a keyed count default to `1`.
- The following arguments may use `key=value` or a comma-separated list of
    keyed values:
    - `count`
    - `device`
    - `setup`
    - `teardown`

### Incompatible Arguments

- `jobs`
- `exclude`

### Ignored Arguments

- `failed_only`
- `fail_policy`

## 6. Multi-Shared Load

**Tests:** several tests

**Devices:** several devices

All tests share the same device requirements. Each test runs once, and the
runner distributes tests across the available compatible devices. A device runs
only one assigned test at a time; tests may run concurrently on different
devices. This mode is named `multi-shared-load`.

### CLI Criteria

- The positional test arguments resolve into a list of tests.
- `jobs` is greater than `1`.

### Incompatible Arguments

None.

### Ignored Arguments

None.

## Logical Classification by Three Binary Inputs

A useful way to reason about the suite family is to treat the decision as a
three-bit classification problem:

- `test`: `single` or `multi`
- `device`: `sequential` or `parallel`
- `jobs`: `joint` or `distributed`

This gives a truth table with $2^3 = 8$ combinations. The public suite modes
are the meaningful combinations after collapsing the scheduling axis (`jobs`)
into the underlying execution family.

| test | device | jobs | Meaning | Public mode |
| --- | --- | --- | --- | --- |
| `single` | `sequential` | `joint` | One test, one device, no scheduling fan-out | `single` |
| `single` | `sequential` | `distributed` | One test, one device, but work is split across job groups | Same family as `single`; not a distinct public mode |
| `single` | `parallel` | `joint` | One test repeated across several devices | `single-repeated` |
| `single` | `parallel` | `distributed` | One test repeated across several devices with process fan-out | Same family as `single-repeated` |
| `multi` | `sequential` | `joint` | Several tests run in order on one device | `multi-sequential` |
| `multi` | `sequential` | `distributed` | Several tests, one device, but multiple job groups | Same family as `multi-sequential`; process fan-out only |
| `multi` | `parallel` | `joint` | Several tests, several devices, one joint execution schedule | `multi-repeated` |
| `multi` | `parallel` | `distributed` | Several tests, several devices, split across several job groups | `multi-shared-load`; role-qualified input stays in the `multi-role` family |

The important distinction is that `test` and `device` define the fundamental
suite family, while `jobs` describes how that family is scheduled. In other
words, `jobs` is a scheduling axis, not the primary mode axis.

The resulting public names are therefore:

- `single`
- `multi-sequential`
- `single-repeated`
- `multi-repeated`
- `multi-role`
- `multi-shared-load`

The `jobs` axis may add process-level concurrency, but it does not create a
separate suite family by itself. It changes the scheduler used inside the same
underlying test/device family.

## Mode Inference

Mode inference uses the number of requested tests, the number of selected
compatible devices, and whether tests have distinct role-specific device
requirements.

| Devices \\ Tests | One test | Several tests |
| --- | --- | --- |
| One device | **single** | **multi-sequential** |
| Several devices | **single-repeated** | **multi-repeated**, **multi-role**, or **multi-shared-load** |

For the several-tests/several-devices case:

- **multi-role**: tests have distinct device requirements and are assigned to named
    participants such as `server`, `client`, or `sniffer`.
- **multi-shared-load**: all tests have the same device requirements and are
    distributed across the available compatible devices.
- **multi-repeated**: every test uses the same replicated device
    count, but the tests execute one phase at a time in input order.

The mode determines which arguments are valid and which runner implementation
is selected. It does not resolve devices itself; device discovery and matching
remain a later step in suite construction.

## Mode Compatibility

The modes form an extension hierarchy rather than five unrelated execution
strategies.

| Mode | Extends | Distinguishing condition |
| --- | --- | --- |
| `single` | Base case | One test and one device |
| `multi-sequential` | `single` | Several tests and one device |
| `single-repeated` | `single` | One test and several devices |
| `multi-repeated` | `multi-sequential` + `single-repeated` | Several tests, several devices, `jobs=1` |
| `multi-shared-load` | Multi-test/multi-device family | Several tests, several devices, `jobs>1` |
| `multi-role` | Separate role-based branch | Role-qualified test arguments |

The following combinations are incompatible:

- Role-qualified and unqualified test arguments cannot be mixed.
- `multi-role` cannot use `jobs`.
- `multi-role` cannot use `exclude`.
- `multi-role` accepts either one scalar count for all roles or keyed counts
    such as `server=3`; keyed counts override the default count of `1` for the
    named roles.
- `multi-shared-load` requires `jobs>1`.
- `multi-repeated` requires `jobs=1` or the default value.
- `single-repeated` accepts only one test selector.
- `single` requires one test and one device.

The `jobs` value selects between the two multi-test/multi-device scheduling
modes:

```text
jobs=1  -> multi-repeated
jobs>1  -> multi-shared-load
```

`multi-role` is a separate execution family because it adds per-test roles and
may add different device requirements, setup, teardown, counts, and start
sequences.



## Extension Model

Each suite mode should implement the same runner interface. The suite selects a
runner after mode inference and input validation:

```python
class SuiteRunner(Protocol):
    def run(self, suite: Suite) -> None: ...
```

This keeps mode-specific scheduling, device assignment, and synchronization
isolated from common suite construction and result reporting.
