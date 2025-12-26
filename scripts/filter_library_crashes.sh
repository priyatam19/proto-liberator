#!/bin/bash
set -euo pipefail

# Filter crashes to identify library-only crashes
# (crashes in actual library code, not harness/protobuf infrastructure)
#
# Usage: ./filter_library_crashes.sh <workdir> [--verbose]

if [ $# -lt 1 ]; then
    echo "Usage: $0 <workdir> [--verbose]"
    exit 1
fi

WORKDIR="$1"
VERBOSE="${2:-}"

# Find fuzzer binary
FUZZ_BIN=$(ls -1 "${WORKDIR}"/*_fuzzer.bin 2>/dev/null | head -n 1)
if [ -z "$FUZZ_BIN" ] || [ ! -f "$FUZZ_BIN" ]; then
    echo "[ERROR] No fuzzer binary found in ${WORKDIR}"
    exit 1
fi

# Find crash/artifact directories
CRASH_DIRS=()
for dir in "${WORKDIR}/crashes" "${WORKDIR}/artifacts" "${WORKDIR}/crash-"* "${WORKDIR}"/crash_*; do
    if [ -d "$dir" ]; then
        CRASH_DIRS+=("$dir")
    fi
done

# Also check for crash files directly in workdir
CRASH_FILES=()
for pattern in "${WORKDIR}/crash-"* "${WORKDIR}/leak-"* "${WORKDIR}/timeout-"* "${WORKDIR}/oom-"*; do
    for f in $pattern; do
        if [ -f "$f" ]; then
            CRASH_FILES+=("$f")
        fi
    done
done

# Add files from crash directories
for dir in "${CRASH_DIRS[@]}"; do
    for f in "$dir"/*; do
        if [ -f "$f" ]; then
            CRASH_FILES+=("$f")
        fi
    done
done

if [ ${#CRASH_FILES[@]} -eq 0 ]; then
    echo "[INFO] No crash files found in ${WORKDIR}"
    exit 0
fi

echo "========================================"
echo "Library-Only Crash Filter"
echo "========================================"
echo "Workdir: ${WORKDIR}"
echo "Fuzzer:  ${FUZZ_BIN}"
echo "Total crashes found: ${#CRASH_FILES[@]}"
echo "========================================"

# Patterns to EXCLUDE (infrastructure code)
EXCLUDE_PATTERNS=(
    "harness.cc"
    "\.pb\.cc"
    "\.pb\.h"
    "libprotobuf-mutator"
    "google/protobuf"
    "absl/"
    "libFuzzer"
    "LLVMFuzzer"
    "__sanitizer"
    "__asan"
    "proto-liberator"
)

# Build grep exclude pattern
EXCLUDE_REGEX=$(IFS="|"; echo "${EXCLUDE_PATTERNS[*]}")

# Output directories
mkdir -p "${WORKDIR}/crashes_library_only"
mkdir -p "${WORKDIR}/crashes_infrastructure"
mkdir -p "${WORKDIR}/crash_analysis"

LIBRARY_CRASHES=0
INFRA_CRASHES=0
UNKNOWN_CRASHES=0

# Analyze each crash
for crash_file in "${CRASH_FILES[@]}"; do
    crash_name=$(basename "$crash_file")
    
    # Skip non-crash files
    if [[ ! "$crash_name" =~ ^(crash-|leak-|timeout-|oom-) ]] && [[ ! -f "$crash_file" ]]; then
        continue
    fi
    
    # Run the crash and capture stack trace
    stack_trace=$(timeout 30s "$FUZZ_BIN" "$crash_file" 2>&1 || true)
    
    # Save full stack trace for analysis
    echo "$stack_trace" > "${WORKDIR}/crash_analysis/${crash_name}.trace"
    
    # Extract the crash location (first non-infrastructure frame)
    # Look for #0, #1, etc. frames that are NOT in infrastructure
    crash_location=""
    is_library_crash=false
    
    # Get all stack frames
    frames=$(echo "$stack_trace" | grep -E "^\s*#[0-9]+" || true)
    
    if [ -z "$frames" ]; then
        # No stack trace - might be a timeout or other issue
        ((UNKNOWN_CRASHES++)) || true
        if [ "$VERBOSE" = "--verbose" ]; then
            echo "[UNKNOWN] $crash_name - no stack trace"
        fi
        continue
    fi
    
    # Check each frame to find the crash location
    while IFS= read -r frame; do
        # Skip infrastructure frames
        if echo "$frame" | grep -qE "$EXCLUDE_REGEX"; then
            continue
        fi
        
        # This is the first non-infrastructure frame - likely the crash location
        crash_location="$frame"
        is_library_crash=true
        break
    done <<< "$frames"
    
    if [ "$is_library_crash" = true ]; then
        ((LIBRARY_CRASHES++)) || true
        cp "$crash_file" "${WORKDIR}/crashes_library_only/"
        
        if [ "$VERBOSE" = "--verbose" ]; then
            echo "[LIBRARY] $crash_name"
            echo "         Location: $crash_location"
        fi
    else
        ((INFRA_CRASHES++)) || true
        cp "$crash_file" "${WORKDIR}/crashes_infrastructure/"
        
        if [ "$VERBOSE" = "--verbose" ]; then
            echo "[INFRA]   $crash_name"
            # Show first frame for context
            first_frame=$(echo "$frames" | head -1)
            echo "         Location: $first_frame"
        fi
    fi
done

echo ""
echo "========================================"
echo "Crash Analysis Summary"
echo "========================================"
echo "Total crashes analyzed: ${#CRASH_FILES[@]}"
echo "Library-only crashes:   $LIBRARY_CRASHES"
echo "Infrastructure crashes: $INFRA_CRASHES"
echo "Unknown/No trace:       $UNKNOWN_CRASHES"
echo ""
echo "Library crashes saved to: ${WORKDIR}/crashes_library_only/"
echo "Infrastructure crashes:   ${WORKDIR}/crashes_infrastructure/"
echo "Full traces saved to:     ${WORKDIR}/crash_analysis/"
echo "========================================"

# Create summary JSON
cat > "${WORKDIR}/crash_summary.json" << EOF
{
    "workdir": "${WORKDIR}",
    "total_crashes": ${#CRASH_FILES[@]},
    "library_crashes": $LIBRARY_CRASHES,
    "infrastructure_crashes": $INFRA_CRASHES,
    "unknown_crashes": $UNKNOWN_CRASHES,
    "library_crash_rate": $(echo "scale=2; $LIBRARY_CRASHES * 100 / ${#CRASH_FILES[@]}" | bc 2>/dev/null || echo "0"),
    "timestamp": "$(date -Is)"
}
EOF

echo ""
echo "Summary written to: ${WORKDIR}/crash_summary.json"
