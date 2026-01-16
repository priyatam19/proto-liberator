#!/bin/bash
set -euo pipefail

# Snapshot-and-exec so edits to this file during a long campaign don't affect
# the running process (bash reads scripts incrementally).
if [ -z "${PROTO_LIBERATOR_RUN_CAMPAIGN_SNAPSHOTTED:-}" ]; then
  export PROTO_LIBERATOR_RUN_CAMPAIGN_SNAPSHOTTED=1
  export PROTO_LIBERATOR_RUN_CAMPAIGN_ORIG_ROOT="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
  )"
  SNAP="$(mktemp -t run_campaign.XXXXXXXX.sh)"
  cp "$0" "${SNAP}"
  chmod +x "${SNAP}"
  exec bash "${SNAP}" "$@"
fi

# Run a proto-liberator fuzzing campaign.
#
# Supports a small number of build variants (2–3) in parallel for one campaign,
# each with its own out-dir and (optional) custom compile flags (cc-args).
#
# Example (3 variants in parallel):
#   scripts/run_campaign.sh \
#     --library cjson \
#     --conditions /path/to/conditions.json \
#     --apis /path/to/apis_clang.json \
#     --out-root workdir/campaigns \
#     --header cjson/cJSON.h \
#     --target-include /path/to/include \
#     --target-lib /path/to/libcjson.a \
#     --duration-sec 86400 --jobs 2 --workers 2 \
#     --variant base \
#     --variant cmp --variant-cc-arg -fsanitize-coverage=trace-cmp \
#     --variant gep --variant-cc-arg -fsanitize-coverage=trace-gep
#
# Notes:
# - This script uses `src/run_all.py` to generate schema/bindings/harness and to
#   build BOTH a fuzzer binary and a coverage/profile binary.
# - Coverage reporting is done via `scripts/collect_coverage.sh` (llvm-cov),
#   and crash clustering via `scripts/cluster_crashes.sh` (CASR).

usage() {
  cat <<'EOF'
Usage:
  scripts/run_campaign.sh [options]

Required:
  --library NAME
  --conditions PATH
  --apis PATH
  --out-root DIR
  --header HEADER               Repeatable

Common options:
  --driver PATH                 Optional driver.meta (v2 ok without)
  --schema-mode v2|v1           Default: v2
  --mutation-mode lpm|nanopb    Default: lpm
  --fork N                      Default: 1
  --harness-style strict|simple Default: simple
  --max-actions N               Default: 64
  --num-seeds N                 Default: 64
  --seed-max-len N              Default: 16
  --minimum-apis PATH           Optional apis_minimized.txt to restrict APIs
  --minimum-apis PATH           Optional apis_minimized.txt to restrict APIs
  --seed-rng N                  Default: 0
  --target-include DIR          Repeatable
  --target-lib PATH             Repeatable
  --extra-src PATH              Repeatable
  --profile-extra-src PATH      Build *_profile.bin with extra sources (repeatable)
  --profile-keep-target-lib     Also link --target-lib into *_profile.bin
  --cc-arg ARG                  Extra compile arg for ALL variants (repeatable)
  --with-lenient                Add a second "lenient" variant (if no variants specified)
  --lenient-env KEY=VAL         Env override for lenient variant (repeatable)
  --with-lenient-resize         Add a third "lenient-resize" variant
  --lenient-resize-env KEY=VAL  Env override for lenient-resize variant (repeatable)

Fuzz runtime:
  --duration-sec N              Default: 86400 (24h)
  --max-len N                   Default: 4096
  --timeout-sec N               Default: 25
  --jobs N                      libFuzzer -jobs (default: 1)
  --workers N                   libFuzzer -workers (default: 1)
  --fork N                      libFuzzer -fork (default: 1)
  --keep-going                  Add -ignore_crashes=1 -ignore_timeouts=1 -ignore_ooms=1 (default)
  --stop-on-crash               Disable --keep-going behaviour
  --live-coverage-interval-sec N  If set, periodically runs *_profile.bin on the current corpus and writes profraw (enables --live coverage)
  --fuzz-arg ARG                Extra runtime arg for ALL variants (repeatable)

Variants (2–3 recommended):
  --variant NAME                Start/declare a variant (repeatable)
  --variant-cc-arg ARG          Compile arg for the CURRENT variant (repeatable)
  --variant-fuzz-arg ARG        Runtime arg for the CURRENT variant (repeatable)
  --variant-env KEY=VAL         Env override for the CURRENT variant (repeatable)

EOF
}

