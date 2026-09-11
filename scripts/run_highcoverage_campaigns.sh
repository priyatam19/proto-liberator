#!/usr/bin/env bash
set -euo pipefail

# Launch one complete Proto-libErator campaign for every library named by
# artifacts/highcoverage_runs.txt. Each per-library campaign is delegated to
# run_campaign.sh, including live and final coverage collection/post-processing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

LIBRARIES_FILE="${ROOT_DIR}/artifacts/highcoverage_runs.txt"
EXPECTED_BRANCH="main"
DURATION_SEC="86400"
COVERAGE_INTERVAL_SEC="900"
MAX_PARALLEL="11"
MAX_ACTIONS="64"
MAX_LEN="4096"
TIMEOUT_SEC="25"
JOBS="1"
WORKERS="1"
FORK="1"
SEED="0"
CLANG="/usr/bin/clang"
PTHREADPOOL_CPUS="${PROTO_LIBERATOR_PTHREADPOOL_CPUS:-0-1}"
OUT_ROOT=""
DRY_RUN="0"
REGENERATE_HARNESSES="0"
FRESH_SEEDS="0"
MAX_ACTIONS_OVERRIDDEN="0"
MAX_LEN_OVERRIDDEN="0"
TIMEOUT_OVERRIDDEN="0"
JOBS_OVERRIDDEN="0"
WORKERS_OVERRIDDEN="0"
FORK_OVERRIDDEN="0"
SEED_OVERRIDDEN="0"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_highcoverage_campaigns.sh [options]

Launches exactly one full Proto-libErator campaign for each of the 11 libraries
derived from artifacts/highcoverage_runs.txt. Live coverage is refreshed every
15 minutes by default.

Options:
  --libraries-file PATH          Coverage-report list used to derive libraries
  --out-root DIR                 Run output (default: artifacts/highcoverage_campaigns/<timestamp>)
  --duration-sec N               Fuzzing time per library (default: 86400 / 24h)
  --coverage-interval-sec N      Live coverage refresh interval (default: 900 / 15m)
  --max-parallel N               Concurrent library campaigns (default: 11)
  --max-actions N                Override the saved campaign profile
  --max-len N                    Override the saved campaign profile
  --timeout-sec N                Override the saved campaign profile
  --jobs N                       Override the saved campaign profile
  --workers N                    Override the saved campaign profile
  --fork N                       Override the saved campaign profile
  --seed N                       Override the deterministic profile seed
  --clang PATH                  Clang executable base (default: /usr/bin/clang)
  --pthreadpool-cpus LIST       CPU list reserved for pthreadpool (default: 0-1)
  --fresh-seeds                 Saved proto/harness, but generate simple seeds
  --regenerate-harnesses        Keep newly generated proto/harness files
  --dry-run                      Preflight inputs and print all 11 commands only
  -h, --help                     Show this help

The launcher must be run from the api-sequencing branch. On Ctrl-C or SIGTERM,
it stops every campaign process it launched. Per-library logs and a results TSV
are saved beneath --out-root.
EOF
}

require_positive_integer() {
  local option="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "[ERROR] ${option} must be a positive integer (got: ${value})" >&2
    exit 2
  fi
}

require_nonnegative_integer() {
  local option="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] ${option} must be a non-negative integer (got: ${value})" >&2
    exit 2
  fi
}

