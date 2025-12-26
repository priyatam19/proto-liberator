#!/bin/bash
set -euo pipefail

# Coverage collection script for proto-liberator campaigns
# Matches Liberator paper's methodology: reports Branch Coverage (llvm-cov column 13)
#
# Usage:
#   ./collect_coverage.sh <workdir>
#   ./collect_coverage.sh <workdir> --final
#   ./collect_coverage.sh <workdir> --live
#
# Library-only reporting (like Liberator):
#   ./collect_coverage.sh <workdir> --final --ignore-regex '<regex>'
#   ./collect_coverage.sh <workdir> --final --ignore-file <file-with-regex-lines>
#
# Explicit binary selection:
#   ./collect_coverage.sh <workdir> --final --binary <path/to/*_profile.bin>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ $# -lt 1 ]; then
    echo "Usage: $0 <workdir> [--final|--live] [--binary BIN] [--ignore-regex REGEX] [--ignore-file FILE]"
    exit 0
fi

WORKDIR="$1"
shift

MODE="--final"
BIN_OVERRIDE=""
IGNORE_REGEX=""
IGNORE_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --final|--live)
            MODE="$1"
            shift
            ;;
        --binary)
            BIN_OVERRIDE="${2:-}"
            shift 2
            ;;
        --ignore-regex)
            IGNORE_REGEX="${2:-}"
            shift 2
            ;;
        --ignore-file)
            IGNORE_FILE="${2:-}"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 <workdir> [--final|--live] [--binary BIN] [--ignore-regex REGEX] [--ignore-file FILE]"
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown argument: $1"
            echo "Usage: $0 <workdir> [--final|--live] [--binary BIN] [--ignore-regex REGEX] [--ignore-file FILE]"
            exit 2
            ;;
    esac
done

if [ -n "${IGNORE_FILE}" ]; then
    if [ ! -f "${IGNORE_FILE}" ]; then
        echo "[ERROR] ignore file not found: ${IGNORE_FILE}"
        exit 2
    fi
    # Join non-empty, non-comment lines with '|'
    file_regex=$(grep -vE '^\s*(#|$)' "${IGNORE_FILE}" | paste -sd'|' -)
    if [ -n "${file_regex}" ]; then
        if [ -n "${IGNORE_REGEX}" ]; then
            IGNORE_REGEX="(${IGNORE_REGEX})|(${file_regex})"
        else
            IGNORE_REGEX="${file_regex}"
        fi
    fi
fi

# Find LLVM tools
LLVM_PROFDATA="${LLVM_PROFDATA:-$(which llvm-profdata-14 2>/dev/null || which llvm-profdata 2>/dev/null)}"
LLVM_COV="${LLVM_COV:-$(which llvm-cov-14 2>/dev/null || which llvm-cov 2>/dev/null)}"

if [ -z "$LLVM_PROFDATA" ] || [ -z "$LLVM_COV" ]; then
    echo "[ERROR] llvm-profdata and llvm-cov required"
    exit 1
fi