if [ -n "${PROTO_LIBERATOR_RUN_CAMPAIGN_ORIG_ROOT:-}" ]; then
  ROOT_DIR="${PROTO_LIBERATOR_RUN_CAMPAIGN_ORIG_ROOT}"
  SCRIPT_DIR="${ROOT_DIR}/scripts"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

LIBRARY=""
CONDITIONS=""
APIS=""
DRIVER=""
OUT_ROOT=""
declare -a HEADERS=()
SCHEMA_MODE="v2"
MUTATION_MODE="lpm"
MAX_ACTIONS="64"
NUM_SEEDS="64"
SEED_MAX_LEN="16"
SEED_RNG="0"
HARNESS_STYLE="simple"

DURATION_SEC="86400"
MAX_LEN="4096"
TIMEOUT_SEC="25"
JOBS="1"
WORKERS="1"
FORK="1"
KEEP_GOING="1"
GENERATE_SEEDS="1"
LIVE_COVERAGE_INTERVAL_SEC="0"
WITH_LENIENT="0"
WITH_LENIENT_RESIZE="0"

GLOBAL_CC_ARGS=()
GLOBAL_FUZZ_ARGS=()
TARGET_INCLUDES=()
TARGET_LIBS=()
EXTRA_SRCS=()
PROFILE_EXTRA_SRCS=()
PROFILE_KEEP_TARGET_LIB="0"
MINIMUM_APIS=""
MINIMUM_APIS=""

declare -a VARIANTS=()
declare -A VARIANT_CC_ARGS=()
declare -A VARIANT_FUZZ_ARGS=()
declare -A VARIANT_ENVS=()
declare -a LENIENT_ENV=()
declare -a LENIENT_RESIZE_ENV=()
CURRENT_VARIANT=""

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --library) LIBRARY="${2:-}"; shift 2;;
    --conditions) CONDITIONS="${2:-}"; shift 2;;
    --apis) APIS="${2:-}"; shift 2;;
    --driver) DRIVER="${2:-}"; shift 2;;
    --out-root) OUT_ROOT="${2:-}"; shift 2;;
    --header) HEADERS+=("${2:-}"); shift 2;;
    --schema-mode) SCHEMA_MODE="${2:-}"; shift 2;;
    --mutation-mode) MUTATION_MODE="${2:-}"; shift 2;;
    --max-actions) MAX_ACTIONS="${2:-}"; shift 2;;
    --num-seeds) NUM_SEEDS="${2:-}"; shift 2;;
    --seed-max-len) SEED_MAX_LEN="${2:-}"; shift 2;;
    --seed-rng) SEED_RNG="${2:-}"; shift 2;;
    --harness-style) HARNESS_STYLE="${2:-}"; shift 2;;

    --duration-sec) DURATION_SEC="${2:-}"; shift 2;;
    --max-len) MAX_LEN="${2:-}"; shift 2;;
    --timeout-sec) TIMEOUT_SEC="${2:-}"; shift 2;;
    --jobs) JOBS="${2:-}"; shift 2;;
    --workers) WORKERS="${2:-}"; shift 2;;
    --keep-going) KEEP_GOING="1"; shift;;
    --no-seed-gen) GENERATE_SEEDS="0"; shift;;
    --stop-on-crash) KEEP_GOING="0"; shift;;
    --fork) FORK="${2:-}"; shift 2;;
    --live-coverage-interval-sec) LIVE_COVERAGE_INTERVAL_SEC="${2:-0}"; shift 2;;
    --with-lenient) WITH_LENIENT="1"; shift;;
    --with-lenient-resize) WITH_LENIENT_RESIZE="1"; shift;;

    --cc-arg) GLOBAL_CC_ARGS+=("${2:-}"); shift 2;;
    --fuzz-arg) GLOBAL_FUZZ_ARGS+=("${2:-}"); shift 2;;
    --target-include) TARGET_INCLUDES+=("${2:-}"); shift 2;;
    --target-lib) TARGET_LIBS+=("${2:-}"); shift 2;;
    --minimum-apis) MINIMUM_APIS="${2:-}"; shift 2;;
    --extra-src) EXTRA_SRCS+=("${2:-}"); shift 2;;
    --profile-extra-src) PROFILE_EXTRA_SRCS+=("${2:-}"); shift 2;;
    --profile-keep-target-lib) PROFILE_KEEP_TARGET_LIB="1"; shift;;

    --variant)
      CURRENT_VARIANT="${2:-}"
      if [ -z "${CURRENT_VARIANT}" ]; then
        echo "[ERROR] --variant requires a name" >&2
        exit 2
      fi
      VARIANTS+=("${CURRENT_VARIANT}")
      VARIANT_CC_ARGS["${CURRENT_VARIANT}"]=""
      VARIANT_FUZZ_ARGS["${CURRENT_VARIANT}"]=""
      VARIANT_ENVS["${CURRENT_VARIANT}"]=""
      shift 2
      ;;
    --variant-cc-arg)
      if [ -z "${CURRENT_VARIANT}" ]; then
        echo "[ERROR] --variant-cc-arg must follow a --variant" >&2
        exit 2
      fi
      VARIANT_CC_ARGS["${CURRENT_VARIANT}"]+=$'\n'"${2:-}"
      shift 2
      ;;
    --variant-fuzz-arg)
      if [ -z "${CURRENT_VARIANT}" ]; then
        echo "[ERROR] --variant-fuzz-arg must follow a --variant" >&2
        exit 2
      fi
      VARIANT_FUZZ_ARGS["${CURRENT_VARIANT}"]+=$'\n'"${2:-}"
      shift 2
      ;;
    --variant-env)
      if [ -z "${CURRENT_VARIANT}" ]; then
        echo "[ERROR] --variant-env must follow a --variant" >&2
        exit 2
      fi
      VARIANT_ENVS["${CURRENT_VARIANT}"]+=$'\n'"${2:-}"
      shift 2
      ;;
    --lenient-env)
      LENIENT_ENV+=("${2:-}")
      shift 2
      ;;
    --lenient-resize-env)
      LENIENT_RESIZE_ENV+=("${2:-}")
      shift 2
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "${LIBRARY}" ] || [ -z "${CONDITIONS}" ] || [ -z "${APIS}" ] || [ -z "${OUT_ROOT}" ] || [ "${#HEADERS[@]}" -eq 0 ]; then
  echo "[ERROR] Missing required args." >&2
  usage >&2
  exit 2
