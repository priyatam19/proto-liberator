# Shared library: resolves one library's campaign inputs (conditions/apis
# paths, include dirs, target lib archive, headers, saved corpus/profile
# metadata) into the *_BY_LIB associative arrays below.
#
# Sourced by scripts/run_highcoverage_campaigns.sh (the 11-library batch
# launcher) and scripts/resolve_library_campaign.sh (a single-library CLI
# wrapper used by per-library CI jobs). Extracted so both stay in sync
# instead of maintaining two copies of this resolution logic.
#
# Callers must set before calling preflight_library:
#   ROOT_DIR, CLANG, REGENERATE_HARNESSES ("0"/"1"), FRESH_SEEDS ("0"/"1")

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
