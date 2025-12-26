#!/usr/bin/env python3
"""
Coverage metrics extraction for proto-liberator campaigns.
Matches Liberator paper's methodology: extracts Branch Coverage (column 13).

Usage:
    ./extract_coverage_metrics.py --report <llvm-cov-report.txt> [--output <metrics.json>]
    ./extract_coverage_metrics.py --workdir <campaign_workdir>
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def parse_llvm_cov_report(report_path: str) -> dict:
    """
    Parse llvm-cov report output and extract coverage metrics.
    
    llvm-cov report columns:
    1: Filename
    2: Regions (total)
    3: Missed Regions
    4: Region Cover %
    5: Functions (total)
    6: Missed Functions
    7: Executed Functions %
    8: Lines (total)
    9: Missed Lines
    10: Line Cover %
    11: Branches (total)
    12: Missed Branches
    13: Branch Cover %
    """
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "report_path": str(report_path),
        "files": [],
        "totals": {}
    }
    
    with open(report_path, 'r') as f:
        lines = f.readlines()
    
    # Find the TOTAL line (last non-empty line with numbers)
    total_line = None
    for line in reversed(lines):
        line = line.strip()
        if line and re.match(r'^(TOTAL|Filename)', line) is None:
            # Check if line has numeric data
            parts = line.split()
            if len(parts) >= 13:
                try:
                    # Try to parse as total line
                    total_line = line
                    break
                except:
                    continue
        elif line.startswith('TOTAL'):
            total_line = line
            break
    
    if not total_line:
        # Try to find any line with coverage data
        for line in reversed(lines):
            parts = line.strip().split()
            if len(parts) >= 4:
                total_line = line.strip()
                break
    
    if total_line:
        parts = total_line.split()
        
        # Handle different formats (with/without filename column)
        if parts[0] == 'TOTAL' or not parts[0].replace('.', '').replace('/', '').replace('_', '').isalnum():
            # Standard format with TOTAL label
            offset = 1 if parts[0] == 'TOTAL' else 0
        else:
            offset = 0
        
        try:
            metrics["totals"] = {
                "regions": int(parts[offset + 0]) if len(parts) > offset else 0,
                "missed_regions": int(parts[offset + 1]) if len(parts) > offset + 1 else 0,
                "region_cover": parts[offset + 2] if len(parts) > offset + 2 else "0%",
                "functions": int(parts[offset + 3]) if len(parts) > offset + 3 else 0,
                "missed_functions": int(parts[offset + 4]) if len(parts) > offset + 4 else 0,
                "function_cover": parts[offset + 5] if len(parts) > offset + 5 else "0%",
                "lines": int(parts[offset + 6]) if len(parts) > offset + 6 else 0,
                "missed_lines": int(parts[offset + 7]) if len(parts) > offset + 7 else 0,
                "line_cover": parts[offset + 8] if len(parts) > offset + 8 else "0%",
                "branches": int(parts[offset + 9]) if len(parts) > offset + 9 else 0,
                "missed_branches": int(parts[offset + 10]) if len(parts) > offset + 10 else 0,
                "branch_cover": parts[offset + 11] if len(parts) > offset + 11 else "0%"
            }
        except (ValueError, IndexError) as e:
            print(f"Warning: Could not parse total line: {total_line}", file=sys.stderr)
            print(f"Parts: {parts}", file=sys.stderr)
    
    return metrics


def percent_to_float(pct_str: str) -> float:
    """Convert '75.34%' to 75.34"""
    return float(pct_str.rstrip('%'))


def print_liberator_style_summary(metrics: dict, library_name: str = "unknown"):
    """Print summary matching Liberator paper Tables 4-6 format."""
    totals = metrics.get("totals", {})
    
    print()
    print("=" * 60)
    print(f"COVERAGE METRICS: {library_name}")
    print("=" * 60)
    print(f"Timestamp: {metrics.get('timestamp', 'N/A')}")
    print()
    print(f"Region Coverage:   {totals.get('region_cover', 'N/A')}")
    print(f"Function Coverage: {totals.get('function_cover', 'N/A')}")
    print(f"Line Coverage:     {totals.get('line_cover', 'N/A')}")
    print(f"Branch Coverage:   {totals.get('branch_cover', 'N/A')}  <-- Reported in Tables 4-6")
    print()
    print("Raw Totals:")
    print(f"  Regions:   {totals.get('regions', 0):,} total, {totals.get('missed_regions', 0):,} missed")
    print(f"  Functions: {totals.get('functions', 0):,} total, {totals.get('missed_functions', 0):,} missed")
    print(f"  Lines:     {totals.get('lines', 0):,} total, {totals.get('missed_lines', 0):,} missed")
    print(f"  Branches:  {totals.get('branches', 0):,} total, {totals.get('missed_branches', 0):,} missed")
    print("=" * 60)
    print()


def generate_csv_row(metrics: dict, library_name: str) -> str:
    """Generate CSV row for comparison tables."""
    totals = metrics.get("totals", {})
    branch_cover = totals.get("branch_cover", "0%")
    line_cover = totals.get("line_cover", "0%")
    region_cover = totals.get("region_cover", "0%")
    function_cover = totals.get("function_cover", "0%")
    
    return f"{library_name},{branch_cover},{line_cover},{region_cover},{function_cover}"


def find_coverage_report(workdir: str) -> str:
    """Find the coverage report in a campaign workdir."""
    workdir = Path(workdir)
    
    # Try common locations
    candidates = [
        workdir / "coverage" / "final" / "report_full.txt",
        workdir / "coverage_report.txt",
        workdir / "coverage" / "report_full.txt",
        workdir / "report.txt",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    
    # Search for any report file
    for report_file in workdir.rglob("*report*.txt"):
        if report_file.is_file():
            return str(report_file)
    
    return None


def main():
    parser = argparse.ArgumentParser(description="Extract coverage metrics from llvm-cov report")
    parser.add_argument("--report", "-r", type=str, help="Path to llvm-cov report file")
    parser.add_argument("--workdir", "-w", type=str, help="Campaign workdir to find report in")
    parser.add_argument("--output", "-o", type=str, help="Output JSON file")
    parser.add_argument("--library", "-l", type=str, default="unknown", help="Library name")
    parser.add_argument("--csv", action="store_true", help="Output CSV row only")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    
    args = parser.parse_args()
    
    # Find report file
    report_path = args.report
    if not report_path and args.workdir:
        report_path = find_coverage_report(args.workdir)
        if not report_path:
            print(f"Error: No coverage report found in {args.workdir}", file=sys.stderr)
            sys.exit(1)
    
    if not report_path:
        print("Error: Must specify --report or --workdir", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.exists(report_path):
        print(f"Error: Report file not found: {report_path}", file=sys.stderr)
        sys.exit(1)
    
    # Parse metrics
    metrics = parse_llvm_cov_report(report_path)
    metrics["library"] = args.library
    
    # Output
    if args.csv:
        print("library,branch_cover,line_cover,region_cover,function_cover")
        print(generate_csv_row(metrics, args.library))
    elif args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print_liberator_style_summary(metrics, args.library)
        
        # Also print CSV for easy copy-paste
        print("CSV format (for comparison tables):")
        print("library,branch_cover,line_cover,region_cover,function_cover")
        print(generate_csv_row(metrics, args.library))
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"\nMetrics saved to: {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