fi

# Normalize key paths to absolute to avoid issues when the script changes directories.
OUT_ROOT="$(cd "${OUT_ROOT}" && pwd)"
CONDITIONS="$(cd "$(dirname "${CONDITIONS}")" && pwd)/$(basename "${CONDITIONS}")"
APIS="$(cd "$(dirname "${APIS}")" && pwd)/$(basename "${APIS}")"
if [ -n "${MINIMUM_APIS}" ]; then
  MINIMUM_APIS="$(cd "$(dirname "${MINIMUM_APIS}")" && pwd)/$(basename "${MINIMUM_APIS}")"
fi
if [ -n "${DRIVER}" ]; then
  DRIVER="$(cd "$(dirname "${DRIVER}")" && pwd)/$(basename "${DRIVER}")"
fi

LENIENT_DEFAULTS=$'PROTO_LIBERATOR_NULL_BUDGET=4\nPROTO_LIBERATOR_NULL_PROB_NUM=1\nPROTO_LIBERATOR_NULL_PROB_DEN=8\nPROTO_LIBERATOR_STALE_BUDGET=1\nPROTO_LIBERATOR_STALE_PROB_NUM=1\nPROTO_LIBERATOR_STALE_PROB_DEN=32\nPROTO_LIBERATOR_CHARPP_FALLBACK=1'

if [ "${#VARIANTS[@]}" -eq 0 ]; then
  if [ "${WITH_LENIENT}" = "1" ] || [ "${WITH_LENIENT_RESIZE}" = "1" ]; then
    VARIANTS=("strict")
    VARIANT_CC_ARGS["strict"]=""
    VARIANT_FUZZ_ARGS["strict"]=""
    VARIANT_ENVS["strict"]=""
    if [ "${WITH_LENIENT}" = "1" ]; then
      VARIANTS+=("lenient")
      VARIANT_CC_ARGS["lenient"]=""
      VARIANT_FUZZ_ARGS["lenient"]=""
      VARIANT_ENVS["lenient"]=""
    fi
    if [ "${WITH_LENIENT_RESIZE}" = "1" ]; then
      VARIANTS+=("lenient-resize")
      VARIANT_CC_ARGS["lenient-resize"]=""
      VARIANT_FUZZ_ARGS["lenient-resize"]=""
      VARIANT_ENVS["lenient-resize"]=""
    fi
  else
    VARIANTS=("default")
    VARIANT_CC_ARGS["default"]=""
    VARIANT_FUZZ_ARGS["default"]=""
    VARIANT_ENVS["default"]=""
  fi
