#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/fuzz_library.sh <target> [--liberator-root PATH] [--driver-index N] [--out-dir DIR] [--schema-mode v2|v1] [--header H] [--] [run_all args...]

This is a thin wrapper that:
  1) Runs libErator analysis + driver generation (via libErator docker scripts)
  2) Calls proto-liberator orchestrator (src/run_all.py) with detected paths

Requirements:
  - libErator checkout (LIBERATOR_ROOT) with docker scripts available
  - Docker installed + working (for libErator steps)

Examples (cJSON):
  LIBERATOR_ROOT=../liberator \
    scripts/fuzz_library.sh cjson \
      --schema-mode v2 \
      --out-dir workdir/cjson_auto \
      --header cjson/cJSON.h \
      -- --build --fuzz --generate-seeds
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ -z "${1:-}" ]; then
  usage
  exit 0
fi

TARGET_NAME="$1"
shift

LIBERATOR_ROOT="${LIBERATOR_ROOT:-}"
DRIVER_INDEX=0
OUT_DIR=""
SCHEMA_MODE="v2"
HEADER=""

EXTRA_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --liberator-root)
      LIBERATOR_ROOT="$2"
      shift 2
      ;;
    --driver-index)
      DRIVER_INDEX="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --schema-mode)
      SCHEMA_MODE="$2"
      shift 2
      ;;
    --header)
      HEADER="$2"
      shift 2
      ;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -z "$LIBERATOR_ROOT" ]; then
  if [ -d "${ROOT_DIR}/../liberator" ]; then
    LIBERATOR_ROOT="${ROOT_DIR}/../liberator"
  else
    echo "[fuzz_library] ERROR: LIBERATOR_ROOT not set and ../liberator not found."
    echo "[fuzz_library] Set: LIBERATOR_ROOT=/path/to/liberator"
    exit 2
  fi
fi

LIBERATOR_ROOT="$(cd "$LIBERATOR_ROOT" && pwd)"

if [ -z "$OUT_DIR" ]; then
  OUT_DIR="${ROOT_DIR}/workdir/${TARGET_NAME}_auto"
fi
mkdir -p "$OUT_DIR"

if [ -z "$HEADER" ]; then
  if [ "$TARGET_NAME" = "cjson" ]; then
    HEADER="cjson/cJSON.h"
  else
    echo "[fuzz_library] ERROR: --header is required for targets other than cjson."
    exit 2
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[fuzz_library] ERROR: docker not found; libErator integration requires docker."
  exit 2
fi

ANALYSIS_DIR="${LIBERATOR_ROOT}/analysis/${TARGET_NAME}/work/apipass"
CONDITIONS_JSON="${ANALYSIS_DIR}/conditions.json"
APIS_JSON="${ANALYSIS_DIR}/apis_clang.json"
if [ ! -f "$APIS_JSON" ]; then
  APIS_JSON="${ANALYSIS_DIR}/apis_llvm.json"
fi

DRIVER_META="${LIBERATOR_ROOT}/workdir/${TARGET_NAME}/metadata/driver${DRIVER_INDEX}.meta"

echo "[fuzz_library] libErator root: ${LIBERATOR_ROOT}"
echo "[fuzz_library] target: ${TARGET_NAME}"

if [ ! -f "$CONDITIONS_JSON" ]; then
  echo "[fuzz_library] Running libErator analysis (docker)..."
  (cd "${LIBERATOR_ROOT}/docker" && DEVENV=1 TARGET="${TARGET_NAME}" ./run_analysis.sh)
else
  echo "[fuzz_library] Analysis already present: ${CONDITIONS_JSON}"
fi

if [ ! -f "$DRIVER_META" ]; then
  echo "[fuzz_library] Running libErator driver generation (docker)..."
  (cd "${LIBERATOR_ROOT}/docker" && TARGET="${TARGET_NAME}" ./run_drivergeneration.sh)
else
  echo "[fuzz_library] Driver meta already present: ${DRIVER_META}"
fi

if [ ! -f "$CONDITIONS_JSON" ]; then
  echo "[fuzz_library] ERROR: conditions.json not found after analysis: ${CONDITIONS_JSON}"
  exit 1
fi
if [ ! -f "$APIS_JSON" ]; then
  echo "[fuzz_library] ERROR: apis_clang.json/apis_llvm.json not found: ${ANALYSIS_DIR}"
  exit 1
fi
if [ ! -f "$DRIVER_META" ] && [ "$SCHEMA_MODE" = "v1" ]; then
  echo "[fuzz_library] ERROR: driver meta not found for v1: ${DRIVER_META}"
  exit 1
fi

INCLUDE_DIR="${LIBERATOR_ROOT}/analysis/${TARGET_NAME}/work/include"
LIB_DIR="${LIBERATOR_ROOT}/analysis/${TARGET_NAME}/work/lib"
AUTO_LIB=""
if [ -d "$LIB_DIR" ]; then
  # Pick the only .a if unambiguous.
  mapfile -t ARCHIVES < <(ls -1 "$LIB_DIR"/*.a 2>/dev/null || true)
  if [ "${#ARCHIVES[@]}" -eq 1 ]; then
    AUTO_LIB="${ARCHIVES[0]}"
  fi
fi

RUN_ALL_ARGS=(
  --library "$TARGET_NAME"
  --conditions "$CONDITIONS_JSON"
  --apis "$APIS_JSON"
  --out-dir "$OUT_DIR"
  --schema-mode "$SCHEMA_MODE"
  --header "$HEADER"
)

if [ -f "$DRIVER_META" ]; then
  RUN_ALL_ARGS+=(--driver "$DRIVER_META")
fi
if [ -d "$INCLUDE_DIR" ]; then
  RUN_ALL_ARGS+=(--target-include "$INCLUDE_DIR")
fi
if [ -n "$AUTO_LIB" ]; then
  RUN_ALL_ARGS+=(--target-lib "$AUTO_LIB")
fi

echo "[fuzz_library] Running proto-liberator orchestrator..."
python3 "${ROOT_DIR}/src/run_all.py" "${RUN_ALL_ARGS[@]}" "${EXTRA_ARGS[@]}"

