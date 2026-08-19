# ottu Use Cases

ottu (On-Target Testing Utility) is a command-line tool for running automated tests on embedded targets, selecting and managing devices, and collecting standardized test outputs across local and lab-managed hardware setups.

This document outlines all the use cases for the On-Target Testing Utility (ottu) CLI tool. These serve as the foundation for implementation.

## Table of Contents

- [0. Installing ottu](#0-installing-ottu)
- [0.1 Basic CLI Commands](#01-basic-cli-commands)
- [1. Running Tests on a Single Target Device](#1-running-tests-on-a-single-target-device)
- [1.2. Specifying the Target Device](#12-specifying-the-target-device)
- [2. Running Tests on Multiple Devices](#2-running-tests-on-multiple-devices)
- [3. Additional Test Options](#3-additional-test-options)
- [4. Running a Test Plan](#4-running-a-test-plan)
- [4.1 Test Plan Schema](#41-test-plan-schema)
- [5. Using and Managing Multiple Devices](#5-using-and-managing-multiple-devices)
- [6. Upcoming Topics (Upcoming Iterations)](#6-upcoming-topics-upcoming-iterations)

## 0. Installing ottu

ottu can be installed via pip or equivalent package manager:

```bash
pip install ottu
```
or via source:

```bash
git clone https://github.com/Infineon/ottu.git
cd ottu
pip install .
```

## 0.1 Basic CLI Commands

### 0.1.1 Show ottu Version

**Scenario:** A developer wants to check which ottu version is installed.

**Prerequisites:**
- ottu is installed and available in PATH.

**Command:**
```bash
ottu version
```

**Expected Outcome:**
- The CLI prints the installed ottu version.
- Command exits successfully.

### 0.1.2 Show Help

**Scenario:** A developer wants to see available commands and options.

**Prerequisites:**
- None.

**Command:**
```bash
ottu help
```

**Expected Outcome:**
- The CLI prints top-level usage information.
- Available commands and primary options are listed.
- Command exits successfully.

### 0.1.3 Show Command Help

**Scenario:** A developer wants to see options for a specific command.

**Prerequisites:**
- None.

**Command:**
```bash
ottu run --help
```

**Expected Outcome:**
- The CLI prints usage and options for `run`.
- Command exits successfully.

`--help` should be available for every ottu command.

## 1. Running Tests on a Single Target Device

**Scenario:** A developer wants to run a test or a set of tests on a connected device.

**Expected Outcome:**
- Tests are executed on the board
- Results are collected and displayed
- Exit code indicates pass/fail status

> [!NOTE]
> -- Feedback --
> - Failure reporting should go beyond pass/fail and include the execution phase and error reason when available, for example whether the problem occurred during flash, connect, test execution, or output parsing. See the specific discussion: [NikhitaR-IFX feedback](https://github.com/Infineon/ottu/pull/2#discussion_r3806069368).
> - Exit code behavior should be defined explicitly, for example 0 for all tests passed, 1 for one or more failed tests, and 2 for device errors. See the specific discussion: [IFX-Anusha exit-code feedback](https://github.com/Infineon/ottu/pull/2#discussion_r3811700737).

### 1.1. Choosing Which Tests to Run

#### 1.1.1 Running All Project Tests

**Prerequisites:**
- The user is in the root directory of a project which has a discoverable test path (e.g., `tests/` or `test/`).
- There are some tests available in the test path.
- The target device is connected and ready for testing, and a default device can be discovered without specifying any device info.

**Command** 

```bash
ottu run
```
 
If some tests need device requirements for them to run (i.e. they need a specific device or a specific mode), the tool will not try to discriminate if the target device satisfies those. Therefore, if the target device does not satisfy the requirements of a test, the test will fail

### 1.1.2 Running a Single Test

**Scenario:** A developer wants to run a specific test on a connected device.

**Prerequisites:**
 - The test path exists and contains the specific test.
 - The target device is connected and ready for testing.

**Command:**

```bash
ottu run test_name 
```

### 1.1.3 Running Multiple Tests

The following arguments should be supported to specify which tests to run:

#### 1.1.3.1 Multiple Test Names 

```bash
ottu run test1 test2 test3
```

#### 1.1.3.2 A Directory Containing Tests

```bash
ottu run tests_dir/
```

#### 1.1.3.3 Using a Glob Pattern

```bash
ottu run "tests_dir/test_*.py"
```

#### 1.1.3.4 A Combination of the Above

```bash
ottu run tests_dir/ test1 test2
```
#### 1.1.4 Tests Specification Options

##### 1.1.4.1 Excluding Tests

If a directory or the entire test suite is provided, and some tests are not to be run, the `--exclude` option can be used to specify which tests to exclude.
That can also be a test name, a directory or a glob pattern.

```bash
ottu run tests_dir/ --exclude test_dir/test_to_exclude.py
```

For multiple exclusions, the  `--exclude` option can be used multiple times.

```bash
ottu run tests_dir/ --exclude test_dir/test_to_exclude.py --exclude test_dir/test_feature_*.py
```

## 1.2. Specifying the Target Device

If the default device cannot be unambiguously automatically determined, the minimum required information to discover the device should be provided (e.g., `--port /dev/ttyUSB0`).

In order to make this reusable to many frameworks, we will use a generic `--device` option to specify device parameters.

The parameters will be then passed as a key-value pair, separated by `=`. For example:

```bash
ottu run --device port=/dev/ttyUSB0
```

If more than one parameter is needed, they can be separated by a comma. For example:

```bash
ottu run --device port=/dev/ttyUSB0,baud=9600
```

And double or single quotes can be used to wrap the entire value if it contains spaces or special characters. For example:

```bash
# Space in a value
ottu run --device 'name=Board A,port=/dev/ttyACM0'

# '#' would otherwise start a shell comment
ottu run --device 'name=CI runner #1,port=/dev/ttyACM0'

# Value contains a single quote
ottu run --device "name=Alice's board,port=/dev/ttyACM0"
```

## 2. Running Tests on Multiple Devices

**Scenario:** A developer wants to run a test on multiple connected devices.

**Prerequisites:**
- The test path exists and contains the specific test.
- Multiple target devices are connected and ready for testing.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --device port=/dev/ttyUSB1 test_name
```

In this case, the test specification can only be a single test name, not a directory or a glob pattern. Because the same test is run on multiple devices, supporting multiple test selectors in this form would make execution semantics unclear.

**Expected Outcome:**
- Tests are executed on the board
- The results are collected and displayed for each device
- Exit code indicates pass/fail status for each device

### 2.1 Running a Different Test on Each Device

**Scenario:** A developer wants to run different tests on each device.

**Prerequisites:**
- The test path exists and contains the specific tests.
- Multiple target devices are connected and ready for testing.

**Command:**
```bash
ottu run \
  --device role=server,port=/dev/ttyUSB0 \
  --device role=client,port=/dev/ttyUSB1 \
  --role-test server=tests/test_server.py \
  --role-test client=tests/test_client.py
```

**Expected Outcome:**
- Tests are executed on the target boards.
- Results are collected and displayed for each role/device. 

- Exit code indicates pass/fail status for each device.

For this use case, tests should be provided as explicit test names, not directories or glob patterns.

### 2.2 Setting Temporal Dependency Between Role Tests

**Scenario:** A developer wants to configure the order in which role-specific tests run.

**Command:**
```bash
ottu run \
  --device role=server,port=/dev/ttyUSB0 \
  --device role=client,capabilities=wifi \
  --device role=sniffer,port=/dev/ttyUSB2 \
  --role-test server=tests/test_server.py \
  --role-test client=tests/test_client.py \
  --role-test sniffer=tests/test_sniffer.py \
  --role-start-order server=1 \
  --role-start-order client=2 \
  --role-start-order sniffer=3
```

Ordering rules:
- Lower `--role-start-order` starts first.
- `--role-start-order` must be a positive integer.
- Two role tests cannot share the same `--role-start-order` value.
- Role tests without `--role-start-order` run after positioned role tests, in declaration order.
- `--role-start-order` defines role start sequencing only; it does not require every role test to complete before the next role starts.
- The same role may be assigned additional later `--role-start-order` values to start that role again in a later phase.

> [!NOTE]
> -- Feedback --
> - Per-device result reporting should clearly identify which board instance failed in multi-device runs, especially when several devices share the same role.
> In a multi-device role run such as five `client` boards executing `test_client.py`, the user needs to know exactly which board instance failed. The run output should identify each instance clearly, for example:
>
> `client-01 /dev/ttyUSB1 PASS`
> `client-02 /dev/ttyUSB2 PASS`
> `client-03 /dev/ttyUSB3 FAIL`
>
> Without a per-instance result label, it is ambiguous which board to reset after a soft reset or a more destructive recovery action.
>
> See the related discussion: [NikhitaR-IFX comment on failed board identification](https://github.com/Infineon/ottu/pull/2#discussion_r3805897402)  

#### 2.2.1 Specifying Multiple Devices for a Role

**Scenario:** A developer wants to run a role test on multiple devices that share the same role.
**Command:**

```bash
ottu run \
  --device role=server,port=/dev/ttyUSB0 \
  --device role=client,capabilities=wifi \
  --role-test server=tests/test_server.py \
  --role-test client=tests/test_client.py \
  --role-start-order server=1 \
  --role-start-order client=2 \
  --count client=5
```

The `--count` option specifies how many devices should be used for a given role. In this case, the `client` role will be run on 5 devices that match the `client` role.

#### 2.2.2 Re-Running a Role in a Later Start Phase

**Scenario:** A developer wants one role to start again after an earlier start phase has completed.

**Command:**

```bash
ottu run \
  --device role=server,port=/dev/ttyUSB0 \
  --device role=client,port=/dev/ttyUSB1 \
  --role-test server=tests/test_server.py \
  --role-test client=tests/test_client.py \
  --role-start-order server=1 \
  --role-start-order client=2 \
  --role-start-order server=3
```

In this example, `server=3` means that the `server` role is started again in a later phase, after the earlier positioned starts have already completed.

Additional rules:
- Repeated `--role-start-order` entries for the same role are valid when each value is unique.
- Later values represent subsequent starts of the same role, not a redefinition of the role test.
- This is useful for staged flows where one role must participate again after an earlier exchange or setup phase.

> [!NOTE]
> -- Feedback --
> The semantics of a repeated role start order should be clarified: whether the role is re-executed from the start, a new process is started, or previous state is preserved. See the specific discussion: [IFX-Anusha role-repeat feedback](https://github.com/Infineon/ottu/pull/2#discussion_r3811774160).


### 2.3 Synchronizing Test Execution Between Devices

For target devices that do not implement a synchronization mechanism, the `ottu-target` C library provides an API that can be used to synchronize test execution between host and target.

More on this feature TBD.


# 3. Additional Test Options

## 3.1 Test Timeout

**Scenario:** A test can hang or take too long to run, 
and the developer wants to set a max timeout for the test to run.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --timeout 30 test_name
```


## 3.2 Test Retry

**Scenario:** A test can fail intermittently, and the developer wants to automatically retry the test a specified number of times.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --retry 3 test_name
```

If instead of a test, there are multiple tests, the retry will be applied to each test individually. For example, if there are 3 tests and the retry is set to 3, each test will be retried up to 3 times if it fails.


## 3.3 Setup Script

**Scenario:** A developer wants to run a setup script before running the tests.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --setup setup_script.py test_name
```

This setup script will run before each test when multiple 
tests are specified. If the setup script fails, the test will not run and the error will be reported (TBD).

If a hook should run once before each suite, the `--suite-setup` option can be used instead of `--setup`.

Based on the extension of the script, the tool will try to determine how to run it. For example, if the script is a Python script, it will be run with the Python interpreter. If the script is a shell script, it will be run with the shell interpreter.
The supported extensions are TBD, but at least `.py` and `.sh` should be supported.

If a space-separated string list is provided for the setup script, it will be executed as a command. For example:

```bash
ottu run --device port=/dev/ttyUSB0 --setup "python setup_script.py --arg1 value1" test_name
```

## 3.4 Teardown Script

**Scenario:** A developer wants to run a teardown script after running the tests.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --teardown teardown_script.py
```

This teardown script will run after each test when multiple tests are specified. If the teardown script fails, the error will be reported, but it will not affect the test result (TBD).

If a hook should run once after each suite, the `--suite-teardown` option can be used instead of `--teardown`.

As for setup scripts, based on the extension of the script, the tool will try to determine how to run it. For example, if the script is a Python script, it will be run with the Python interpreter. If the script is a shell script, it will be run with the shell interpreter.

If a space-separated string list is provided for the teardown script, it will be executed as a command. For example:
```bash
ottu run --device port=/dev/ttyUSB0 --teardown "python teardown_script.py --arg1 value1"
```
## 3.5 Run Tests from Another Directory

** Scenario:** A developer wants to run tests from a different directory than the current working directory.


**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --working-dir /path/to/test/d
```
The working directory is usually the root of the project, but it can be any directory that contains the tests to run.
The test name can be specified as a relative path from the working directory.

## 3.6 Dry Run

**Scenario:** A developer wants to see what tests would be run without actually running them.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --dry-run test_name
```

> [!NOTE]
> -- Feedback --
>  Dry-run behavior should be documented clearly: whether it validates configuration and discovery only or also includes readiness checks such as device availability and flashing. See the specific discussion: [IFX-Anusha dry-run feedback](https://github.com/Infineon/ottu/pull/2#discussion_r3811813749).

## 3.7 Log Level

**Scenario:** A developer wants to control the verbosity of test execution logs.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --log-level debug
```

**Expected Outcome:**
- The CLI emits logs according to the selected log level.
- Supported levels should include at least `debug`, `info`, `warning`, and `error`.

## 3.8. Logging

**Scenario:** A developer wants to log test execution details to a file.

The log can be used for debugging, auditing, or sharing with others. The log file can be specified with the `--log-file` option.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --log-file test_log.txt test_name
```
## 3.9. Output Format

**Scenario:** A developer wants to specify the output format of the test results.

```bash
ottu run --device port=/dev/ttyUSB0 --output-format json test_name
```

The supported output formats are TBD.
The format will be also evaluated based on the tap consumer. 

## 3.10 Save the Test Results to a File

**Scenario:** A developer wants to save the test results to a file for later analysis or reporting.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --output-save results.json test_name
```

The file will be overwritten if it already exists. If the file does not exist, it will be created.

## 3.11 Output Parser

**Scenario:** A developer wants to specify a custom output parser for the test results.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --output-parser unity test_name
```

Currently, the supported parsers are:
- `unity`: for Unity test framework
- `unittest`: for Python's built-in unittest framework
- `exp-match`: direct file comparison with expected output file. Regex matching might be considered.

### 3.11.1 Expected File Lookup for `exp-match`

When `--output-parser exp-match` is used, ottu should look for an expected output file in the same directory as the test file.

Default lookup rule:
- If the test file is `test_name.extension`, the expected file should be `test_name.extension.exp` in the same directory.

Example:
- `tests/test_login.txt` expects `tests/test_login.txt.exp`

If the expected output file does not follow that naming convention, a dedicated override flag can be used for that use case:

```bash
ottu run --device port=/dev/ttyUSB0 --output-parser exp-match --output-exp-file expected/test_login_golden.txt test_name
```


## 3.12 Parallel Test Execution

**Scenario:** A developer wants to run tests in parallel on multiple devices to speed up the testing process.

**Prerequisites**:
 - Only relevant for multiple tests and multiple devices. 
 - The devices must have shared resource manager enabled.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --device port=/dev/ttyUSB1 --jobs 2 test_name
```

Parallel execution is best understood as a job-based model rather than a device-only model. In general, a job is one runnable test target, and that job may require one device or several devices depending on the test. For example, in a fleet of equivalent boards, a set of board-agnostic tests can be scheduled in parallel across all available compatible devices. If `N` matching devices are available, ottu may dispatch up to `N` jobs concurrently, subject to the configured job limit and host resource constraints.

If a test requires more than one device, that test still counts as a single job that consumes the required device set.

## 3.13 Run failed tests only

**Scenario:** A developer wants to rerun only the tests that failed in the previous run.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --failed-only
```

> [!NOTE]
> -- Feedback --
> `--failed-only` should state whether it reruns only the most recent failed tests or all failed tests from the last attempt, and whether it reads from a saved results file. See the specific discussion: [IFX-Anusha failed-only feedback](https://github.com/Infineon/ottu/pull/2#discussion_r3811858908).

## 3.14 Test Result Directory

**Scenario:** Test outputs are stored in a default location, but a developer wants to choose where result artifacts are written.

**Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --output-dir out/test-results test_name
```

**Expected Outcome:**
- If `--output-dir` is not set, results are written to the default output location.
- If `--output-dir` is set, result artifacts are written under the specified directory.

## 3.15 Device Match Count

**Scenario:** A developer wants to run the same test on only a subset of devices that match a non-unique device selector.

**Command:**
```bash
ottu run --device "board=stm32f4" --count 2 test_name
```

**Expected Outcome:**
- The CLI selects up to `count` devices from the matched device set.
- `--count` must be a positive integer.
- `--count` is valid only when the device selector can match multiple devices.
- If the selector is uniquely identifying one device, using `--count` should be rejected.

## 3.16 CLI Short-Flag Summary 

Notes:
- Short flags are command-scoped.
- Reusing the same short flag across different commands is acceptable.

| Long option | Proposed short | Scope |
|---|---|---|
| `--help` | `-h` | all commands |
| `--device` | `-d` | run, list-devices, config |
| `--device-list` | `-m` | run |
| `--exclude` | `-x` | run |
| `--role-test` | `-R` | run |
| `--role-start-order` | `-O` | run |
| `--timeout` | `-t` | run |
| `--retry` | `-r` | run |
| `--setup` | `-s` | run |
| `--suite-setup` | `-S` | run |
| `--teardown` | `-u` | run |
| `--suite-teardown` | `-U` | run |
| `--working-dir` | `-C` | run |
| `--dry-run` | `-n` | run |
| `--log-level` | `-L` | run |
| `--log-file` | `-l` | run |
| `--output-format` | `-f` | run |
| `--output-exp-file` | `-e` | run |
| `--output-save` | `-o` | run |
| `--output-dir` | `-D` | run |
| `--output-parser` | `-p` | run |
| `--count` | `-c` | run |
| `--jobs` | `-j` | run |
| `--failed-only` | `-F` | run |
| `--plan` | `-P` | run |

# 4. Running a Test Plan

**Scenario:** A developer wants to define and run a test plan that specifies which tests to run. Running such list as arguments to the command line is not practical, and such test plan is provided as a configuration file.

**Prerequisites:**
- Test plan is defined in a configuration file (e.g., `test_plan.yaml`)
- The target devices are connected and ready for testing.

** Command:**
```bash
ottu run --device port=/dev/ttyUSB0 --plan test_plan.yaml
```

**Expected Outcome:**
- Multiple tests executed sequentially
- Each test result logged
- Summary report generated

### 4.1 Test Plan Schema 

Based on the cli options, the test provides the following
schema:

```yaml
version: "1.0.0"

# Optional global execution root for relative paths
working-directory: .

# Optional global output defaults
output:
  dir: out/results

# Optional defaults applied to every test suite unless overridden
defaults:
  timeout: 30
  retry: 0
  dry-run: false
  log-level: info
  output:
    parser: unity
    format: tap
  jobs: 1
  suite-setup: scripts/suite_setup.py
  suite-teardown: scripts/suite_teardown.py

# Device inventory used by tests
device-list:
  - devices/boards.yaml
  - devices/lab-boards.yaml
devices:
  - name: STM32 Nucleo F429ZI
    port: /dev/ttyUSB0
    baud: 115200
  - name: RP2040 Pico W
    port: /dev/ttyUSB1
    baud: 115200

# Test suites to execute
suites:
  - name: smoke-controller
    tests:
      - tests/test_controller.py
    count: 2
    requires:
      device:
        name: STM32 Nucleo F429ZI

  - name: integration-link
    tests:
      - tests/test_link.py
      - tests/integration/
      - "tests/**/test_link_*.py"
    exclude:
      - "tests/**/test_link_flaky_*.py"
    requires:
      libs:
        - unity@10.5
        - ArduinoJSON
      device:
        capabilities: [uart, sync]
      exclude:
        - device:
            name: RP2040 Pico W RevA
    timeout: 60
    retry: 2
    log-level: debug
    setup: "python scripts/setup_link.py"
    teardown:
      - sh
      - scripts/teardown_link.sh
    output:
      dir: out/integration-link
      save: out/link_results.json
      format: json

  - name: server-client-split
    tests:
      - role: server
        order: 1
        test: tests/test_server.py
        count: 1
      - role: client
        order: 2
        test: tests/test_client.py
        count: 4
    requires:
      device:
        - role: server
          name: STM32 Nucleo F429ZI
          capabilities: [tcp-server]
        - role: client
          name: RP2040 Pico W
    output:
      parser: unittest
```

#### 4.1.1 Top-Level Keys

- `version`: Schema version as SemVer string. Start with `"1.0.0"`.
- `working-directory`: Root path used to resolve relative paths for tests, scripts, and outputs (including `output.dir`).
- `output`: Global defaults for output options.
- `defaults`: Global defaults for suite execution options and suite lifecycle hooks.
  This section is optional; if omitted, built-in tool defaults are used.
- `device-list`: Optional path to an external device list file.
- `devices`: Optional inline list of device entries.
- `suites`: Ordered list of test-suite entries.
  Default execution order is declaration order.

A test suite is an ordered collection of test selectors and execution metadata that is treated as one logical run. It may resolve to one or many concrete test cases, but it is configured, scheduled, and reported as a single execution unit.

#### 4.1.2 Device Inventory

`device-list` and `devices` are alternative sources for the device inventory:

- `device-list`: Path or list of paths to device inventory files (for example `devices.yaml` or `[devices.yaml, lab_devices.yaml]`).
- `devices`: Inline list of device entries.

Each entry under `devices` supports:

- `name`: Hardware/device name (not a role), used for references in tests.
- Additional device fields are defined by the device/backend layer and are intentionally not detailed in this section.

Device source rules:

- Relative `device-list` paths are resolved against `working-directory`.
- If `device-list` is a list, file entries are merged in declaration order.
- CLI `--device-list` overrides schema `device-list`.
- If both `device-list` and `devices` are provided, `device-list` takes precedence.
- If no device list source is provided, the inline `devices` list is used.

#### 4.1.3 Test Suite Dictionary

Each item under `suites` supports:

- `name`: Optional suite name used in logs and reports.
- `tests`: Test selector list for the suite.
  - String form: one selector.
  - List form: list of selector strings.
  - Role-aware list form: list of dictionaries with `role` + `test` (+ optional per-item `order`).
- `requires`: Requirement dictionary for software and device selection.
- `exclude`: Selector list removed from the expanded suite `tests` set.
- `timeout`: Max seconds for this test.
- `retry`: Retry count for this test.
- `dry-run`: If true, resolve and print actions only.
- `log-level`: Logging verbosity for this test.
- `jobs`: Number of parallel jobs for this test scope.
- `log-file`: Per-test logging destination path.
- `output`: Output dictionary.
- `count`: Number of device instances to run this test on.
- `setup`: Hook before each test case.
- `teardown`: Hook after each test case.
- `suite-setup`: Hook run once before the suite.
- `suite-teardown`: Hook run once after the suite.

Notes:

- Use `test` for both standard and role-specific selection.
- Role-aware `test` items must include:
  - `role`: Role name.
  - `test`: One explicit test path/name string.
- Role-aware `test` items may include:
  - `order`: Optional positive integer sequence between role test items.
  - `count`: Optional positive integer number of devices for that role (defaults to `1`).
- Role-aware `test` lists support exactly one test per role (roles must be unique in the list).
- If per-item `order` is omitted, role-aware items run in declaration order.
- For non-role tests (`test` string or selector list), test-entry `count` is valid at the same level as `test`.
- For role-aware tests (`test` role-item list), use per-item `count`; test-entry `count` is not used.
- `defaults.log-level` sets the default logging verbosity for all tests.
- Test-entry `log-level` overrides `defaults.log-level` for that test only.
- `defaults.output.parser` sets the default parser for all tests.
- `output.parser` overrides `defaults.output.parser` for that test only.
- `defaults.output.format` sets the default output format for all tests.
- `output.format` overrides `defaults.output.format` for that test only.
- Top-level `output.dir` sets the default artifact directory for all tests.
- Test-entry `output.dir` overrides top-level `output.dir` for that test only.
- Relative `output.dir` values are resolved against `working-directory`.

`requires` dictionary:

- `libs`: Flat library list. Each entry can be a name (`lib`) or a pinned selector (`lib@version`).
- `device`: Device selection requirements.
- `exclude`: Optional list of exclusion rules applied after positive matching.

Library resolution is toolchain-specific: each backend decides how to resolve and apply `libs` entries during build and/or runtime.

`requires.device` supports one device filter dictionary or a list of device filter dictionaries.

Device filter keys:

- `role`: Role selector for role-aware tests.
  - String form: exact include match, for example `role: server`.
- `name`: Device name selector.
  - String form: exact include match, for example `name: STM32-Nucleo`.
- `capabilities`: Required device capability selector.
  - String form: one required capability.
  - List form: all listed capabilities are required.

Device name examples:

- Include only one name:
  - `name: STM32-Nucleo`

Role requirement example:

- Bind a role-aware test item to a specific role/device filter:
  - `role: server`
  - `name: STM32-Nucleo`

Role count example (role-aware test item scope):

- Request one server and four clients:
  - `test:`
  - `  - { role: server, test: tests/test_server.py, count: 1 }`
  - `  - { role: client, test: tests/test_client.py, count: 4 }`

Non-role count example (test-entry scope):

- Run one test on three matching devices:
  - `test: tests/test_smoke.py`
  - `count: 3`

Capabilities example:

- Require one capability:
  - `capabilities: uart`
- Require multiple capabilities:
  - `capabilities: [uart, sync]`
  - or:
  ```yaml
  capabilities:
    - uart
    - sync
  ```

`requires.exclude` rule examples:

- Exclude specific devices by name:
  - `exclude:`
  - `  - device: { name: STM32-Nucleo-RevA }`
  - `  - device: { name: RP2040 Pico W RevA }`
- Future rule types can be added as additional keys per rule item.

Test selector forms:

- String/list selectors:
  - Exact test name or file path.
  - Directory path.
  - Wildcard glob path (for example `tests/**/test_*.py`).
- Role-aware list selector:
  - Each item is `{ role: <role-name>, test: <test-selector>, order?: <int>, count?: <int> }`.
- `exclude` applies after test selector expansion.

Test selector list behavior:

- List items may mix exact tests, directories, and wildcard globs.
- The resolver expands all entries and executes the final merged set.

#### 4.1.4 Hook Dictionary

Hook keys (`suite-setup`, `suite-teardown`, `setup`, `teardown`) support these forms. When defined under `defaults`, they apply to every suite unless overridden by a suite entry.

- String form: command line or script path.
- List form: argv list, each token as one item.

Hook constraints:

- Empty string/list values are invalid.

#### 4.1.5 Output Dictionary

`output` supports:

- `save`: Path to write structured results.
- `parser`: Output parser key.
- `format`: Output format key.
- `dir`: Directory for test result artifacts.

#### 4.1.6 Logging Dictionary

`logging` supports:

- `file`: Path for raw/log output.

#### 4.1.7 Supported Value Dictionaries

`output.parser` values:

- `unity`
- `unittest`
- `exp-match`

`output.format` values:

- `tap`
- `json`
- `text`
- `junit`

Device field value dictionaries (for example `connection`) are defined in the device schema documentation.

#### 4.1.8 Minimal and Multi-Role Examples

Minimal single-device plan:

```yaml
version: "1.0.0"
devices:
  - name: STM32 Nucleo F429ZI
    port: /dev/ttyUSB0
tests:
  - test: tests/test_smoke.py
    count: 2
    output:
      dir: out/smoke
    requires:
      device:
        name: STM32 Nucleo F429ZI
```

Multi-role split-test plan:

```yaml
version: "1.0.0"
working-directory: .
devices:
  - name: ESP32 DevKitC
    port: /dev/ttyUSB0
  - name: RP2040 Pico
    port: /dev/ttyUSB1
tests:
  - name: gw-client-handshake
    test:
      - role: gateway
        order: 1
        test: tests/test_gateway.py
        count: 1
      - role: client
        order: 2
        test: tests/test_client.py
        count: 2
    exclude:
      - tests/experimental/**
    requires:
      libs:
        - unittest
      exclude:
        - device:
            name: RP2040 Pico RevA
      device:
        - role: gateway
          name: ESP32 DevKitC
        - role: client
          name: RP2040 Pico
    timeout: 90
    retry: 1
    output:
      parser: unity
      format: json
      save: out/gw_client.json
```

# 5. Using and Managing Multiple Devices

Up to this point the use cases have focused on the tests on a limited set of devices. 
In order to support more complex scenarios, we need to provide a way to manage the devices and their characteristics. This will allow the user to configure the devices before running the tests, and also to query the devices for their characteristics.

The device management will be handled by the library `etdevs` (Embedded Test Devices). This library will provide a way to discover the devices, and to query and configure their characteristics. The library will be agnostic to the underlying hardware and software, allowing it to work with a variety of devices and test frameworks.

## 5.1. Run Tests on Devices from a Device List File

**Scenario:** The user wants to run tests and provide a list of available devices in a file, instead of specifying them one by one in the command line. This is useful when the user has a large number of devices, and wants to avoid specifying them all in the command line.

Provide the device list through the `--device-list` option.

**Prerequisites:**
- Device list file available (e.g., `devices.yaml`)

**Command:**
```bash
ottu run --device-list devices.yaml
```

**Expected Outcome:**
- Devices configured according to the file
- Device characteristics updated

## 5.2 Filtering Devices by Characteristics

**Scenario:** The user wants to filter the available devices based on their characteristics, given an available device list. 

**Prerequisites:**
- Device list file available (e.g., `devices.yaml`)
- Device characteristics defined in the file

**Command:**
```bash
ottu run --device capabilities=wifi --device-list devices.yaml test_name
``` 

**Expected Outcome:**
- Looks for a device matching the specified characteristics in the device list
- Tests are executed on a matching device
- Results are collected and displayed

## 5.3 Device Management

These features will be provided by `etdevs` library, which will provide a way to query and configure the devices before running the tests. The library will be agnostic to the underlying hardware and software, allowing it to work with a variety of devices and test frameworks.

It will support the following features:
- List all the available devices and their characteristics
- Query and filter devices based on their characteristics
- Configure device characteristics before running the tests

# 6. Upcoming Topics (Upcoming Iterations)

## 6.1 Project Configuration

**Scenario**. The user wants to configure the project settings, such as test paths, default device parameters, and output directories.

**Prerequisites:**
- An existing project to run tests on.

**Command:**
```bash
ottu config ... (TBD)
```

## 6.2 Toolchain Support

We will need at some point certain toolchain support params like:
- intermediate process configuration options (build, flash, connect, run, collect results)
- Specifying tools, etc.
- Run only partial step of the test run (build, flash, connect, run, collect results  )

This is TBD and will depend on the toolchain used for the tests. The toolchain support will be provided by the `etdevs` library, which will provide a way to configure the toolchain parameters before running the tests.

## 6.3 Access to Remote Devices

**Scenario:** The user wants to run tests on a device that is not directly connected to the host, but is accessible via network. This is useful when the device is located in a different location, or when the device is not directly accessible from the host.

**Prerequisites:**
- Board has network connectivity
- Network configuration available
- A shared device management system (e.g., a lab-grid) is available to manage the devices and their characteristics.

**Command:**
```bash
ottu run --device name=KIT_PSE84_AI --remote TBD
```

**Expected Outcome:**
- Connection established via network
- Tests run over network
- Results collected and displayed

---

## 6.4 Additional Device Interfaces

**Scenario:** The device supports additional interfaces for communication, such as USB. 

**Prerequisites:**
- Board has USB support
- USB driver available

**Command:**
```bash
ottu run --device usb-vid=0x1234,usb-pid=0x5678
```

**Expected Outcome:**
- USB connection established
- Tests run over USB

This is something that belongs to the device management library, and will be handled by the `etdevs` library. The `etdevs` library will provide a way to configure the device interfaces before running the tests.

## 6.5. Power Cycling and Reset of Devices

**Scenario:** The user wants to power cycle or reset the device before running the tests. This is useful when the device is in an unknown state, or when the device needs to be reset to a known state before running the tests.

**Prerequisites:**
- Board has power cycling or reset support (switchable)
- Power cycling or reset driver available
- A shared device management system (e.g., a lab-grid) is available to manage the devices and their characteristics.

**Command:**
```bash
ottu run --device name=KIT_PSE84_AI --reset <mode> 
```

**Expected Outcome:**
- Device is reset or power cycled
- Tests run on the device
- Results collected and displayed

## 6.6 Fail Policy Strategy

**Scenario:** The user wants to define a fail policy strategy for the tests. This is useful when the user wants to define how the tests should behave when a test fails, such as stopping the test run, or continuing with the next test.

**Prerequisites:**
- A fail policy strategy defined in the test configuration

**Command:**
```bash
ottu run --fail-policy stop-on-failure
```
Some options:
- `stop-on-failure`: Stop the test run on the first failure
- `continue-on-failure`: Continue the test run even if a test fails
- `retry-on-failure`: Retry the test a specified number of times on failure

**Expected Outcome:**
- Tests stop on the first failure
- Results collected and displayed

# General Feedback

Use this section to capture cross-cutting comments, open questions, and design notes that should not be lost while discussing specific use cases.

This section summarizes the main design points relevant to the overall device and execution model.

> [!NOTE]
> - Provide `alias` key for unique user-friendly names of devices . 
> - Document how to register devices and run the first first test.
> 
> See the specific discussion: [NikhitaR-IFX feedback](https://github.com/Infineon/ottu/pull/2#discussion_r3806069368).


> [!NOTE]
> - Clarify case-sensitivity (for example `server` vs `Sever`). See the specific discussion: [IFX-Anusha role-name feedback](https://github.com/Infineon/ottu/pull/2#discussion_r3811747387).