fi

add_variant_if_missing() {
  local name="$1"
  for v in "${VARIANTS[@]}"; do
    if [ "${v}" = "${name}" ]; then
      return
    fi
  done
  VARIANTS+=("${name}")
  VARIANT_CC_ARGS["${name}"]=""
  VARIANT_FUZZ_ARGS["${name}"]=""
  VARIANT_ENVS["${name}"]=""
}

if [ "${WITH_LENIENT}" = "1" ]; then
  add_variant_if_missing "lenient"
  VARIANT_ENVS["lenient"]+=$'\n'"${LENIENT_DEFAULTS}"
fi

if [ "${WITH_LENIENT_RESIZE}" = "1" ]; then
  add_variant_if_missing "lenient-resize"
  VARIANT_ENVS["lenient-resize"]+=$'\n'"${LENIENT_DEFAULTS}"
  VARIANT_ENVS["lenient-resize"]+=$'\n'"PROTO_LIBERATOR_RESIZE_BYTES=1"
fi

for kv in "${LENIENT_ENV[@]}"; do
  VARIANT_ENVS["lenient"]+=$'\n'"${kv}"
done

for kv in "${LENIENT_RESIZE_ENV[@]}"; do
  VARIANT_ENVS["lenient-resize"]+=$'\n'"${kv}"
done

STAMP="$(date +%Y%m%d_%H%M%S)"
CAMPAIGN_DIR="${OUT_ROOT%/}/${LIBRARY}_${STAMP}"
mkdir -p "${CAMPAIGN_DIR}"

META_JSON="${CAMPAIGN_DIR}/campaign.meta.txt"
{
  echo "library=${LIBRARY}"
  echo "schema_mode=${SCHEMA_MODE}"
  echo "mutation_mode=${MUTATION_MODE}"
  echo "max_actions=${MAX_ACTIONS}"
  echo "duration_sec=${DURATION_SEC}"
  echo "jobs=${JOBS}"
  echo "workers=${WORKERS}"
  echo "timestamp=${STAMP}"
} > "${META_JSON}"

echo "========================================"
echo "Proto-libErator Campaign"
echo "========================================"
echo "Campaign:   ${CAMPAIGN_DIR}"
echo "Library:    ${LIBRARY}"
echo "Variants:   ${#VARIANTS[@]} (${VARIANTS[*]})"
echo "Duration:   ${DURATION_SEC}s"
echo "Jobs/Work:  ${JOBS}/${WORKERS}"
echo "========================================"

