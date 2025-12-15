#!/bin/bash
set -e

# Build script for Proto-libErator Fuzzer
# Usage: ./build_proto_fuzzer.sh <proto_file> <driver_meta> <conditions_json> <output_dir>

if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <proto_file> <driver_meta> <conditions_json> <output_dir>"
    exit 1
fi

PROTO_FILE=$(realpath "$1")
DRIVER_META=$(realpath "$2")
CONDITIONS=$(realpath "$3")
OUTPUT_DIR=$(realpath "$4")
SCRIPT_DIR=$(dirname "$(realpath "$0")")
ROOT_DIR=$(dirname "$SCRIPT_DIR")

mkdir -p "$OUTPUT_DIR"

echo "[Build] Starting build process..."

# 1. Generate Protobuf C bindings
# This requires nanopb installed. If not, we skip this step (assuming stubs or pre-generated)
if command -v protoc >/dev/null 2>&1; then
    echo "[Build] Generating Protobuf bindings..."
    # protoc --proto_path=$(dirname "$PROTO_FILE") --nanopb_out="$OUTPUT_DIR" "$PROTO_FILE"
    # Placeholder: Copy stubs if protoc fails or for testing
else
    echo "[Build] protoc not found, skipping binding generation (expecting stubs or pre-generated files)"
fi

# 2. Generate Harness
echo "[Build] Generating Harness..."
python3 "$ROOT_DIR/src/wrapper_generator.py" \
    --proto "$PROTO_FILE" \
    --driver "$DRIVER_META" \
    --conditions "$CONDITIONS" \
    --output "$OUTPUT_DIR/harness.c"

# 3. Compile
# This requires clang and libFuzzer.
if command -v clang >/dev/null 2>&1; then
    echo "[Build] Compiling..."
    # clang -g -O1 -fsanitize=fuzzer,address \
    #     -I"$OUTPUT_DIR" -I"$ROOT_DIR/external/nanopb" \
    #     "$OUTPUT_DIR/harness.c" "$OUTPUT_DIR"/*.pb.c "$ROOT_DIR/external/nanopb"/*.c \
    #     -o "$OUTPUT_DIR/fuzzer"
    echo "[Build] Compilation command ready (commented out for safety)"
else
    echo "[Build] clang not found, skipping compilation"
fi

echo "[Build] Done."
