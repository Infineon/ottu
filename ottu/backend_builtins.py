"""Built-in backend definitions shipped with Ottu."""

BACKEND_BUILTINS = {
    "arduino-cli": {
        "build": "arduino-cli compile -b {name} {test_path}",
        "program": "arduino-cli upload {test_path} -b {name} --port {port} ",
    },
    "debug": {
        "build": "sh -c 'sleep 3; echo build {device}'",
        "program": "sh -c 'sleep 3; echo program {device}'",
    },
}
