#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ANALYSIS_DIR="${ROOT_DIR}/../analysis/cjson/work"
LIB_DIR="${ANALYSIS_DIR}/lib"
APIPASS_DIR="${ANALYSIS_DIR}/apipass"
REPO_DIR="${ROOT_DIR}/../liberator/targets/cjson/repo"

CONDITIONS="${APIPASS_DIR}/conditions.json"
APIS="${APIPASS_DIR}/apis_clang.json"
OUT_ROOT="${ROOT_DIR}/workdir/campaigns"
TARGET_LIB="${LIB_DIR}/libcjson.a"

HEADER_CJSON="cJSON.h"
HEADER_UTILS="cJSON_Utils.h"

PROFILE_SRC_1="${REPO_DIR}/cJSON.c"
PROFILE_SRC_2="${REPO_DIR}/cJSON_Utils.c"

DEFAULT_DURATION_SEC="${DEFAULT_DURATION_SEC:-86400}"
DEFAULT_LIVE_COV_SEC="${DEFAULT_LIVE_COV_SEC:-900}"
DEFAULT_JOBS="${DEFAULT_JOBS:-1}"
DEFAULT_WORKERS="${DEFAULT_WORKERS:-1}"
DEFAULT_MAX_LEN="${DEFAULT_MAX_LEN:-4096}"
DEFAULT_TIMEOUT_SEC="${DEFAULT_TIMEOUT_SEC:-25}"

exec "${SCRIPT_DIR}/run_campaign.sh" \
  --library cjson \
  --conditions "${CONDITIONS}" \
  --apis "${APIS}" \
  --out-root "${OUT_ROOT}" \
  --schema-mode v2 \
  --mutation-mode lpm \
  --max-actions 64 \
  --header "${HEADER_CJSON}" \
  --header "${HEADER_UTILS}" \
  --target-include "${REPO_DIR}" \
  --target-lib "${TARGET_LIB}" \
  --profile-extra-src "${PROFILE_SRC_1}" \
  --profile-extra-src "${PROFILE_SRC_2}" \
  --duration-sec "${DEFAULT_DURATION_SEC}" \
  --live-coverage-interval-sec "${DEFAULT_LIVE_COV_SEC}" \
  --max-len "${DEFAULT_MAX_LEN}" \
  --timeout-sec "${DEFAULT_TIMEOUT_SEC}" \
  --jobs "${DEFAULT_JOBS}" \
  --workers "${DEFAULT_WORKERS}" \
  --keep-going \
  "$@"
