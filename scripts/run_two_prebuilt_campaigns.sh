#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run two prebuilt fuzzers (nanopb + LPM) as two "campaigns", with live libFuzzer
coverage metrics ("cov", "ft", corpus size, exec/s) visible in logs.

Defaults assume the prebuilt fuzzers live at:
  workdir/cjson_e2e/fuzzer
  workdir/cjson_e2e_lpm/cjson_fuzzer.bin

Usage:
  scripts/run_two_prebuilt_campaigns.sh [options]

Options:
  --out-root DIR        Default: workdir/campaigns
  --name NAME           Default: cjson_prebuilt
  --duration-sec N      Default: 86400
  --max-len N           Default: 4096
  --timeout-sec N       Default: 25
  --jobs N              Default: 1
  --workers N           Default: 1
  --keep-going          Add -ignore_crashes/timeouts/ooms=1
  --mode tmux|nohup     Default: nohup
  --session NAME        tmux session name (default: fuzz_cjson_prebuilt)
  -h, --help

After launch:
  - `nohup` mode prints `watch` commands to run in a terminal.
  - `tmux` mode creates a session you can attach to.
EOF
}

OUT_ROOT="workdir/campaigns"
NAME="cjson_prebuilt"
SESSION="fuzz_cjson_prebuilt"
MODE="nohup"
DURATION_SEC="86400"
MAX_LEN="4096"
TIMEOUT_SEC="25"
JOBS="1"
WORKERS="1"
KEEP_GOING="0"

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0;;
    --out-root) OUT_ROOT="${2:-}"; shift 2;;
    --name) NAME="${2:-}"; shift 2;;
    --session) SESSION="${2:-}"; shift 2;;
    --mode) MODE="${2:-}"; shift 2;;
    --duration-sec) DURATION_SEC="${2:-}"; shift 2;;
    --max-len) MAX_LEN="${2:-}"; shift 2;;
    --timeout-sec) TIMEOUT_SEC="${2:-}"; shift 2;;
    --jobs) JOBS="${2:-}"; shift 2;;
    --workers) WORKERS="${2:-}"; shift 2;;
    --keep-going) KEEP_GOING="1"; shift;;
    *) echo "[ERROR] Unknown arg: $1" >&2; usage >&2; exit 2;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

NANOPB_DIR="${ROOT_DIR}/workdir/cjson_e2e"
NANOPB_FUZZER="${NANOPB_DIR}/fuzzer"
LPM_DIR="${ROOT_DIR}/workdir/cjson_e2e_lpm"
LPM_FUZZER="${LPM_DIR}/cjson_fuzzer.bin"

if ! command -v tmux >/dev/null 2>&1; then
  echo "[ERROR] tmux not found in PATH" >&2
  exit 2
fi
if [ ! -x "${NANOPB_FUZZER}" ]; then
  echo "[ERROR] nanopb fuzzer not executable: ${NANOPB_FUZZER}" >&2
  exit 2
fi
if [ ! -x "${LPM_FUZZER}" ]; then
  echo "[ERROR] LPM fuzzer not executable: ${LPM_FUZZER}" >&2
  exit 2
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "${OUT_ROOT}"
OUT_ROOT_ABS="$(cd "${OUT_ROOT}" && pwd)"
CAMPAIGN_DIR="${OUT_ROOT_ABS%/}/${NAME}_${STAMP}"

N_OUT="${CAMPAIGN_DIR}/nanopb"
L_OUT="${CAMPAIGN_DIR}/lpm"
mkdir -p "${N_OUT}/corpus" "${N_OUT}/artifacts" "${N_OUT}/logs"
mkdir -p "${L_OUT}/corpus" "${L_OUT}/artifacts" "${L_OUT}/logs"

# Seed corpuses (optional but helps startup).
if [ -d "${NANOPB_DIR}/corpus" ]; then
  cp -a "${NANOPB_DIR}/corpus/." "${N_OUT}/corpus/" 2>/dev/null || true
fi
touch "${L_OUT}/corpus/seed_empty" 2>/dev/null || true

KEEP_ARGS=""
if [ "${KEEP_GOING}" = "1" ]; then
  KEEP_ARGS="-ignore_crashes=1 -ignore_timeouts=1 -ignore_ooms=1"
fi

# In many sandboxed environments, LeakSanitizer can't run (ptrace restrictions) and will
# terminate the process. Force leak detection off for stability.
ASAN_OPTS="${ASAN_OPTIONS:-}"
if [ -n "${ASAN_OPTS}" ]; then
  ASAN_OPTS="${ASAN_OPTS}:detect_leaks=0"
