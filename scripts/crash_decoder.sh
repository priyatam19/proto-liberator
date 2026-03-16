#!/bin/bash
set -euo pipefail

# Backward-compatible wrapper around the canonical Python crash classifier.
# Keeps historical entrypoint (`scripts/crash_decoder.sh`) stable.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

exec python3 "${ROOT_DIR}/src/crash_classifier.py" "$@"
