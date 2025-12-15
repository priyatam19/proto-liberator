#!/bin/bash
# Build external dependencies for Proto-libErator
# - libprotobuf-mutator
# - nanopb (for embedded protobuf)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
EXTERNAL_DIR="$PROJECT_ROOT/external"

echo "================================================================"
echo "Proto-libErator Dependency Builder"
echo "================================================================"
echo ""

# Create external directory
mkdir -p "$EXTERNAL_DIR"
cd "$EXTERNAL_DIR"

# ==============================================================================
# Build libprotobuf-mutator
# ==============================================================================

echo "[1/2] Building libprotobuf-mutator..."
echo "----------------------------------------------------------------------"

if [ ! -d "libprotobuf-mutator" ]; then
    echo "  Cloning libprotobuf-mutator..."
    git clone https://github.com/google/libprotobuf-mutator.git
fi

cd libprotobuf-mutator

# Check if already built
if [ -f "build/src/libprotobuf-mutator.a" ]; then
    echo "  ✓ libprotobuf-mutator already built"
else
    echo "  Building libprotobuf-mutator..."

    # Create build directory
    mkdir -p build
    cd build

    # Configure with CMake
    cmake .. \
        -DCMAKE_BUILD_TYPE=Release \
        -DLIB_PROTO_MUTATOR_DOWNLOAD_PROTOBUF=ON \
        -DLIB_PROTO_MUTATOR_TESTING=OFF

    # Build
    make -j$(nproc)

    echo "  ✓ Built libprotobuf-mutator"
    cd ..
fi

cd "$EXTERNAL_DIR"

# ==============================================================================
# Setup nanopb (Optional - for embedded targets)
# ==============================================================================

echo ""
echo "[2/2] Setting up nanopb..."
echo "----------------------------------------------------------------------"

if [ ! -d "nanopb" ]; then
    echo "  Cloning nanopb..."
    git clone https://github.com/nanopb/nanopb.git
fi

cd nanopb

# Check if already built
if [ -f "generator/proto/nanopb_pb2.py" ]; then
    echo "  ✓ nanopb already set up"
else
    echo "  Building nanopb generator..."
    cd generator/proto
    make
    cd ../..
    echo "  ✓ Built nanopb generator"
fi

cd "$PROJECT_ROOT"

# ==============================================================================
# Verification
# ==============================================================================

echo ""
echo "================================================================"
echo "Dependency Build Complete"
echo "================================================================"
echo ""

# Check libprotobuf-mutator
if [ -f "$EXTERNAL_DIR/libprotobuf-mutator/build/src/libprotobuf-mutator.a" ]; then
    echo "✓ libprotobuf-mutator: $(realpath "$EXTERNAL_DIR/libprotobuf-mutator/build/src/libprotobuf-mutator.a")"
else
    echo "✗ libprotobuf-mutator: NOT FOUND"
    exit 1
fi

# Check nanopb
if [ -f "$EXTERNAL_DIR/nanopb/generator/nanopb_generator.py" ]; then
    echo "✓ nanopb: $(realpath "$EXTERNAL_DIR/nanopb")"
else
    echo "✗ nanopb: NOT FOUND"
    exit 1
fi

echo ""
echo "All dependencies built successfully!"
echo ""
echo "Next steps:"
echo "  1. Run: python3 tests/test_installation.py"
echo "  2. Try: python3 src/proto_generator.py --help"
echo ""
