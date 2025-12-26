#!/bin/bash
set -euo pipefail

# CASR-based crash triage + dedup (cluster) for a proto-liberator workdir.
#
# This mirrors Liberator's approach:
#   casr-libfuzzer -> casr-cluster (with ignore filter)
#
# Usage:
#   ./scripts/cluster_crashes.sh <workdir>
#   ./scripts/cluster_crashes.sh <workdir> --crash-dir <dir> --out-dir <dir>
#   ./scripts/cluster_crashes.sh <workdir> --ignore <casr-ignore-file>
#   ./scripts/cluster_crashes.sh <workdir> --docker-image <image-with-casr>
#
# Notes:
# - Requires `casr-libfuzzer` + `casr-cluster` in PATH, OR `--docker-image`.
# - By default it searches for crashes under: artifacts/, crashes/, crash-*, leak-*, timeout-*, oom-*.

usage() {
  cat <<'EOF'
Usage:
  scripts/cluster_crashes.sh <workdir> [options]

Options:
  --crash-dir DIR        Directory containing crash-* files (default: auto-detect)
  --out-dir DIR          Output directory for CASR reports + clusters (default: <workdir>/casr)
  --ignore FILE          CASR cluster ignore file (default: auto-generate proto-liberator filter)
  --fuzzer-bin PATH      Fuzzer binary (default: first <workdir>/*_fuzzer.bin)
  --docker-image IMAGE   Run CASR inside docker image (must contain casr-libfuzzer/casr-cluster)
  -h, --help             Show this help
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ -z "${1:-}" ]; then
  usage
  exit 0
fi

WORKDIR="$1"
shift

CRASH_DIR=""
OUT_DIR=""
IGNORE_FILE=""
FUZZ_BIN=""
DOCKER_IMAGE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --crash-dir)
      CRASH_DIR="${2:-}"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --ignore)
      IGNORE_FILE="${2:-}"
      shift 2
      ;;
    --fuzzer-bin)
      FUZZ_BIN="${2:-}"
      shift 2
      ;;
    --docker-image)
      DOCKER_IMAGE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ ! -d "${WORKDIR}" ]; then
  echo "[ERROR] workdir not found: ${WORKDIR}" >&2
  exit 2
fi

if [ -z "${FUZZ_BIN}" ]; then
  FUZZ_BIN="$(ls -1 "${WORKDIR}"/*_fuzzer.bin 2>/dev/null | head -n 1 || true)"
fi
if [ -z "${FUZZ_BIN}" ] || [ ! -f "${FUZZ_BIN}" ]; then
  echo "[ERROR] fuzzer binary not found (expected ${WORKDIR}/*_fuzzer.bin). Use --fuzzer-bin." >&2
  exit 2
fi

if [ -z "${OUT_DIR}" ]; then
  OUT_DIR="${WORKDIR}/casr"
fi
mkdir -p "${OUT_DIR}"

TRIAGE_DIR="${OUT_DIR}/triage"
CLUSTERS_DIR="${OUT_DIR}/clusters"
LOGS_DIR="${OUT_DIR}/logs"
mkdir -p "${TRIAGE_DIR}" "${CLUSTERS_DIR}" "${LOGS_DIR}"

TMP_DIR="${OUT_DIR}/_tmp"
mkdir -p "${TMP_DIR}"

if [ -z "${CRASH_DIR}" ]; then
  # Prefer proto-liberator's artifact_prefix directory if present.
  if [ -d "${WORKDIR}/artifacts" ]; then
    CRASH_DIR="${WORKDIR}/artifacts"
  elif [ -d "${WORKDIR}/crashes" ]; then
    CRASH_DIR="${WORKDIR}/crashes"
  else
    CRASH_DIR="${TMP_DIR}/crashes"
    mkdir -p "${CRASH_DIR}"
    # Collect crash files directly under workdir (and common subdirs).
    found_any=0
    for pattern in "${WORKDIR}/crash-"* "${WORKDIR}/leak-"* "${WORKDIR}/timeout-"* "${WORKDIR}/oom-"*; do
      for f in $pattern; do
        if [ -f "$f" ]; then
          ln -sf "$f" "${CRASH_DIR}/$(basename "$f")"
          found_any=1
        fi
      done
    done
    for d in "${WORKDIR}/artifacts" "${WORKDIR}/crashes"; do
      if [ -d "$d" ]; then
        for f in "$d"/*; do
          if [ -f "$f" ]; then
            ln -sf "$f" "${CRASH_DIR}/$(basename "$f")"
            found_any=1
          fi
        done
      fi
    done
    if [ "${found_any}" -eq 0 ]; then
      echo "[INFO] no crash files found under ${WORKDIR}" >&2
      exit 0
    fi
  fi
fi

if [ ! -d "${CRASH_DIR}" ]; then
  echo "[ERROR] crash dir not found: ${CRASH_DIR}" >&2
  exit 2
fi

if [ -z "${IGNORE_FILE}" ]; then
  IGNORE_FILE="${OUT_DIR}/cluster_filter.txt"
  cat > "${IGNORE_FILE}" <<'EOF'
FILES
*/harness.c
*/harness.cc
*/bindings/*.pb.*
*/external/libprotobuf-mutator/*
*/google/protobuf/*
*/absl/*
FUNCTIONS
LLVMFuzzerTestOneInput
LLVMFuzzerCustomMutator
LLVMFuzzerCustomCrossOver
_start
__libc_start_main
main
EOF
fi

if [ ! -f "${IGNORE_FILE}" ]; then
  echo "[ERROR] ignore file not found: ${IGNORE_FILE}" >&2
  exit 2
fi

echo "========================================"
echo "Proto-libErator Crash Clustering (CASR)"
echo "========================================"
echo "Workdir:    ${WORKDIR}"
echo "Fuzzer:     ${FUZZ_BIN}"
echo "Crashes:    ${CRASH_DIR}"
echo "Out:        ${OUT_DIR}"
echo "Ignore:     ${IGNORE_FILE}"
if [ -n "${DOCKER_IMAGE}" ]; then
  echo "Docker:     ${DOCKER_IMAGE}"
fi
echo "========================================"

run_casr() {
  local casr_libfuzzer="$1"
  local casr_cluster="$2"

  echo "[CASR] Triaging crashes..."
  "${casr_libfuzzer}" -i "${CRASH_DIR}" -o "${TRIAGE_DIR}" -- "${FUZZ_BIN}" \
    > "${LOGS_DIR}/casr-libfuzzer.log" 2>&1 || true

  echo "[CASR] Clustering..."
  rm -rf "${CLUSTERS_DIR}"
  mkdir -p "${CLUSTERS_DIR}"
  "${casr_cluster}" --ignore "${IGNORE_FILE}" -c "${TRIAGE_DIR}" "${CLUSTERS_DIR}" \
    > "${LOGS_DIR}/casr-cluster.log" 2>&1 || true
}

if [ -z "${DOCKER_IMAGE}" ]; then
  CASR_LIBFUZZER="$(command -v casr-libfuzzer 2>/dev/null || true)"
  CASR_CLUSTER="$(command -v casr-cluster 2>/dev/null || true)"

  if [ -z "${CASR_LIBFUZZER}" ] || [ -z "${CASR_CLUSTER}" ]; then
    cat <<EOF >&2
[ERROR] casr tools not found in PATH.

Install options:
  - Install CASR locally (casr-libfuzzer + casr-cluster)
  - Or rerun with: --docker-image <image-with-casr>

Liberator uses CASR inside its containers; if you have a Liberator image built, pass it here.
EOF
    exit 2
  fi

  run_casr "${CASR_LIBFUZZER}" "${CASR_CLUSTER}"
else
  if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] docker not found, cannot use --docker-image" >&2
    exit 2
  fi

  # Run CASR inside container; mount the workdir so the fuzzer + crashes are visible.
  # If crash/ignore inputs live outside WORKDIR, copy them under OUT_DIR first so they are mount-visible.
  WORKDIR_REAL="$(cd "${WORKDIR}" && pwd)"

  if ! realpath --relative-to="${WORKDIR_REAL}" "${CRASH_DIR}" >/dev/null 2>&1; then
    echo "[WARN] crash dir is outside workdir; copying crashes under ${TMP_DIR} for docker run."
    DOCKER_CRASH_DIR="${TMP_DIR}/crashes_docker"
    rm -rf "${DOCKER_CRASH_DIR}"
    mkdir -p "${DOCKER_CRASH_DIR}"
    find "${CRASH_DIR}" -maxdepth 1 -type f -print0 2>/dev/null | xargs -0 -I{} cp "{}" "${DOCKER_CRASH_DIR}/" || true
    CRASH_DIR="${DOCKER_CRASH_DIR}"
  fi

  if ! realpath --relative-to="${WORKDIR_REAL}" "${IGNORE_FILE}" >/dev/null 2>&1; then
    echo "[WARN] ignore file is outside workdir; copying under ${OUT_DIR} for docker run."
    cp "${IGNORE_FILE}" "${OUT_DIR}/cluster_filter.external.txt"
    IGNORE_FILE="${OUT_DIR}/cluster_filter.external.txt"
  fi

  CRASH_DIR_REL="$(realpath --relative-to="${WORKDIR_REAL}" "${CRASH_DIR}")"
  FUZZ_BIN_REL="$(realpath --relative-to="${WORKDIR_REAL}" "${FUZZ_BIN}")"
  OUT_DIR_REL="$(realpath --relative-to="${WORKDIR_REAL}" "${OUT_DIR}")"
  IGNORE_FILE_REL="$(realpath --relative-to="${WORKDIR_REAL}" "${IGNORE_FILE}")"

  docker run --rm \
    -v "${WORKDIR}:/workdir" \
    -w "/workdir" \
    "${DOCKER_IMAGE}" \
    bash -lc "$(printf '%q ' casr-libfuzzer -i "/workdir/${CRASH_DIR_REL}" -o "/workdir/${OUT_DIR_REL}/triage" -- "/workdir/${FUZZ_BIN_REL}")" \
    > "${LOGS_DIR}/casr-libfuzzer.docker.log" 2>&1 || true

  docker run --rm \
    -v "${WORKDIR}:/workdir" \
    -w "/workdir" \
    "${DOCKER_IMAGE}" \
    bash -lc "$(printf '%q ' casr-cluster --ignore "/workdir/${IGNORE_FILE_REL}" -c "/workdir/${OUT_DIR_REL}/triage" "/workdir/${OUT_DIR_REL}/clusters")" \
    > "${LOGS_DIR}/casr-cluster.docker.log" 2>&1 || true
fi

casrep_count=$(find "${TRIAGE_DIR}" -type f -name "*.casrep" 2>/dev/null | wc -l | tr -d ' ')
cluster_count=$(find "${CLUSTERS_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo "========================================"
echo "CASR Result Summary"
echo "========================================"
echo "CASR reports:  ${casrep_count}  (${TRIAGE_DIR})"
echo "Clusters dir:  ${CLUSTERS_DIR}"
echo "Cluster count: ${cluster_count} (directories under clusters/)"
echo "Logs:          ${LOGS_DIR}"
echo "========================================"
