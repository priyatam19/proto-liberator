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

# Create dummy inputs
cat <<EOF > "$OUTPUT_DIR/conditions.json"
{
  "test_func": {
    "parameters": [
      { "name": "param1", "type": "int" }
    ]
  }
}
EOF

cat <<EOF > "$OUTPUT_DIR/driver.meta"
{
  "headers": ["test_lib.h"]
}
EOF

# Create dummy library header
echo "void test_func(int param1);" > "$OUTPUT_DIR/test_lib.h"

# Generate Harness
echo "[Test] Generating harness..."
/home/priyatam/binaryninja/binaryninja/bn_venv/bin/python3 "$SRC_DIR/wrapper_generator.py" \
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
