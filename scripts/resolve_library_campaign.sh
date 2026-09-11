#!/usr/bin/env bash
set -euo pipefail

# Resolve one library's campaign inputs (same resolution
# scripts/run_highcoverage_campaigns.sh uses for all 11) and print the
# resulting `run_campaign.sh` argument list, one argument per line, so a
# caller can do:
#
#   mapfile -t ARGS < <(scripts/resolve_library_campaign.sh --library cjson)
#   scripts/run_campaign.sh "${ARGS[@]}" --stage build --campaign-dir "${DIR}"
#
# Used by per-library CI jobs that need this library's resolved
# conditions/apis/headers/target-lib/corpus without re-deriving it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/resolve_library_campaign.sh --library NAME [options]

Options:
  --out-root DIR            Passed through as --out-root (default: artifacts/highcoverage_campaigns/<stamp>/campaigns)
  --duration-sec N          Default: use library's saved campaign.json profile fuzz duration is NOT stored there; default 86400
  --coverage-interval-sec N Default: 900
  --max-actions N           Override saved profile
  --max-len N               Override saved profile
  --timeout-sec N           Override saved profile
  --jobs N                  Override saved profile
  --workers N                Override saved profile
  --fork N                   Override saved profile
  --seed N                   Override saved profile
  --clang PATH               Default: /usr/bin/clang
  --regenerate-harnesses      Regenerate proto/harness instead of reusing saved ones
  --fresh-seeds                Reuse saved proto/harness, regenerate simple seeds
  -h, --help
EOF
}

LIBRARY=""
OUT_ROOT="${ROOT_DIR}/artifacts/highcoverage_campaigns/$(date -u +%Y%m%d_%H%M%S)/campaigns"
DURATION_SEC="86400"
COVERAGE_INTERVAL_SEC="900"
MAX_ACTIONS="64"; MAX_ACTIONS_OVERRIDDEN="0"
MAX_LEN="4096"; MAX_LEN_OVERRIDDEN="0"
TIMEOUT_SEC="25"; TIMEOUT_OVERRIDDEN="0"
JOBS="1"; JOBS_OVERRIDDEN="0"
WORKERS="1"; WORKERS_OVERRIDDEN="0"
FORK="1"; FORK_OVERRIDDEN="0"
SEED="0"; SEED_OVERRIDDEN="0"
CLANG="/usr/bin/clang"
REGENERATE_HARNESSES="0"
FRESH_SEEDS="0"

while (( $# > 0 )); do
  case "$1" in
    --library) LIBRARY="${2:-}"; shift 2 ;;
    --out-root) OUT_ROOT="${2:-}"; shift 2 ;;
    --duration-sec) DURATION_SEC="${2:-}"; shift 2 ;;
    --coverage-interval-sec) COVERAGE_INTERVAL_SEC="${2:-}"; shift 2 ;;
    --max-actions) MAX_ACTIONS="${2:-}"; MAX_ACTIONS_OVERRIDDEN="1"; shift 2 ;;
    --max-len) MAX_LEN="${2:-}"; MAX_LEN_OVERRIDDEN="1"; shift 2 ;;
    --timeout-sec) TIMEOUT_SEC="${2:-}"; TIMEOUT_OVERRIDDEN="1"; shift 2 ;;
    --jobs) JOBS="${2:-}"; JOBS_OVERRIDDEN="1"; shift 2 ;;
    --workers) WORKERS="${2:-}"; WORKERS_OVERRIDDEN="1"; shift 2 ;;
    --fork) FORK="${2:-}"; FORK_OVERRIDDEN="1"; shift 2 ;;
    --seed) SEED="${2:-}"; SEED_OVERRIDDEN="1"; shift 2 ;;
    --clang) CLANG="${2:-}"; shift 2 ;;
    --regenerate-harnesses) REGENERATE_HARNESSES="1"; shift ;;
    --fresh-seeds) FRESH_SEEDS="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[ERROR] Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "${LIBRARY}" ]]; then
  echo "[ERROR] --library is required" >&2
  usage >&2
  exit 2
fi

declare -A CONDITIONS_BY_LIB=()
declare -A APIS_BY_LIB=()
declare -A INCLUDE_ROOT_BY_LIB=()
declare -A INCLUDE_DIRS_BY_LIB=()
declare -A TARGET_LIB_BY_LIB=()
declare -A EXTRA_TARGET_LIBS_BY_LIB=()
declare -A HEADERS_BY_LIB=()
declare -A MINIMUM_APIS_BY_LIB=()
declare -A INITIAL_CORPUS_BY_LIB=()
declare -A INITIAL_CORPUS_SHA256_BY_LIB=()
declare -A PROFILE_MAX_ACTIONS_BY_LIB=()
declare -A PROFILE_MAX_LEN_BY_LIB=()
declare -A PROFILE_TIMEOUT_BY_LIB=()
declare -A PROFILE_JOBS_BY_LIB=()
declare -A PROFILE_WORKERS_BY_LIB=()
declare -A PROFILE_FORK_BY_LIB=()
declare -A PROFILE_SEED_BY_LIB=()