build_variant() {
  local variant="$1"
  local out_dir="${CAMPAIGN_DIR}/${variant}"
  mkdir -p "${out_dir}"

  local -a run_all_args=(
    --library "${LIBRARY}"
    --conditions "${CONDITIONS}"
    --apis "${APIS}"
    --out-dir "${out_dir}"
    --schema-mode "${SCHEMA_MODE}"
    --mutation-mode "${MUTATION_MODE}"
    --max-actions "${MAX_ACTIONS}"
    --num-seeds "${NUM_SEEDS}"
    --seed-max-len "${SEED_MAX_LEN}"
    --seed-rng "${SEED_RNG}"
    --harness-style "${HARNESS_STYLE}"
    --build
    --build-profile
  )

  for h in "${HEADERS[@]}"; do
    run_all_args+=(--header "${h}")
  done

  if [ "${GENERATE_SEEDS}" = "1" ]; then
    run_all_args+=(--generate-seeds)
  fi

  if [ -n "${DRIVER}" ]; then
    run_all_args+=(--driver "${DRIVER}")
  fi

  for inc in "${TARGET_INCLUDES[@]}"; do
    run_all_args+=(--target-include "${inc}")
  done
  for lib in "${TARGET_LIBS[@]}"; do
    run_all_args+=(--target-lib "${lib}")
  done
  if [ -n "${MINIMUM_APIS}" ]; then
    run_all_args+=(--minimum-apis "${MINIMUM_APIS}")
  fi
  for src in "${EXTRA_SRCS[@]}"; do
    run_all_args+=(--extra-src "${src}")
  done
  for src in "${PROFILE_EXTRA_SRCS[@]}"; do
    run_all_args+=(--profile-extra-src "${src}")
  done
  if [ "${PROFILE_KEEP_TARGET_LIB}" = "1" ]; then
    run_all_args+=(--profile-keep-target-lib)
  fi
  for a in "${GLOBAL_CC_ARGS[@]}"; do
    # Use --cc-arg=<value> so values starting with '-' are unambiguous to argparse.
    run_all_args+=(--cc-arg="${a}")
  done

  # Variant-specific cc args (stored newline-delimited)
  while IFS= read -r a; do
    [ -z "${a}" ] && continue
    run_all_args+=(--cc-arg="${a}")
  done <<< "${VARIANT_CC_ARGS[${variant}]}"

  echo "[Campaign] Building variant '${variant}' -> ${out_dir}"
  python3 "${ROOT_DIR}/src/run_all.py" "${run_all_args[@]}"

  # Save a best-effort list of library sources for llvm-cov -show-functions.
  # (llvm-cov requires explicit source paths for -show-functions.)
  local sources_file="${out_dir}/coverage.sources.txt"
  : > "${sources_file}"
  for src in "${PROFILE_EXTRA_SRCS[@]}"; do
    [ -n "${src}" ] || continue
    abs="$(readlink -f "${src}" 2>/dev/null || true)"
    if [ -n "${abs}" ]; then
      echo "${abs}" >> "${sources_file}"
    fi
  done
}

