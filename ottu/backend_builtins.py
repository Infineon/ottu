"""Built-in backend definitions shipped with Ottu."""

BACKEND_BUILTINS = {
    "arduino-cli": {
        "build": "arduino-cli compile -b {name} {test_path}",
        "program": "arduino-cli upload {test_path} -b {name} --port {port} ",
    },
    "debug": {
        "build": "echo build {device}",
        "program": "echo program {device}",
    },
}