# shellcheck source=lib/resolve_library_campaign.sh
source "${SCRIPT_DIR}/lib/resolve_library_campaign.sh"

preflight_library "${LIBRARY}"

effective_max_actions="${MAX_ACTIONS}"
effective_max_len="${MAX_LEN}"
effective_timeout="${TIMEOUT_SEC}"
effective_jobs="${JOBS}"
effective_workers="${WORKERS}"
effective_fork="${FORK}"
effective_seed="${SEED}"

if [[ "${REGENERATE_HARNESSES}" != "1" ]]; then
  [[ "${MAX_ACTIONS_OVERRIDDEN}" == "1" ]] || effective_max_actions="${PROFILE_MAX_ACTIONS_BY_LIB[${LIBRARY}]}"
  [[ "${MAX_LEN_OVERRIDDEN}" == "1" ]] || effective_max_len="${PROFILE_MAX_LEN_BY_LIB[${LIBRARY}]}"
  [[ "${TIMEOUT_OVERRIDDEN}" == "1" ]] || effective_timeout="${PROFILE_TIMEOUT_BY_LIB[${LIBRARY}]}"
  [[ "${JOBS_OVERRIDDEN}" == "1" ]] || effective_jobs="${PROFILE_JOBS_BY_LIB[${LIBRARY}]}"
  [[ "${WORKERS_OVERRIDDEN}" == "1" ]] || effective_workers="${PROFILE_WORKERS_BY_LIB[${LIBRARY}]}"
  [[ "${FORK_OVERRIDDEN}" == "1" ]] || effective_fork="${PROFILE_FORK_BY_LIB[${LIBRARY}]}"
  [[ "${SEED_OVERRIDDEN}" == "1" ]] || effective_seed="${PROFILE_SEED_BY_LIB[${LIBRARY}]}"
fi

ARGS=(
  --library "${LIBRARY}"
  --conditions "${CONDITIONS_BY_LIB[${LIBRARY}]}"
  --apis "${APIS_BY_LIB[${LIBRARY}]}"
  --out-root "${OUT_ROOT}"
  --schema-mode v2
  --mutation-mode lpm
  --harness-style simple
  --clang "${CLANG}"
  --max-actions "${effective_max_actions}"
  --duration-sec "${DURATION_SEC}"
  --live-coverage-interval-sec "${COVERAGE_INTERVAL_SEC}"
  --max-len "${effective_max_len}"
  --timeout-sec "${effective_timeout}"
  --jobs "${effective_jobs}"
  --workers "${effective_workers}"
  --fork "${effective_fork}"
  --seed-rng "${effective_seed}"
  --fuzz-arg "-seed=${effective_seed}"
  --keep-going
  --variant default
  --target-lib "${TARGET_LIB_BY_LIB[${LIBRARY}]}"
)

mapfile -t headers <<< "${HEADERS_BY_LIB[${LIBRARY}]}"
for value in "${headers[@]}"; do
  [[ -n "${value}" ]] && ARGS+=(--header "${value}")
done

mapfile -t include_dirs <<< "${INCLUDE_DIRS_BY_LIB[${LIBRARY}]}"
for value in "${include_dirs[@]}"; do
  [[ -n "${value}" ]] && ARGS+=(--target-include "${value}")
done

if [[ -n "${MINIMUM_APIS_BY_LIB[${LIBRARY}]}" ]]; then
  ARGS+=(--minimum-apis "${MINIMUM_APIS_BY_LIB[${LIBRARY}]}")
fi
if [[ -n "${EXTRA_TARGET_LIBS_BY_LIB[${LIBRARY}]}" ]]; then
  ARGS+=(--target-lib "${EXTRA_TARGET_LIBS_BY_LIB[${LIBRARY}]}")
fi
if [[ "${REGENERATE_HARNESSES}" != "1" && "${FRESH_SEEDS}" != "1" ]]; then
  ARGS+=(
    --initial-corpus-archive "${INITIAL_CORPUS_BY_LIB[${LIBRARY}]}"
    --initial-corpus-sha256 "${INITIAL_CORPUS_SHA256_BY_LIB[${LIBRARY}]}"
  )
fi
if [[ "${REGENERATE_HARNESSES}" != "1" && "${LIBRARY}" == "cpu_features" ]]; then
  ARGS+=(--cc-arg -DSTACK_LINE_READER_BUFFER_SIZE=1024)
fi
if [[ "${REGENERATE_HARNESSES}" == "1" ]]; then
  ARGS+=(--regenerate-harnesses)
fi

printf '%s\n' "${ARGS[@]}"
