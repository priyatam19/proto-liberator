#!/usr/bin/env bash
set -euo pipefail

# Resolve one library's campaign args and run a single run_campaign.sh
# --stage against a fixed --campaign-dir. Used by the per-library CI
# pipeline (build / fuzz / postprocess as separate jobs sharing one
# campaign directory) so each job is a single, identical one-line call.
#
# Usage:
#   ci_run_stage.sh <library> <stage> <campaign_dir> <duration_sec> \
#     <coverage_interval_sec> [fork_override] [regenerate_harnesses:0|1] [fresh_seeds:0|1]

LIBRARY="$1"
STAGE="$2"
CAMPAIGN_DIR="$3"
DURATION_SEC="$4"
COVERAGE_INTERVAL_SEC="$5"
FORK_OVERRIDE="${6:-}"
REGENERATE_HARNESSES="${7:-0}"
FRESH_SEEDS="${8:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${CAMPAIGN_DIR}"

EXTRA=()
[[ -n "${FORK_OVERRIDE}" ]] && EXTRA+=(--fork "${FORK_OVERRIDE}")
[[ "${REGENERATE_HARNESSES}" == "1" ]] && EXTRA+=(--regenerate-harnesses)
[[ "${FRESH_SEEDS}" == "1" ]] && EXTRA+=(--fresh-seeds)

mapfile -t LIB_ARGS < <("${SCRIPT_DIR}/resolve_library_campaign.sh" \
  --library "${LIBRARY}" \
  --out-root "${CAMPAIGN_DIR}" \
  --duration-sec "${DURATION_SEC}" \
  --coverage-interval-sec "${COVERAGE_INTERVAL_SEC}" \
  "${EXTRA[@]}")

CMD=("${SCRIPT_DIR}/run_campaign.sh" "${LIB_ARGS[@]}" --campaign-dir "${CAMPAIGN_DIR}" --stage "${STAGE}")
if [[ "${LIBRARY}" == "pthreadpool" ]]; then
  CMD=(taskset -c "${PROTO_LIBERATOR_PTHREADPOOL_CPUS:-0-1}" "${CMD[@]}")
fi

echo "[ci_run_stage] library=${LIBRARY} stage=${STAGE} campaign_dir=${CAMPAIGN_DIR}"
"${CMD[@]}"