else
  ASAN_OPTS="detect_leaks=0"
fi

N_CMD="cd '${N_OUT}' && env ASAN_OPTIONS='${ASAN_OPTS}' '${NANOPB_FUZZER}' '${N_OUT}/corpus' -artifact_prefix='${N_OUT}/artifacts/' -detect_leaks=0 -max_total_time='${DURATION_SEC}' -max_len='${MAX_LEN}' -timeout='${TIMEOUT_SEC}' -print_final_stats=1 -jobs='${JOBS}' -workers='${WORKERS}' ${KEEP_ARGS} 2>&1 | tee -a '${N_OUT}/logs/fuzz.log'"
L_CMD="cd '${L_OUT}' && env ASAN_OPTIONS='${ASAN_OPTS}' '${LPM_FUZZER}' '${L_OUT}/corpus' -artifact_prefix='${L_OUT}/artifacts/' -detect_leaks=0 -max_total_time='${DURATION_SEC}' -max_len='${MAX_LEN}' -timeout='${TIMEOUT_SEC}' -print_final_stats=1 -jobs='${JOBS}' -workers='${WORKERS}' ${KEEP_ARGS} 2>&1 | tee -a '${L_OUT}/logs/fuzz.log'"

N_WATCH="watch -n 1 \"echo '[nanopb] corpus='\\\$(find '${N_OUT}/corpus' -type f 2>/dev/null | wc -l) 'artifacts='\\\$(find '${N_OUT}/artifacts' -type f 2>/dev/null | wc -l); awk '/^#/{line=\\\$0} END{print line}' '${N_OUT}/logs/fuzz.log' 2>/dev/null | tail -n 1\""
L_WATCH="watch -n 1 \"echo '[lpm]    corpus='\\\$(find '${L_OUT}/corpus' -type f 2>/dev/null | wc -l) 'artifacts='\\\$(find '${L_OUT}/artifacts' -type f 2>/dev/null | wc -l); awk '/^#/{line=\\\$0} END{print line}' '${L_OUT}/logs/fuzz.log' 2>/dev/null | tail -n 1\""

case "${MODE}" in
  tmux)
    if ! command -v tmux >/dev/null 2>&1; then
      echo "[ERROR] tmux not found in PATH" >&2
      exit 2
    fi
    if tmux has-session -t "${SESSION}" 2>/dev/null; then
      echo "[ERROR] tmux session already exists: ${SESSION}" >&2
      echo "Kill it with: tmux kill-session -t ${SESSION}" >&2
      exit 2
    fi

    # Note: some sandboxed environments disallow unix sockets; if tmux fails, rerun with --mode nohup.
    tmux new-session -d -s "${SESSION}" -n fuzz "bash -lc \"echo 'Campaign dir: ${CAMPAIGN_DIR}'; echo; ${N_CMD}\""
    tmux split-window -h -t "${SESSION}:fuzz" "bash -lc \"${N_WATCH}\""
    tmux split-window -v -t "${SESSION}:fuzz.0" "bash -lc \"${L_CMD}\""
    tmux split-window -v -t "${SESSION}:fuzz.1" "bash -lc \"${L_WATCH}\""
    tmux select-layout -t "${SESSION}:fuzz" tiled >/dev/null

    cat <<EOF
Started tmux session: ${SESSION}
Campaign dir: ${CAMPAIGN_DIR}

Attach:
  tmux attach -t ${SESSION}
EOF
    ;;
  nohup)
    # Start both fuzzers in the background and write pidfiles.
    (bash -lc "set -e; ${N_CMD}") </dev/null >/dev/null 2>&1 &
    echo "$!" > "${N_OUT}/logs/fuzzer.pid"
    (bash -lc "set -e; ${L_CMD}") </dev/null >/dev/null 2>&1 &
    echo "$!" > "${L_OUT}/logs/fuzzer.pid"

    cat <<EOF
Started background fuzzers (nohup-style).
Campaign dir: ${CAMPAIGN_DIR}

Monitor in two terminals:
  ${N_WATCH}
  ${L_WATCH}

Tail logs:
  tail -f '${N_OUT}/logs/fuzz.log'
  tail -f '${L_OUT}/logs/fuzz.log'

Stop:
  kill \$(cat '${N_OUT}/logs/fuzzer.pid') \$(cat '${L_OUT}/logs/fuzzer.pid')
EOF
    ;;
  *)
    echo "[ERROR] Unknown --mode: ${MODE} (expected: tmux|nohup)" >&2
    exit 2
    ;;
esac
