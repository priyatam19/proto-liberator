#!/bin/bash
set -e

# Test script for verifying harness generation and compilation
# Uses stubs to avoid external dependencies

TEST_DIR=$(dirname "$(realpath "$0")")
ROOT_DIR=$(dirname "$TEST_DIR")
SRC_DIR="$ROOT_DIR/src"
STUBS_DIR="$TEST_DIR/stubs"
OUTPUT_DIR="$TEST_DIR/output"

mkdir -p "$OUTPUT_DIR"

echo "[Test] Setting up test environment..."

# Ensure runtime Python deps are available (clean-machine friendly)
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" -c 'import jinja2' >/dev/null 2>&1; then
    echo "[Test] Installing runtime deps into a local venv..."
    VENV_DIR="$OUTPUT_DIR/venv"
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/python" -m pip -q install --upgrade pip >/dev/null
    "$VENV_DIR/bin/python" -m pip -q install jinja2 >/dev/null
    PYTHON_BIN="$VENV_DIR/bin/python"
fi

# Create dummy inputs
cat <<EOF > "$OUTPUT_DIR/conditions.json"
{
  "test_func": {
    "param_0": {
      "type_string": "%struct.foo*",
      "set_by": ["creator"],
      "access_type_set": [{"access": "read", "type_string": "%struct.foo*"}]
    },
    "param_1": {
      "type_string": "i8*",
      "is_array": true,
      "access_type_set": [{"access": "read", "type_string": "i8*"}]
    },
    "return": {
      "type_string": "i32",
      "access_type_set": [{"access": "read", "type_string": "i32"}]
    },
    "parameters": [
      { "name": "h", "type": "struct foo *" },
      { "name": "s", "type": "char *" }
    ]
  }
}
EOF

cat <<EOF > "$OUTPUT_DIR/driver.meta"
{
  "headers": ["test_lib.h"],
  "api_sequence": ["test_func"]
}
EOF

# Create dummy library header
cat <<EOF > "$OUTPUT_DIR/test_lib.h"
struct foo;
void test_func(struct foo *h, char *s);
EOF

# Create dummy protobuf header matching the provided --proto basename.
# wrapper_generator.py includes "{{ proto_stem }}.pb.h".
cp "$STUBS_DIR/input.pb.h" "$OUTPUT_DIR/dummy.pb.h"

# Generate Harness
echo "[Test] Generating harness..."
"$PYTHON_BIN" "$SRC_DIR/wrapper_generator.py" \
    --proto "dummy.proto" \
    --driver "$OUTPUT_DIR/driver.meta" \
    --conditions "$OUTPUT_DIR/conditions.json" \
    --output "$OUTPUT_DIR/harness.c"

# Compile
echo "[Test] Compiling harness..."
if command -v clang >/dev/null 2>&1; then
    clang -c -I"$STUBS_DIR" -I"$OUTPUT_DIR" "$OUTPUT_DIR/harness.c" -o "$OUTPUT_DIR/harness.o"
    echo "[Test] Compilation successful!"
else
    echo "[Test] clang not found, skipping compilation step."
fi
