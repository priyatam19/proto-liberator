#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"

# Required: point to a libErator conditions.json (list format).
CONDITIONS="${CONDITIONS:-}"
if [ -z "$CONDITIONS" ]; then
  echo "Usage: CONDITIONS=/path/to/conditions.json $0 [output_dir]"
  exit 2
fi

OUT_DIR="${1:-$ROOT_DIR/tests/output_seeds/seeds}"
NUM_SEEDS="${NUM_SEEDS:-32}"
MAX_LEN="${MAX_LEN:-16}"
RNG_SEED="${RNG_SEED:-0}"

mkdir -p "$OUT_DIR"

echo "[Seed-Gen] Wire-mode seed generation..."
python3 "$SRC_DIR/seed_generator.py" \
  --conditions "$CONDITIONS" \
  --output-dir "$OUT_DIR" \
  --num-seeds "$NUM_SEEDS" \
  --max-len "$MAX_LEN" \
  --rng-seed "$RNG_SEED"

echo "[Seed-Gen] Done: $(ls -1 "$OUT_DIR" | wc -l) files in $OUT_DIR"