# Paths
FUZZ_BIN="${WORKDIR}/*_fuzzer.bin"
FUZZ_BIN=$(ls -1 $FUZZ_BIN 2>/dev/null | head -n 1 || true)
PROFILE_BIN=$(ls -1 "${WORKDIR}"/*_profile.bin 2>/dev/null | head -n 1 || true)

if [ -n "${BIN_OVERRIDE}" ]; then
    if [ ! -f "${BIN_OVERRIDE}" ]; then
        echo "[ERROR] binary not found: ${BIN_OVERRIDE}"
        exit 2
    fi
    FUZZ_BIN="${BIN_OVERRIDE}"
elif [ -n "${PROFILE_BIN}" ]; then
    # Prefer coverage-instrumented binary when present.
    FUZZ_BIN="${PROFILE_BIN}"
fi

if [ -z "${FUZZ_BIN}" ] || [ ! -f "${FUZZ_BIN}" ]; then
    echo "[ERROR] No binary found in ${WORKDIR} (expected *_profile.bin or *_fuzzer.bin)."
    exit 2
fi
PROFRAW_DIR="${WORKDIR}/profraw"
CORPUS_DIR="${WORKDIR}/corpus"
COVERAGE_DIR="${WORKDIR}/coverage"
PROFDATA_LIVE="${WORKDIR}/coverage_live.profdata"
PROFDATA_FINAL="${COVERAGE_DIR}/merged.profdata"

mkdir -p "${COVERAGE_DIR}"

echo "========================================"
echo "Proto-libErator Coverage Collection"
echo "========================================"
echo "Workdir:    ${WORKDIR}"
echo "Fuzzer:     ${FUZZ_BIN}"
echo "Mode:       ${MODE}"
if [ -n "${IGNORE_REGEX}" ]; then
    echo "Ignore:     ${IGNORE_REGEX}"
fi
echo "========================================"

# Function to merge profraw files
merge_profraw() {
    local output_profdata="$1"
    local min_age_minutes="${2:-0}"
    
    local profraw_files=()
    
    if [ "$min_age_minutes" -gt 0 ]; then
        # Only files older than min_age_minutes
        mapfile -t profraw_files < <(find "${PROFRAW_DIR}" -maxdepth 1 -type f -name "*.profraw" -mmin +"${min_age_minutes}" 2>/dev/null)
    else
        # All profraw files
        mapfile -t profraw_files < <(find "${PROFRAW_DIR}" -maxdepth 1 -type f -name "*.profraw" 2>/dev/null)
    fi
    
    if [ "${#profraw_files[@]}" -eq 0 ]; then
        echo "[Coverage] No profraw files to merge"
        return 1
    fi
    
    echo "[Coverage] Merging ${#profraw_files[@]} profraw files..."
    
    "${LLVM_PROFDATA}" merge -sparse "${profraw_files[@]}" -o "${output_profdata}"
    
    echo "[Coverage] Created: ${output_profdata}"
    return 0
}

# Function to generate coverage report
generate_report() {
    local profdata="$1"
    local report_dir="$2"
    local ignore_args=()
    if [ -n "${IGNORE_REGEX}" ]; then
        ignore_args+=("--ignore-filename-regex=${IGNORE_REGEX}")
    fi
    
    if [ ! -f "${profdata}" ]; then
        echo "[Coverage] No profdata file: ${profdata}"
        return 1
    fi
    
    if [ ! -f "${FUZZ_BIN}" ]; then
        echo "[Coverage] No fuzzer binary found"
        return 1
    fi
    
    mkdir -p "${report_dir}"
    
    echo "[Coverage] Generating coverage report..."
    
    # Full report (all columns)
    "${LLVM_COV}" report "${FUZZ_BIN}" \
        -instr-profile="${profdata}" \
        "${ignore_args[@]}" \
        > "${report_dir}/report_full.txt" 2>/dev/null || true
    
    # Summary report (last line = TOTAL)
    "${LLVM_COV}" report "${FUZZ_BIN}" \
        -instr-profile="${profdata}" \
        "${ignore_args[@]}" \
        2>/dev/null | tail -5 > "${report_dir}/report_summary.txt" || true
    
    # Show detailed source coverage
    "${LLVM_COV}" show "${FUZZ_BIN}" \
        -instr-profile="${profdata}" \
        -format=text \
        "${ignore_args[@]}" \
        > "${report_dir}/show.txt" 2>/dev/null || true
    
    # Export as JSON for programmatic access
    "${LLVM_COV}" export "${FUZZ_BIN}" \
        -instr-profile="${profdata}" \
        -format=text \
        "${ignore_args[@]}" \
        > "${report_dir}/export.json" 2>/dev/null || true
    
    # Export as LCOV for visualization tools
    "${LLVM_COV}" export "${FUZZ_BIN}" \
        -instr-profile="${profdata}" \
        -format=lcov \
        "${ignore_args[@]}" \
        > "${report_dir}/coverage.lcov" 2>/dev/null || true
    
    # Function-level coverage
    "${LLVM_COV}" report "${FUZZ_BIN}" \
        -instr-profile="${profdata}" \
        -show-functions \
        "${ignore_args[@]}" \
        > "${report_dir}/functions.txt" 2>/dev/null || true
    
    echo "[Coverage] Reports written to: ${report_dir}"
}

# Function to extract coverage metrics (matching Liberator's approach)
extract_metrics() {
    local report_file="$1"
    local output_csv="$2"
    
    if [ ! -f "${report_file}" ]; then
        echo "[Coverage] Report file not found: ${report_file}"
        return 1
    fi
    
    # llvm-cov report columns:
    # 1:Filename 2:Regions 3:MissedRegions 4:RegionCover% 
    # 5:Functions 6:MissedFunctions 7:ExecutedFunctions%
    # 8:Lines 9:MissedLines 10:LineCover%
    # 11:Branches 12:MissedBranches 13:BranchCover%
    
    local total_line=$(tail -n 1 "${report_file}")
    
    # Extract values
    local regions=$(echo "$total_line" | awk '{print $2}')
    local missed_regions=$(echo "$total_line" | awk '{print $3}')
    local region_cover=$(echo "$total_line" | awk '{print $4}')
    local functions=$(echo "$total_line" | awk '{print $5}')
    local missed_functions=$(echo "$total_line" | awk '{print $6}')
    local function_cover=$(echo "$total_line" | awk '{print $7}')
    local lines=$(echo "$total_line" | awk '{print $8}')
    local missed_lines=$(echo "$total_line" | awk '{print $9}')
    local line_cover=$(echo "$total_line" | awk '{print $10}')
    local branches=$(echo "$total_line" | awk '{print $11}')
    local missed_branches=$(echo "$total_line" | awk '{print $12}')
    local branch_cover=$(echo "$total_line" | awk '{print $13}')
    
    # Write CSV header if file doesn't exist
    if [ ! -f "${output_csv}" ]; then
        echo "timestamp,regions,missed_regions,region_cover,functions,missed_functions,function_cover,lines,missed_lines,line_cover,branches,missed_branches,branch_cover" > "${output_csv}"
    fi
    
    # Append metrics
    local timestamp=$(date -Is)
    echo "${timestamp},${regions},${missed_regions},${region_cover},${functions},${missed_functions},${function_cover},${lines},${missed_lines},${line_cover},${branches},${missed_branches},${branch_cover}" >> "${output_csv}"
    
    # Print summary (matching Liberator's Table 4-6 format)
    echo ""
    echo "========================================"
    echo "COVERAGE METRICS (Liberator-style)"
    echo "========================================"
    echo "Region Coverage:   ${region_cover}"
    echo "Function Coverage: ${function_cover}"
    echo "Line Coverage:     ${line_cover}"
    echo "Branch Coverage:   ${branch_cover}  <-- Reported in Tables 4-6"
    echo "========================================"
    echo ""
    echo "Raw totals:"
    echo "  Regions:   ${regions} total, ${missed_regions} missed"
    echo "  Functions: ${functions} total, ${missed_functions} missed"
    echo "  Lines:     ${lines} total, ${missed_lines} missed"
    echo "  Branches:  ${branches} total, ${missed_branches} missed"
    echo "========================================"
}

# Function to run corpus through coverage binary
run_corpus_coverage() {
    local corpus_dir="$1"
    local profraw_output_dir="$2"
    
    if [ ! -d "${corpus_dir}" ]; then
        echo "[Coverage] Corpus directory not found: ${corpus_dir}"
        return 1
    fi
    
    local corpus_count=$(find "${corpus_dir}" -type f | wc -l)
    echo "[Coverage] Running ${corpus_count} corpus files through fuzzer for coverage..."
    
    mkdir -p "${profraw_output_dir}"
    
    local i=0
    for input in "${corpus_dir}"/*; do
        if [ -f "$input" ]; then
            local basename=$(basename "$input")
            export LLVM_PROFILE_FILE="${profraw_output_dir}/corpus_${basename}.profraw"
            timeout 10s "${FUZZ_BIN}" "$input" -runs=0 2>/dev/null || true
            i=$((i + 1))
            if [ $((i % 100)) -eq 0 ]; then
                echo "[Coverage] Processed ${i}/${corpus_count} corpus files..."
            fi
        fi
    done
    
    echo "[Coverage] Finished processing ${i} corpus files"
}

# Try to generate coverage by running the entire corpus directory once.
# This is much faster than iterating over files, because libFuzzer will execute the initial corpus
# and then exit immediately with -runs=0.
run_corpus_dir_once() {
    local corpus_dir="$1"
    local profraw_output_dir="$2"

    if [ ! -d "${corpus_dir}" ]; then
        echo "[Coverage] Corpus directory not found: ${corpus_dir}"
        return 1
    fi

    mkdir -p "${profraw_output_dir}"
    export LLVM_PROFILE_FILE="${profraw_output_dir}/%m_%p.profraw"
    timeout 120s "${FUZZ_BIN}" "${corpus_dir}" -runs=0 2>/dev/null || true

    local count_after
    count_after=$(find "${profraw_output_dir}" -name "*.profraw" 2>/dev/null | wc -l)
    if [ "${count_after}" -gt 0 ]; then
        echo "[Coverage] Generated ${count_after} profraw files from corpus directory run"
        return 0
    fi
    return 1
}

# Main logic based on mode
case "${MODE}" in
    --live)
        # Live mode: merge existing profraw, update live profdata
        echo "[Coverage] Live mode: updating coverage_live.profdata..."
        
        if ! merge_profraw "${PROFDATA_LIVE}" 1; then
            # If nothing is old enough yet, try a best-effort corpus run once to generate profraw,
            # then merge everything (including very recent profraw).
            run_corpus_dir_once "${CORPUS_DIR}" "${PROFRAW_DIR}" || true
            merge_profraw "${PROFDATA_LIVE}" 0 || true
        fi

        if [ -f "${PROFDATA_LIVE}" ]; then
            generate_report "${PROFDATA_LIVE}" "${COVERAGE_DIR}/live"
            extract_metrics "${COVERAGE_DIR}/live/report_full.txt" "${COVERAGE_DIR}/coverage_timeline.csv"
        fi
        ;;
        
    --final)
        # Final mode: comprehensive coverage report
        echo "[Coverage] Final mode: generating comprehensive coverage report..."
        
        # Check if we have profraw files or need to run corpus
        profraw_count=$(find "${PROFRAW_DIR}" -name "*.profraw" 2>/dev/null | wc -l)
        
        if [ "$profraw_count" -eq 0 ]; then
            echo "[Coverage] No profraw files found, running corpus through fuzzer..."
            if ! run_corpus_dir_once "${CORPUS_DIR}" "${PROFRAW_DIR}"; then
                run_corpus_coverage "${CORPUS_DIR}" "${PROFRAW_DIR}"
            fi
        fi
        
        # Merge all profraw
        if merge_profraw "${PROFDATA_FINAL}" 0; then
            generate_report "${PROFDATA_FINAL}" "${COVERAGE_DIR}/final"
            extract_metrics "${COVERAGE_DIR}/final/report_full.txt" "${COVERAGE_DIR}/coverage_final.csv"
            
            # Also save to top-level for easy access
            cp "${COVERAGE_DIR}/coverage_final.csv" "${WORKDIR}/coverage_metrics.csv"
            
            # Create a simple summary file
            cat > "${WORKDIR}/coverage_summary.txt" << EOF
Proto-libErator Coverage Summary
================================
Generated: $(date -Is)
Workdir: ${WORKDIR}

$(cat "${COVERAGE_DIR}/final/report_summary.txt")

Full report: ${COVERAGE_DIR}/final/report_full.txt
Function coverage: ${COVERAGE_DIR}/final/functions.txt
Source coverage: ${COVERAGE_DIR}/final/show.txt
LCOV export: ${COVERAGE_DIR}/final/coverage.lcov
EOF
            echo "[Coverage] Summary written to: ${WORKDIR}/coverage_summary.txt"
        fi
        ;;
        
    --rerun)
        # Re-run corpus to collect fresh coverage
        echo "[Coverage] Re-run mode: collecting fresh coverage from corpus..."
        
        # Clear old profraw
        rm -rf "${PROFRAW_DIR}"/*.profraw 2>/dev/null || true
        
        run_corpus_coverage "${CORPUS_DIR}" "${PROFRAW_DIR}"
        
        if merge_profraw "${PROFDATA_FINAL}" 0; then
            generate_report "${PROFDATA_FINAL}" "${COVERAGE_DIR}/final"
            extract_metrics "${COVERAGE_DIR}/final/report_full.txt" "${COVERAGE_DIR}/coverage_final.csv"
        fi
        ;;
        
    *)
        echo "Unknown mode: ${MODE}"
        echo "Use: --live, --final, or --rerun"
        exit 1
        ;;
esac

echo "[Coverage] Done!"