while (( $# > 0 )); do
  case "$1" in
    --libraries-file) LIBRARIES_FILE="${2:-}"; shift 2 ;;
    --out-root) OUT_ROOT="${2:-}"; shift 2 ;;
    --duration-sec) DURATION_SEC="${2:-}"; shift 2 ;;
    --coverage-interval-sec) COVERAGE_INTERVAL_SEC="${2:-}"; shift 2 ;;
    --max-parallel) MAX_PARALLEL="${2:-}"; shift 2 ;;
    --max-actions) MAX_ACTIONS="${2:-}"; MAX_ACTIONS_OVERRIDDEN="1"; shift 2 ;;
    --max-len) MAX_LEN="${2:-}"; MAX_LEN_OVERRIDDEN="1"; shift 2 ;;
    --timeout-sec) TIMEOUT_SEC="${2:-}"; TIMEOUT_OVERRIDDEN="1"; shift 2 ;;
    --jobs) JOBS="${2:-}"; JOBS_OVERRIDDEN="1"; shift 2 ;;
    --workers) WORKERS="${2:-}"; WORKERS_OVERRIDDEN="1"; shift 2 ;;
    --fork) FORK="${2:-}"; FORK_OVERRIDDEN="1"; shift 2 ;;
    --seed) SEED="${2:-}"; SEED_OVERRIDDEN="1"; shift 2 ;;
    --clang) CLANG="${2:-}"; shift 2 ;;
    --pthreadpool-cpus) PTHREADPOOL_CPUS="${2:-}"; shift 2 ;;
    --fresh-seeds) FRESH_SEEDS="1"; shift ;;
    --regenerate-harnesses) REGENERATE_HARNESSES="1"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${FRESH_SEEDS}" == "1" && "${REGENERATE_HARNESSES}" == "1" ]]; then
  echo "[ERROR] --fresh-seeds and --regenerate-harnesses are mutually exclusive." >&2
  exit 2
fi

require_positive_integer --duration-sec "${DURATION_SEC}"
require_positive_integer --coverage-interval-sec "${COVERAGE_INTERVAL_SEC}"
require_positive_integer --max-parallel "${MAX_PARALLEL}"
require_positive_integer --max-actions "${MAX_ACTIONS}"
require_positive_integer --max-len "${MAX_LEN}"
require_positive_integer --timeout-sec "${TIMEOUT_SEC}"
require_positive_integer --jobs "${JOBS}"
require_positive_integer --workers "${WORKERS}"
require_positive_integer --fork "${FORK}"
require_nonnegative_integer --seed "${SEED}"

