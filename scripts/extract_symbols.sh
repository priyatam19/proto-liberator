#!/bin/bash
# extract_symbols.sh - Extract exported function symbols from library files
# Usage: ./extract_symbols.sh <library-path>

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <library-path>" >&2
    exit 1
fi

LIB_PATH="$1"

if [ ! -f "$LIB_PATH" ]; then
    echo "Error: Library file not found: $LIB_PATH" >&2
    exit 1
fi

# Detect library type by extension
if [[ "$LIB_PATH" == *.so* ]]; then
    # Shared library: use -D flag for dynamic symbols
    nm -D --defined-only --extern-only "$LIB_PATH" 2>/dev/null | awk '$2 == "T" {print $3}'
elif [[ "$LIB_PATH" == *.a ]]; then
    # Static library: no -D flag
    nm --defined-only --extern-only "$LIB_PATH" 2>/dev/null | awk '$2 == "T" {print $3}'
else
    # Try to detect by running nm with -D first, fallback to without
    if nm -D --defined-only --extern-only "$LIB_PATH" 2>/dev/null | awk '$2 == "T" {print $3}' | grep -q .; then
        nm -D --defined-only --extern-only "$LIB_PATH" 2>/dev/null | awk '$2 == "T" {print $3}'
    else
        nm --defined-only --extern-only "$LIB_PATH" 2>/dev/null | awk '$2 == "T" {print $3}'
    fi
fi

# Check if nm command succeeded
if [ $? -ne 0 ]; then
    echo "Error: nm command failed on $LIB_PATH" >&2
    exit 1
fi
