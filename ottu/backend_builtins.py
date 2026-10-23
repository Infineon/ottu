"""Built-in backend definitions shipped with Ottu."""

BACKEND_BUILTINS = {
    "arduino-cli": {
        "build": (
            "arduino-cli compile -b {name}"
            ' --build-property "compiler.cpp.extra_flags={defines}" {test_path}'
        ),
        "program": "arduino-cli upload {test_path} -b {name} --port {address} ",
    },
    "debug": {
        "build": "sh -c 'sleep 3; echo build {device} {defines}'",
        "program": "sh -c 'sleep 3; echo program {device}'",
    },
}