if [[ "${CLANG}" == */* ]]; then
  if [[ ! -x "${CLANG}" || ! -x "${CLANG}++" ]]; then
    echo "[ERROR] Expected executable compiler pair: ${CLANG} and ${CLANG}++" >&2
    exit 2
  fi
else
  if ! command -v "${CLANG}" >/dev/null 2>&1 || ! command -v "${CLANG}++" >/dev/null 2>&1; then
    echo "[ERROR] Expected compiler pair on PATH: ${CLANG} and ${CLANG}++" >&2
    exit 2
  fi
fi

if ! printf '#include <sanitizer/asan_interface.h>\nint main() { return 0; }\n' \
  | "${CLANG}++" -x c++ -fsyntax-only - >/dev/null 2>&1; then
  echo "[ERROR] ${CLANG}++ cannot compile <sanitizer/asan_interface.h>." >&2
  echo "[ERROR] Select a complete LLVM installation with --clang (for example /usr/bin/clang)." >&2
  exit 2
fi

for command_name in git jq python3 sha256sum tar taskset timeout; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: ${command_name}" >&2
    exit 2
  fi
done

if ! taskset -c "${PTHREADPOOL_CPUS}" true >/dev/null 2>&1; then
  echo "[ERROR] Invalid or unavailable --pthreadpool-cpus list: ${PTHREADPOOL_CPUS}" >&2
  exit 2
fi

if [[ ! -x "${SCRIPT_DIR}/run_campaign.sh" ]]; then
  echo "[ERROR] Campaign runner is missing or not executable: ${SCRIPT_DIR}/run_campaign.sh" >&2
  exit 2
fi
if [[ ! -x "${SCRIPT_DIR}/collect_coverage.sh" ]]; then
  echo "[ERROR] Coverage collector is missing or not executable: ${SCRIPT_DIR}/collect_coverage.sh" >&2
  exit 2
fi

CURRENT_BRANCH="$(git -C "${ROOT_DIR}" branch --show-current)"
if [[ "${CURRENT_BRANCH}" != "${EXPECTED_BRANCH}" ]]; then
  echo "[ERROR] Expected git branch '${EXPECTED_BRANCH}', found '${CURRENT_BRANCH:-detached HEAD}'." >&2
  exit 2
fi

if [[ ! -f "${LIBRARIES_FILE}" ]]; then
  echo "[ERROR] Library source file not found: ${LIBRARIES_FILE}" >&2
  exit 2
fi
LIBRARIES_FILE="$(readlink -f "${LIBRARIES_FILE}")"

ARTIFACTS_DIR="$(readlink -f "${ROOT_DIR}/artifacts")"
declare -a LIBRARIES=()
declare -A LIBRARY_SEEN=()
mapfile -t KNOWN_ANALYSIS_LIBRARIES < <(
  find "${ROOT_DIR}/analysis" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort
)

while IFS= read -r report_path || [[ -n "${report_path}" ]]; do
  report_path="${report_path%$'\r'}"
  [[ -z "${report_path}" || "${report_path}" =~ ^[[:space:]]*# ]] && continue
  if [[ "${report_path}" != "${ARTIFACTS_DIR}/"* ]]; then
    echo "[ERROR] Report path is outside ${ARTIFACTS_DIR}: ${report_path}" >&2
    exit 2
  fi

  relative_path="${report_path#"${ARTIFACTS_DIR}/"}"
  artifact_component="${relative_path%%/*}"
  library="${artifact_component}"
  if [[ -z "${library}" || "${library}" == "${relative_path}" ]]; then
    echo "[ERROR] Could not derive a library from: ${report_path}" >&2
    exit 2
  fi

  # Most reports live under artifacts/<library>/..., but some live beneath a
  # campaign-labelled directory such as minijail_harness_relax_eval_<stamp>.
  # Resolve those labels against the checked-in/local analysis directory names.
  if [[ ! -d "${ROOT_DIR}/analysis/${library}" ]]; then
    declare -a matching_libraries=()
    for known_library in "${KNOWN_ANALYSIS_LIBRARIES[@]}"; do
      if [[ "${artifact_component}" == "${known_library}_"* || "${artifact_component}" == "${known_library}-"* ]]; then
        matching_libraries+=("${known_library}")
      fi
    done
    if (( ${#matching_libraries[@]} != 1 )); then
      echo "[ERROR] Could not uniquely map artifact directory '${artifact_component}' to an analysis library." >&2
      exit 2
    fi
    library="${matching_libraries[0]}"
  fi

  if [[ ! "${library}" =~ ^[A-Za-z0-9_.+-]+$ ]]; then
    echo "[ERROR] Unsafe library name derived from ${report_path}: ${library}" >&2
    exit 2
  fi
  if [[ -z "${LIBRARY_SEEN[${library}]:-}" ]]; then
    LIBRARIES+=("${library}")
    LIBRARY_SEEN["${library}"]="1"
  fi
done < "${LIBRARIES_FILE}"

if (( ${#LIBRARIES[@]} != 11 )); then
  echo "[ERROR] Expected exactly 11 unique libraries in ${LIBRARIES_FILE}; found ${#LIBRARIES[@]}." >&2
  exit 2
fi

if (( MAX_PARALLEL > ${#LIBRARIES[@]} )); then
  MAX_PARALLEL="${#LIBRARIES[@]}"
fi

declare -A TARGET_LIB_HINTS=(
  [cjson]="libcjson.a"
  [c-ares]="libcares_static.a libcares.a"
  [pthreadpool]="libpthreadpool.a"
  [libdwarf]="libdwarf.a"
  [libplist]="libplist-2.0.a"
  [cpu_features]="libcpu_features.a"
  [minijail]="libminijail.pie.a libminijail.a"
  [libhtp]="libhtp.a libhtp-c.a"
  [libpcap]="libpcap.a"
  [libtiff]="libtiff.a"
  [libsndfile]="libsndfile.a"
)

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

preflight_library() {
  local library="$1"
  local apipass_dir="${ROOT_DIR}/analysis/${library}/work/apipass"
  local conditions="${apipass_dir}/conditions.json"
  local apis="${apipass_dir}/apis_clang.json"
  local include_root="${ROOT_DIR}/ground_truths/sources/${library}/work/include"
  local source_root="${ROOT_DIR}/ground_truths/sources/${library}/repo"
  local target_lib_dir="${ROOT_DIR}/ground_truths/sources/${library}/work/lib"
  local driver_meta="${ROOT_DIR}/ground_truths/libraries/${library}/candidate/driver.meta.json"
  local minimum_apis="${apipass_dir}/apis_minimized.txt"
  local target_lib=""
  local saved_sources_dir="${ROOT_DIR}/generated_harnesses/${library}"
  local campaign_profile="${saved_sources_dir}/campaign.json"
  local initial_corpus=""
  local initial_corpus_name=""
  local initial_corpus_sha256=""
  local initial_corpus_files=""
  local actual_corpus_files=""
  local actual_corpus_sha256=""
  local hint
  local header
  local header_match
  local cap_library
  local -a headers=()
  local -a header_matches=()
  local -a include_dirs=("${include_root}")
  local -a fallback_libs=()
  local -A include_seen=(["${include_root}"]="1")

  if [[ "${REGENERATE_HARNESSES}" != "1" ]]; then
    for required_path in \
      "${saved_sources_dir}/${library}.v2.proto" \
      "${saved_sources_dir}/harness.cc" \
      "${campaign_profile}"; do
      if [[ ! -f "${required_path}" ]]; then
        echo "[ERROR] ${library}: required saved campaign source not found: ${required_path}" >&2
        return 1
      fi
    done
    if [[ -d "${source_root}" ]]; then
      include_dirs+=("${source_root}")
      include_seen["${source_root}"]="1"
    fi
    if [[ -d "${source_root}/include" ]]; then
      include_dirs+=("${source_root}/include")
      include_seen["${source_root}/include"]="1"
    fi

    if ! jq -e '
      .version == 1 and
      ([.runtime.max_actions, .runtime.max_len, .runtime.timeout_sec,
        .runtime.jobs, .runtime.workers, .runtime.fork] | all(type == "number" and . > 0 and floor == .)) and
      (.runtime.seed | type == "number" and . >= 0 and floor == .) and
      (.use_minimum_apis | type == "boolean")
    ' "${campaign_profile}" >/dev/null; then
      echo "[ERROR] ${library}: invalid saved campaign profile: ${campaign_profile}" >&2
      return 1
    fi
    if [[ "${FRESH_SEEDS}" != "1" ]]; then
      if ! jq -e '
        (.initial_corpus.archive | type == "string" and length > 0) and
        (.initial_corpus.sha256 | test("^[0-9a-f]{64}$")) and
        (.initial_corpus.files | type == "number" and . > 0 and floor == .)
      ' "${campaign_profile}" >/dev/null; then
        echo "[ERROR] ${library}: invalid saved corpus profile: ${campaign_profile}" >&2
        return 1
      fi
      initial_corpus_name="$(jq -er '.initial_corpus.archive' "${campaign_profile}")"
      if [[ "${initial_corpus_name}" == /* || "${initial_corpus_name}" == *..* || "${initial_corpus_name}" == */* ]]; then
        echo "[ERROR] ${library}: unsafe initial corpus archive name in campaign profile." >&2
        return 1
      fi
      initial_corpus="${saved_sources_dir}/${initial_corpus_name}"
      initial_corpus_sha256="$(jq -er '.initial_corpus.sha256' "${campaign_profile}")"
      initial_corpus_files="$(jq -er '.initial_corpus.files' "${campaign_profile}")"
      if [[ ! -f "${initial_corpus}" ]]; then
        echo "[ERROR] ${library}: initial corpus archive not found: ${initial_corpus}" >&2
        return 1
      fi
      actual_corpus_sha256="$(sha256sum "${initial_corpus}" | awk '{print $1}')"
      if [[ "${actual_corpus_sha256}" != "${initial_corpus_sha256}" ]]; then
        echo "[ERROR] ${library}: initial corpus archive checksum mismatch." >&2
        return 1
      fi
      if tar -tzf "${initial_corpus}" | awk '
          /^\// || /(^|\/)\.\.($|\/)/ { unsafe=1 }
          END { exit unsafe ? 0 : 1 }
        '; then
        echo "[ERROR] ${library}: initial corpus archive contains an unsafe path." >&2
        return 1
      fi
      actual_corpus_files="$(tar -tzf "${initial_corpus}" | awk '!/\/$/ { count++ } END { print count+0 }')"
      if [[ "${actual_corpus_files}" != "${initial_corpus_files}" ]]; then
        echo "[ERROR] ${library}: initial corpus archive file-count mismatch." >&2
        return 1
      fi

      INITIAL_CORPUS_BY_LIB["${library}"]="${initial_corpus}"
      INITIAL_CORPUS_SHA256_BY_LIB["${library}"]="${initial_corpus_sha256}"
    fi
    PROFILE_MAX_ACTIONS_BY_LIB["${library}"]="$(jq -er '.runtime.max_actions' "${campaign_profile}")"
    PROFILE_MAX_LEN_BY_LIB["${library}"]="$(jq -er '.runtime.max_len' "${campaign_profile}")"
    PROFILE_TIMEOUT_BY_LIB["${library}"]="$(jq -er '.runtime.timeout_sec' "${campaign_profile}")"
    PROFILE_JOBS_BY_LIB["${library}"]="$(jq -er '.runtime.jobs' "${campaign_profile}")"
    PROFILE_WORKERS_BY_LIB["${library}"]="$(jq -er '.runtime.workers' "${campaign_profile}")"
    PROFILE_FORK_BY_LIB["${library}"]="$(jq -er '.runtime.fork' "${campaign_profile}")"
    PROFILE_SEED_BY_LIB["${library}"]="$(jq -er '.runtime.seed' "${campaign_profile}")"
  fi

  if [[ ! -f "${apis}" ]]; then
    apis="${apipass_dir}/apis_llvm.json"
  fi

  for required_path in "${conditions}" "${apis}" "${driver_meta}"; do
    if [[ ! -f "${required_path}" ]]; then
      echo "[ERROR] ${library}: required file not found: ${required_path}" >&2
      return 1
    fi
  done
  for required_dir in "${include_root}" "${target_lib_dir}"; do
    if [[ ! -d "${required_dir}" ]]; then
      echo "[ERROR] ${library}: required directory not found: ${required_dir}" >&2
      return 1
    fi
  done

  mapfile -t headers < <(jq -er '.headers[] | select(type == "string" and length > 0)' "${driver_meta}")
  if (( ${#headers[@]} == 0 )); then
    echo "[ERROR] ${library}: no headers in ${driver_meta}" >&2
    return 1
  fi
  if [[ "${library}" == "libdwarf" ]]; then
    headers+=("libdwarf.h")
  fi

  # Some bundles keep public headers one level below include/ while driver.meta
  # records only the basename. Add the matching header directory as another -I.
  for header in "${headers[@]}"; do
    if [[ "${header}" == /* || -f "${include_root}/${header}" ]]; then
      continue
    fi
    mapfile -t header_matches < <(find "${include_root}" -type f -name "$(basename "${header}")" -print | sort)
    if (( ${#header_matches[@]} != 1 )); then
      echo "[ERROR] ${library}: header '${header}' has ${#header_matches[@]} matches beneath ${include_root}" >&2
      return 1
    fi
    header_match="$(dirname "${header_matches[0]}")"
    if [[ -z "${include_seen[${header_match}]:-}" ]]; then
      include_dirs+=("${header_match}")
      include_seen["${header_match}"]="1"
    fi
  done

  for hint in ${TARGET_LIB_HINTS[${library}]:-}; do
    if [[ -f "${target_lib_dir}/${hint}" ]]; then
      target_lib="${target_lib_dir}/${hint}"
      break
    fi
  done
  if [[ -z "${target_lib}" ]]; then
    mapfile -t fallback_libs < <(
      find "${target_lib_dir}" -maxdepth 1 -type f -name '*.a' \
        ! -name '*_profile.a' ! -name '*_cluster.a' | sort
    )
    if (( ${#fallback_libs[@]} != 1 )); then
      echo "[ERROR] ${library}: cannot select one target archive in ${target_lib_dir}" >&2
      return 1
    fi
    target_lib="${fallback_libs[0]}"
  fi

  CONDITIONS_BY_LIB["${library}"]="${conditions}"
  APIS_BY_LIB["${library}"]="${apis}"
  INCLUDE_ROOT_BY_LIB["${library}"]="${include_root}"
  INCLUDE_DIRS_BY_LIB["${library}"]="$(printf '%s\n' "${include_dirs[@]}")"
  TARGET_LIB_BY_LIB["${library}"]="${target_lib}"
  if [[ "${library}" == "minijail" ]]; then
    cap_library="$("${CLANG}" --print-file-name=libcap.so)"
    if [[ "${cap_library}" == "libcap.so" || ! -f "${cap_library}" ]]; then
      echo "[ERROR] ${library}: libcap.so is required but was not found by ${CLANG}" >&2
      return 1
    fi
    EXTRA_TARGET_LIBS_BY_LIB["${library}"]="${cap_library}"
  else
    EXTRA_TARGET_LIBS_BY_LIB["${library}"]=""
  fi
  HEADERS_BY_LIB["${library}"]="$(printf '%s\n' "${headers[@]}")"
  if [[ -f "${minimum_apis}" ]] \
    && { [[ "${REGENERATE_HARNESSES}" == "1" ]] || jq -e '.use_minimum_apis' "${campaign_profile}" >/dev/null; }; then
    MINIMUM_APIS_BY_LIB["${library}"]="${minimum_apis}"
  else
    MINIMUM_APIS_BY_LIB["${library}"]=""
  fi
}

for library in "${LIBRARIES[@]}"; do
  preflight_library "${library}"
done

STAMP="$(date +%Y%m%d_%H%M%S)"
if [[ -z "${OUT_ROOT}" ]]; then
  OUT_ROOT="${ARTIFACTS_DIR}/highcoverage_campaigns/${STAMP}"
elif [[ "${OUT_ROOT}" != /* ]]; then
  OUT_ROOT="$(pwd)/${OUT_ROOT}"
fi

declare -a CAMPAIGN_CMD=()
build_campaign_command() {
  local library="$1"
  local value
  local effective_max_actions="${MAX_ACTIONS}"
  local effective_max_len="${MAX_LEN}"
  local effective_timeout="${TIMEOUT_SEC}"
  local effective_jobs="${JOBS}"
  local effective_workers="${WORKERS}"
  local effective_fork="${FORK}"
  local effective_seed="${SEED}"
  local -a headers=()
  local -a include_dirs=()

  if [[ "${REGENERATE_HARNESSES}" != "1" ]]; then
    [[ "${MAX_ACTIONS_OVERRIDDEN}" == "1" ]] || effective_max_actions="${PROFILE_MAX_ACTIONS_BY_LIB[${library}]}"
    [[ "${MAX_LEN_OVERRIDDEN}" == "1" ]] || effective_max_len="${PROFILE_MAX_LEN_BY_LIB[${library}]}"
    [[ "${TIMEOUT_OVERRIDDEN}" == "1" ]] || effective_timeout="${PROFILE_TIMEOUT_BY_LIB[${library}]}"
    [[ "${JOBS_OVERRIDDEN}" == "1" ]] || effective_jobs="${PROFILE_JOBS_BY_LIB[${library}]}"
    [[ "${WORKERS_OVERRIDDEN}" == "1" ]] || effective_workers="${PROFILE_WORKERS_BY_LIB[${library}]}"
    [[ "${FORK_OVERRIDDEN}" == "1" ]] || effective_fork="${PROFILE_FORK_BY_LIB[${library}]}"
    [[ "${SEED_OVERRIDDEN}" == "1" ]] || effective_seed="${PROFILE_SEED_BY_LIB[${library}]}"
  fi

  CAMPAIGN_CMD=(
    "${SCRIPT_DIR}/run_campaign.sh"
    --library "${library}"
    --conditions "${CONDITIONS_BY_LIB[${library}]}"
    --apis "${APIS_BY_LIB[${library}]}"
    --out-root "${OUT_ROOT}/campaigns"
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
    --target-lib "${TARGET_LIB_BY_LIB[${library}]}"
  )

  mapfile -t headers <<< "${HEADERS_BY_LIB[${library}]}"
  for value in "${headers[@]}"; do
    [[ -n "${value}" ]] && CAMPAIGN_CMD+=(--header "${value}")
  done

  mapfile -t include_dirs <<< "${INCLUDE_DIRS_BY_LIB[${library}]}"
  for value in "${include_dirs[@]}"; do
    [[ -n "${value}" ]] && CAMPAIGN_CMD+=(--target-include "${value}")
  done

  if [[ -n "${MINIMUM_APIS_BY_LIB[${library}]}" ]]; then
    CAMPAIGN_CMD+=(--minimum-apis "${MINIMUM_APIS_BY_LIB[${library}]}")
  fi
  if [[ -n "${EXTRA_TARGET_LIBS_BY_LIB[${library}]}" ]]; then
    CAMPAIGN_CMD+=(--target-lib "${EXTRA_TARGET_LIBS_BY_LIB[${library}]}")
  fi
  if [[ "${REGENERATE_HARNESSES}" != "1" && "${FRESH_SEEDS}" != "1" ]]; then
    CAMPAIGN_CMD+=(
      --initial-corpus-archive "${INITIAL_CORPUS_BY_LIB[${library}]}"
      --initial-corpus-sha256 "${INITIAL_CORPUS_SHA256_BY_LIB[${library}]}"
    )
  fi
  if [[ "${REGENERATE_HARNESSES}" != "1" && "${library}" == "cpu_features" ]]; then
    CAMPAIGN_CMD+=(--cc-arg -DSTACK_LINE_READER_BUFFER_SIZE=1024)
  fi
  if [[ "${library}" == "pthreadpool" ]]; then
    CAMPAIGN_CMD=(taskset -c "${PTHREADPOOL_CPUS}" "${CAMPAIGN_CMD[@]}")
  fi
  if [[ "${REGENERATE_HARNESSES}" == "1" ]]; then
    CAMPAIGN_CMD+=(--regenerate-harnesses)
  fi
}

echo "[Launcher] Branch:            ${CURRENT_BRANCH}"
echo "[Launcher] Libraries source:  ${LIBRARIES_FILE}"
echo "[Launcher] Libraries (11):    ${LIBRARIES[*]}"
echo "[Launcher] Duration/library:  ${DURATION_SEC}s"
echo "[Launcher] Coverage interval: ${COVERAGE_INTERVAL_SEC}s"
echo "[Launcher] Max parallel:      ${MAX_PARALLEL}"
echo "[Launcher] Clang:             ${CLANG}"
echo "[Launcher] pthreadpool CPUs:  ${PTHREADPOOL_CPUS}"
echo "[Launcher] Output root:       ${OUT_ROOT}"

if [[ "${DRY_RUN}" == "1" ]]; then
  echo
  echo "[Launcher] Dry run; commands were not started:"
  for library in "${LIBRARIES[@]}"; do
    build_campaign_command "${library}"
    printf '  '
    printf '%q ' "${CAMPAIGN_CMD[@]}"
    printf '\n'
  done
  exit 0
fi

mkdir -p "${OUT_ROOT}/campaigns" "${OUT_ROOT}/logs"
EVENTS_FILE="${OUT_ROOT}/events.tsv"
RESULTS_FILE="${OUT_ROOT}/results.tsv"
COMMANDS_FILE="${OUT_ROOT}/commands.sh"
CONFIG_FILE="${OUT_ROOT}/launcher.meta.txt"

printf 'timestamp\tlibrary\tevent\tpid\texit_code\n' > "${EVENTS_FILE}"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  for library in "${LIBRARIES[@]}"; do
    build_campaign_command "${library}"
    printf '%q ' "${CAMPAIGN_CMD[@]}"
    printf '\n'
  done
} > "${COMMANDS_FILE}"
chmod +x "${COMMANDS_FILE}"

{
  echo "branch=${CURRENT_BRANCH}"
  echo "commit=$(git -C "${ROOT_DIR}" rev-parse HEAD)"
  echo "libraries_file=${LIBRARIES_FILE}"
  echo "libraries=${LIBRARIES[*]}"
  echo "duration_sec=${DURATION_SEC}"
  echo "coverage_interval_sec=${COVERAGE_INTERVAL_SEC}"
  echo "max_parallel=${MAX_PARALLEL}"
  echo "max_actions=${MAX_ACTIONS}"
  echo "max_len=${MAX_LEN}"
  echo "timeout_sec=${TIMEOUT_SEC}"
  echo "jobs=${JOBS}"
  echo "workers=${WORKERS}"
  echo "fork=${FORK}"
  echo "seed=${SEED}"
  echo "fresh_seeds=${FRESH_SEEDS}"
  echo "clang=${CLANG}"
  echo "pthreadpool_cpus=${PTHREADPOOL_CPUS}"
  echo "started_at=$(date -Is)"
} > "${CONFIG_FILE}"

declare -A PID_TO_LIBRARY=()
declare -A RESULT_BY_LIBRARY=()
RUNNING_COUNT=0
FAILURE_COUNT=0
CLEANING_UP=0

record_event() {
  local library="$1"
  local event="$2"
  local pid="${3:-}"
  local exit_code="${4:-}"
  printf '%s\t%s\t%s\t%s\t%s\n' "$(date -Is)" "${library}" "${event}" "${pid}" "${exit_code}" >> "${EVENTS_FILE}"
}

stop_campaigns() {
  local signal_name="$1"
  local pid
  if (( CLEANING_UP == 1 )); then
    return
  fi
  CLEANING_UP=1
  echo >&2
  echo "[Launcher] Received ${signal_name}; stopping ${RUNNING_COUNT} campaign(s)..." >&2
  for pid in "${!PID_TO_LIBRARY[@]}"; do
    kill "${pid}" 2>/dev/null || true
  done
  for pid in "${!PID_TO_LIBRARY[@]}"; do
    wait "${pid}" 2>/dev/null || true
  done
  exit 130
}
trap 'stop_campaigns SIGINT' INT
trap 'stop_campaigns SIGTERM' TERM

launch_library() {
  local library="$1"
  local log_file="${OUT_ROOT}/logs/${library}.log"
  local pid
  build_campaign_command "${library}"
  "${CAMPAIGN_CMD[@]}" > "${log_file}" 2>&1 &
  pid="$!"
  PID_TO_LIBRARY["${pid}"]="${library}"
  RUNNING_COUNT=$((RUNNING_COUNT + 1))
  record_event "${library}" launched "${pid}"
  echo "[Launcher] Started ${library} (pid=${pid}, log=${log_file})"
}

reap_one_campaign() {
  local finished_pid=""
  local library
  local rc
  if wait -n -p finished_pid "${!PID_TO_LIBRARY[@]}"; then
    rc=0
  else
    rc="$?"
  fi
  if [[ -z "${finished_pid}" ]]; then
    echo "[ERROR] wait completed without identifying a campaign PID" >&2
    exit 1
  fi
  library="${PID_TO_LIBRARY[${finished_pid}]}"
  unset 'PID_TO_LIBRARY['"${finished_pid}"']'
  RUNNING_COUNT=$((RUNNING_COUNT - 1))
  RESULT_BY_LIBRARY["${library}"]="${rc}"
  record_event "${library}" finished "${finished_pid}" "${rc}"
  if (( rc == 0 )); then
    echo "[Launcher] Completed ${library}"
  else
    FAILURE_COUNT=$((FAILURE_COUNT + 1))
    echo "[Launcher] FAILED ${library} (exit=${rc}); see ${OUT_ROOT}/logs/${library}.log" >&2
  fi
}

for library in "${LIBRARIES[@]}"; do
  while (( RUNNING_COUNT >= MAX_PARALLEL )); do
    reap_one_campaign
  done
  launch_library "${library}"
done

while (( RUNNING_COUNT > 0 )); do
  reap_one_campaign
done

printf 'library\tstatus\texit_code\tlog\n' > "${RESULTS_FILE}"
for library in "${LIBRARIES[@]}"; do
  rc="${RESULT_BY_LIBRARY[${library}]:-125}"
  if (( rc == 0 )); then
    status="completed"
  else
    status="failed"
  fi
  printf '%s\t%s\t%s\t%s\n' \
    "${library}" "${status}" "${rc}" "${OUT_ROOT}/logs/${library}.log" >> "${RESULTS_FILE}"
done

echo "[Launcher] Finished all 11 campaigns (${FAILURE_COUNT} failed)."
echo "[Launcher] Results: ${RESULTS_FILE}"
if (( FAILURE_COUNT > 0 )); then
  exit 1
fi