run_fuzz_variant() {
  local variant="$1"
  local out_dir="${CAMPAIGN_DIR}/${variant}"
  local fuzzer_bin="${out_dir}/${LIBRARY}_fuzzer.bin"
  local profile_bin="${out_dir}/${LIBRARY}_profile.bin"
  local corpus_dir="${out_dir}/corpus"
  local artifacts_dir="${out_dir}/artifacts"
  local api_stats_dir="${out_dir}/api_stats"
  local logs_dir="${out_dir}/logs"
  mkdir -p "${artifacts_dir}" "${logs_dir}" "${api_stats_dir}"

  local -a env_kv=()
  while IFS= read -r kv; do
    [ -z "${kv}" ] && continue
    env_kv+=("${kv}")
  done <<< "${VARIANT_ENVS[${variant}]:-}"

  local start_ts
  start_ts="$(date +%s)"
  local end_ts=$((start_ts + DURATION_SEC))
  local run_i=0

  local live_cov_pid=""
  local live_cov_stop="${logs_dir}/.stop_live_coverage"
  rm -f "${live_cov_stop}" 2>/dev/null || true

  if [ "${LIVE_COVERAGE_INTERVAL_SEC}" -gt 0 ] && [ -f "${profile_bin}" ]; then
    (
      mkdir -p "${out_dir}/profraw" 2>/dev/null || true
      mkdir -p "${out_dir}/corpus_min" 2>/dev/null || true
      while [ ! -f "${live_cov_stop}" ]; do
        # Liberator-style live coverage:
        #   1) minimize corpus (merge=1) -> corpus_min
        #   2) run *_profile.bin on corpus_min to collect profraw
        #   3) merge+report via llvm-cov, filtering harness/bindings/etc.
        #
        # We prefer a minimized corpus so coverage replay finishes quickly and doesn't
        # get stuck (or crash) on a huge corpus. We also reset profraw/profdata each
        # interval to avoid stale metrics if a previous profile run failed.

        # Best-effort corpus minimization (incremental).
        merge_timeout="${PROTO_LIBERATOR_LIVE_COVERAGE_MERGE_TIMEOUT_SEC:-120}"
        PROTO_LIBERATOR_API_STATS="${api_stats_dir}/api_stats_live.json" \
          "${env_kv[@]}" \
          timeout "${merge_timeout}s" "${fuzzer_bin}" -merge=1 "${out_dir}/corpus_min" "${corpus_dir}" -detect_leaks=0 >/dev/null 2>&1 || true

        cov_corpus="${out_dir}/corpus_min"
        if [ ! -d "${cov_corpus}" ] || [ -z "$(ls -A "${cov_corpus}" 2>/dev/null || true)" ]; then
          cov_corpus="${corpus_dir}"
        fi

        # Update a live coverage timeline CSV (appends to coverage/coverage_timeline.csv).
        PROTO_LIBERATOR_API_STATS="${api_stats_dir}/api_stats_live.json" \
          "${env_kv[@]}" \
          timeout 300s "${ROOT_DIR}/scripts/collect_coverage.sh" "${out_dir}" --live --reset \
          --corpus-dir "${cov_corpus}" \
          --sources-file "${out_dir}/coverage.sources.txt" \
          --ignore-file "${ROOT_DIR}/scripts/coverage_ignore_default.txt" \
          >> "${logs_dir}/coverage_live.log" 2>&1 || true
        sleep "${LIVE_COVERAGE_INTERVAL_SEC}" || true
      done
    ) &
    live_cov_pid="$!"
    echo "${live_cov_pid}" > "${logs_dir}/live_coverage.pid"
  fi

  # Ensure LeakSanitizer doesn't terminate the run in restricted environments.
  local asan_opts="${ASAN_OPTIONS:-}"
  if [ -n "${asan_opts}" ]; then
    asan_opts="${asan_opts}:detect_leaks=0"
  else
    asan_opts="detect_leaks=0"
  fi

  echo "[Campaign] Fuzzing '${variant}'..."
  : > "${logs_dir}/fuzz.log"

  while true; do
    local now
    now="$(date +%s)"
    local remaining=$((end_ts - now))
    if [ "${remaining}" -le 0 ]; then
      break
    fi

    run_i=$((run_i + 1))
    {
      echo ""
      echo "===== fuzz run ${run_i} (remaining=${remaining}s) ====="
      date -Is
    } >> "${logs_dir}/fuzz.log"

    local -a argv=(
      "${fuzzer_bin}"
      "${corpus_dir}"
      "-artifact_prefix=${artifacts_dir}/"
      "-detect_leaks=0"
      "-fork=${FORK}"
      "-max_total_time=${remaining}"
      "-max_len=${MAX_LEN}"
      "-timeout=${TIMEOUT_SEC}"
      "-print_final_stats=1"
      "-jobs=${JOBS}"
      "-workers=${WORKERS}"
    )

    if [ "${KEEP_GOING}" = "1" ]; then
      argv+=("-ignore_crashes=1" "-ignore_timeouts=1" "-ignore_ooms=1")
    fi

    for a in "${GLOBAL_FUZZ_ARGS[@]}"; do
      argv+=("${a}")
    done

    while IFS= read -r a; do
      [ -z "${a}" ] && continue
      argv+=("${a}")
    done <<< "${VARIANT_FUZZ_ARGS[${variant}]}"

    set +e
    (cd "${out_dir}" && env ASAN_OPTIONS="${asan_opts}" \
      PROTO_LIBERATOR_API_STATS="${api_stats_dir}/api_stats.json" \
      "${env_kv[@]}" \
      "${argv[@]}") >> "${logs_dir}/fuzz.log" 2>&1
    local rc=$?
    set -e

    echo "${rc}" > "${logs_dir}/fuzz.exit_code"
    echo "${run_i} ${rc}" >> "${logs_dir}/fuzz.exit_codes"

    # If we aren't in keep-going mode, don't restart.
    if [ "${KEEP_GOING}" != "1" ]; then
      break
    fi

    # If libFuzzer exited cleanly, we likely hit -max_total_time.
    if [ "${rc}" -eq 0 ]; then
      break
    fi
  done

  if [ -n "${live_cov_pid}" ]; then
    touch "${live_cov_stop}" 2>/dev/null || true
    kill "${live_cov_pid}" 2>/dev/null || true
    wait "${live_cov_pid}" 2>/dev/null || true
  fi

  # Do not fail the whole campaign on a non-zero libFuzzer exit; crashes are expected.
  return 0
}

