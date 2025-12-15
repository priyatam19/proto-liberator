#!/bin/bash
set -e

# E2E Test Script for cJSON
# Runs the full pipeline: Proto Gen -> Wrapper Gen -> Build -> Fuzz

SCRIPT_DIR=$(dirname "$(realpath "$0")")
ROOT_DIR=$(dirname "$SCRIPT_DIR")
SRC_DIR="$ROOT_DIR/src"
EXTERNAL_DIR="$ROOT_DIR/external"
NANOPB_DIR="$EXTERNAL_DIR/nanopb"
OUTPUT_DIR="$ROOT_DIR/workdir/cjson_e2e"

# Inputs (Hardcoded for cJSON based on workspace info)
CONDITIONS_JSON="/home/priyatam/pin_compete/tools/liberator/analysis/cjson/work/apipass/conditions.json"
APIS_JSON="/home/priyatam/pin_compete/tools/liberator/analysis/cjson/work/apipass/apis_clang.json"
DRIVER_META="/home/priyatam/pin_compete/tools/liberator/workdir/cjson/metadata/driver0.meta"

mkdir -p "$OUTPUT_DIR"

echo "[E2E] Starting cJSON E2E Test..."

PYTHON_BIN="/home/priyatam/binaryninja/binaryninja/bn_venv/bin/python3"

# 1. Generate Protobuf Schema
echo "[E2E] Generating Schema..."
"$PYTHON_BIN" "$SRC_DIR/proto_generator.py" \
    --conditions "$CONDITIONS_JSON" \
    --apis "$APIS_JSON" \
    --output "$OUTPUT_DIR/cjson.proto" \
    --library cjson

# 2. Generate Protobuf Bindings (using nanopb)
echo "[E2E] Generating Bindings..."
if [ ! -d "$NANOPB_DIR" ]; then
    echo "Error: nanopb not found at $NANOPB_DIR"
    exit 1
fi

# Setup nanopb generator
export PATH="$NANOPB_DIR/generator:$PATH"
# Ensure protoc can find nanopb plugin dependencies if needed
# But nanopb generator is python script.
# We might need to install protobuf in the venv for nanopb generator to work.

protoc --proto_path="$OUTPUT_DIR" \
       --proto_path="$NANOPB_DIR/generator/proto" \
       --nanopb_out="$OUTPUT_DIR" \
       "$OUTPUT_DIR/cjson.proto"

# 3. Generate Harness
echo "[E2E] Generating Harness..."
"$PYTHON_BIN" "$SRC_DIR/wrapper_generator.py" \
    --proto "$OUTPUT_DIR/cjson.proto" \
    --driver "$DRIVER_META" \
    --conditions "$CONDITIONS_JSON" \
    --output "$OUTPUT_DIR/harness.c" \
    --package cjson_fuzzer

# 4. Compile
echo "[E2E] Compiling..."
# Check for clang
if ! command -v clang >/dev/null 2>&1; then
    echo "Error: clang not found"
    exit 1
fi

# We need libFuzzer. Assuming -fsanitize=fuzzer works.
# Also need to include nanopb sources.
clang -g -O1 -fsanitize=fuzzer,address \
    -DPB_FIELD_32BIT \
    -I"$OUTPUT_DIR" -I"$NANOPB_DIR" \
    "$OUTPUT_DIR/harness.c" \
    "$OUTPUT_DIR/cjson.pb.c" \
    "$NANOPB_DIR/pb_common.c" \
    "$NANOPB_DIR/pb_decode.c" \
    "$NANOPB_DIR/pb_encode.c" \
    -o "$OUTPUT_DIR/fuzzer"

echo "[E2E] Compilation successful!"

# 5. Run Fuzzer
echo "[E2E] Running Fuzzer (100 runs)..."
"$OUTPUT_DIR/fuzzer" -runs=100

echo "[E2E] Test Passed!"
