#!/bin/bash
# Setup symlinks to libErator analysis results and code

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBERATOR_ROOT="/home/priyatam/pin_compete/tools/liberator"

echo "Setting up symlinks to libErator..."
echo ""

# Create examples/cjson/input directory
mkdir -p "$SCRIPT_DIR/examples/cjson/input"
mkdir -p "$SCRIPT_DIR/examples/cjson/generated"

# Symlink libErator analysis results
if [ -d "$LIBERATOR_ROOT/analysis/cjson/work/apipass" ]; then
    echo "✓ Symlinking cJSON analysis results..."
    ln -sf "$LIBERATOR_ROOT/analysis/cjson/work/apipass/conditions.json" \
           "$SCRIPT_DIR/examples/cjson/input/conditions.json"
    ln -sf "$LIBERATOR_ROOT/analysis/cjson/work/apipass/apis_clang.json" \
           "$SCRIPT_DIR/examples/cjson/input/apis_clang.json"
    ln -sf "$LIBERATOR_ROOT/analysis/cjson/work/apipass/data_layout.txt" \
           "$SCRIPT_DIR/examples/cjson/input/data_layout.txt"
else
    echo "⚠ libErator cJSON analysis not found at: $LIBERATOR_ROOT/analysis/cjson"
    echo "  Run libErator analysis first"
fi

# Symlink driver metadata
if [ -d "$LIBERATOR_ROOT/workdir/cjson/metadata" ]; then
    echo "✓ Symlinking cJSON driver metadata..."
    for i in {0..4}; do
        if [ -f "$LIBERATOR_ROOT/workdir/cjson/metadata/driver$i.meta" ]; then
            ln -sf "$LIBERATOR_ROOT/workdir/cjson/metadata/driver$i.meta" \
                   "$SCRIPT_DIR/examples/cjson/input/driver$i.meta"
        fi
    done
else
    echo "⚠ libErator cJSON drivers not found"
    echo "  Run libErator driver generation first"
fi

# Symlink libErator source (for reference)
echo "✓ Symlinking libErator source..."
ln -sf "$LIBERATOR_ROOT" "$SCRIPT_DIR/external/liberator"

echo ""
echo "Symlinks created:"
ls -la "$SCRIPT_DIR/examples/cjson/input/"
echo ""
echo "Done!"
