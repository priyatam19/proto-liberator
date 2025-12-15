#!/bin/bash
set -e

# E2E Test Script for cJSON
# Runs the full pipeline: Proto Gen -> Nanopb bindings -> Wrapper Gen -> Build -> Run a deterministic seed

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

# Use an isolated venv under workdir so the test is reproducible even on a clean machine.
PYTHON_SYSTEM="${PYTHON_SYSTEM:-python3}"
VENV_DIR="$OUTPUT_DIR/venv"
if [ ! -x "$VENV_DIR/bin/python3" ]; then
  echo "[E2E] Creating venv: $VENV_DIR"
  "$PYTHON_SYSTEM" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python3" -m pip install --upgrade pip >/dev/null
  "$VENV_DIR/bin/python3" -m pip install -r "$ROOT_DIR/requirements.txt"
fi
PYTHON_BIN="$VENV_DIR/bin/python3"

# 1. Generate Protobuf Schema
echo "[E2E] Generating Schema..."
"$PYTHON_BIN" "$SRC_DIR/proto_generator.py" \
    --conditions "$CONDITIONS_JSON" \
    --apis "$APIS_JSON" \
    --output "$OUTPUT_DIR/cjson.proto" \
    --library cjson

# 2. Generate Protobuf Bindings (using nanopb)
echo "[E2E] Generating Bindings..."
if [ ! -f "$NANOPB_DIR/generator/proto/nanopb.proto" ]; then
    echo "[E2E] nanopb not found or not populated at $NANOPB_DIR"
    echo "[E2E] Run: ./scripts/build_dependencies.sh"
    exit 1
fi

# Use nanopb's protoc wrapper if available (recommended).
NANOPB_PROTOC="$NANOPB_DIR/generator/protoc"
if [ ! -x "$NANOPB_PROTOC" ]; then
    echo "[E2E] nanopb protoc wrapper not found at $NANOPB_PROTOC"
    echo "[E2E] Ensure nanopb is fully cloned (generator/protoc present)."
    exit 1
fi

"$NANOPB_PROTOC" \
  --nanopb_out="$OUTPUT_DIR" \
  -I"$OUTPUT_DIR" \
  "$OUTPUT_DIR/cjson.proto"

# 3. Generate Harness
echo "[E2E] Generating Harness..."
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

src = Path("/home/priyatam/pin_compete/tools/liberator/workdir/cjson/metadata/driver0.meta")
dst = Path("/home/priyatam/pin_compete/tools/proto-liberator/workdir/cjson_e2e/driver.meta")
data = json.loads(src.read_text())
data["headers"] = ["cjson/cJSON.h"]
dst.write_text(json.dumps(data))
print(f"[E2E] Wrote wrapper meta: {dst}")
PY

"$PYTHON_BIN" "$SRC_DIR/wrapper_generator.py" \
    --proto "$OUTPUT_DIR/cjson.proto" \
    --driver "$OUTPUT_DIR/driver.meta" \
    --conditions "$CONDITIONS_JSON" \
    --apis "$APIS_JSON" \
    --header "cjson/cJSON.h" \
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
# Also need to include nanopb sources and the built cJSON library.
CJSON_INC="/home/priyatam/pin_compete/tools/liberator/analysis/cjson/work/include"
CJSON_LIB="/home/priyatam/pin_compete/tools/liberator/analysis/cjson/work/lib/libcjson.a"
if [ ! -f "$CJSON_LIB" ]; then
    echo "Error: cJSON library not found at $CJSON_LIB"
    exit 1
fi

clang -g -O1 -fsanitize=fuzzer,address \
    -fno-pie -no-pie \
    -DPB_FIELD_32BIT \
    -I"$OUTPUT_DIR" -I"$NANOPB_DIR" -I"$CJSON_INC" \
    "$OUTPUT_DIR/harness.c" \
    "$OUTPUT_DIR/cjson.pb.c" \
    "$NANOPB_DIR/pb_common.c" \
    "$NANOPB_DIR/pb_decode.c" \
    "$NANOPB_DIR/pb_encode.c" \
    "$CJSON_LIB" \
    -o "$OUTPUT_DIR/fuzzer"

echo "[E2E] Compilation successful!"

# 5. Run a deterministic seed so pb_decode succeeds and the wrapper executes calls.
echo "[E2E] Running one deterministic seed..."
CORPUS_DIR="$OUTPUT_DIR/corpus"
rm -rf "$CORPUS_DIR"
mkdir -p "$CORPUS_DIR"
# Provide a minimal valid protobuf message so pb_decode succeeds deterministically.
# Field 1 (global_seed), varint wire type: key=0x08, value=0x00.
printf '\x08\x00' > "$CORPUS_DIR/seed_global_seed_0.bin"

"$OUTPUT_DIR/fuzzer" "$CORPUS_DIR" -runs=1

echo "[E2E] Test Passed!"