postprocess_variant() {
  local variant="$1"
  local out_dir="${CAMPAIGN_DIR}/${variant}"
  local fuzzer_bin="${out_dir}/${LIBRARY}_fuzzer.bin"
  local profile_bin="${out_dir}/${LIBRARY}_profile.bin"
  local corpus_dir="${out_dir}/corpus"
  local corpus_min="${out_dir}/corpus_min"
  local profraw_dir="${out_dir}/profraw"
  local coverage_dir="${out_dir}/coverage"
  local api_stats_dir="${out_dir}/api_stats"
  local casr_dir="${out_dir}/casr"

  mkdir -p "${profraw_dir}" "${coverage_dir}" "${casr_dir}" "${api_stats_dir}"

  local -a env_kv=()
  while IFS= read -r kv; do
    [ -z "${kv}" ] && continue
    env_kv+=("${kv}")
  done <<< "${VARIANT_ENVS[${variant}]:-}"

  if [ -f "${fuzzer_bin}" ] && [ -d "${corpus_dir}" ]; then
    echo "[Campaign] Minimizing corpus for '${variant}'..."
    rm -rf "${corpus_min}"
    mkdir -p "${corpus_min}"
    timeout 30m "${fuzzer_bin}" -merge=1 "${corpus_min}" "${corpus_dir}" >/dev/null 2>&1 || true
  fi

  if [ -f "${profile_bin}" ] && [ -d "${corpus_min}" ]; then
    echo "[Campaign] Profiling coverage for '${variant}'..."
    export LLVM_PROFILE_FILE="${profraw_dir}/final_%m_%p.profraw"

    # Final replay budget controls (wall timeout + per-input timeout inside libFuzzer).
    # Keep these conservative so final coverage completes reliably even on large corpora.
    local final_wall_timeout_sec="${PROTO_LIBERATOR_FINAL_COVERAGE_WALL_TIMEOUT_SEC:-1800}"  # 30m
    local final_input_timeout_sec="${PROTO_LIBERATOR_FINAL_COVERAGE_INPUT_TIMEOUT_SEC:-${TIMEOUT_SEC}}"

    PROTO_LIBERATOR_API_STATS="${api_stats_dir}/api_stats_profile.json" \
      "${env_kv[@]}" \
      timeout "${final_wall_timeout_sec}s" "${profile_bin}" "${corpus_min}" -runs=0 \
      -detect_leaks=0 \
      -timeout="${final_input_timeout_sec}" \
      -fork=1 \
      -ignore_crashes=1 -ignore_timeouts=1 -ignore_ooms=1 \
      -error_exitcode=0 \
      >/dev/null 2>&1 || true
  fi

  echo "[Campaign] Coverage report for '${variant}'..."
  "${ROOT_DIR}/scripts/collect_coverage.sh" "${out_dir}" --final \
    --sources-file "${out_dir}/coverage.sources.txt" \
    --ignore-file "${ROOT_DIR}/scripts/coverage_ignore_default.txt" \
    > "${coverage_dir}/coverage_summary.txt" 2>&1 || true

  if [ -d "${api_stats_dir}" ]; then
    echo "[Campaign] Merging API stats for '${variant}'..."
    "${ROOT_DIR}/scripts/merge_api_stats.py" \
      --input-dir "${api_stats_dir}" \
      --output "${api_stats_dir}/merged_api_stats.json" \
      > "${api_stats_dir}/merge_api_stats.log" 2>&1 || true
  fi

  echo "[Campaign] Crash clustering for '${variant}'..."
  "${ROOT_DIR}/scripts/cluster_crashes.sh" "${out_dir}" > "${casr_dir}/summary.txt" 2>&1 || true
}

PIDS=()
cleanup() {
  if [ "${#PIDS[@]}" -eq 0 ]; then
    return 0
  fi
  for pid in "${PIDS[@]}"; do
    [ -n "${pid}" ] || continue
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT

# Build all variants first (serial, keeps logs simpler and avoids parallel protoc/clang contention).
for v in "${VARIANTS[@]}"; do
  build_variant "${v}"
done

# Run fuzzers in parallel (2–3 variants recommended).
for v in "${VARIANTS[@]}"; do
  run_fuzz_variant "${v}" &
  PIDS+=("$!")
done

for pid in "${PIDS[@]}"; do
  wait "${pid}" || true
done

unset LLVM_PROFILE_FILE || true
PIDS=()

# Post-process each variant (serial).
for v in "${VARIANTS[@]}"; do
  postprocess_variant "${v}"
done

echo "[Campaign] Done: ${CAMPAIGN_DIR}"
