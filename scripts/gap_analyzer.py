#!/usr/bin/env python3
"""
Gap Analyzer - Three-tier function coverage gap analysis for Proto-libErator

Compares function coverage at three tiers:
1. Library exports (nm symbols) vs libErator APIs (apis_clang.json)
2. libErator APIs vs constraints (conditions.json)
3. Constraints vs generated schema (.proto)

Usage:
    python3 scripts/gap_analyzer.py \
        --library cjson \
        --apis-path analysis/cjson/work/apipass/apis_clang.json \
        --conditions-path analysis/cjson/work/apipass/conditions.json \
        --output /tmp/cjson_gap.json \
        --verbose
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Any


def log(msg: str, verbose: bool = True):
    """Print message to stderr if verbose enabled."""
    if verbose:
        print(f"[gap_analyzer] {msg}", file=sys.stderr)


def extract_library_symbols(lib_path: Path, script_dir: Path, verbose: bool = False) -> Set[str]:
    """
    Extract exported function symbols from a library using extract_symbols.sh.

    Args:
        lib_path: Path to .so or .a library file
        script_dir: Directory containing extract_symbols.sh
        verbose: Print progress messages

    Returns:
        Set of function names exported by the library
    """
    script_path = script_dir / "extract_symbols.sh"

    if not script_path.exists():
        log(f"Warning: extract_symbols.sh not found at {script_path}", verbose)
        return set()

    if not lib_path.exists():
        log(f"Warning: Library file not found: {lib_path}", verbose)
        return set()

    try:
        result = subprocess.run(
            [str(script_path), str(lib_path)],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            log(f"Warning: extract_symbols.sh failed: {result.stderr}", verbose)
            return set()

        symbols = set()
        for line in result.stdout.strip().split('\n'):
            # Handle versioned symbols like "malloc@@GLIBC_2.2.5"
            func_name = line.split('@@')[0].strip()
            if func_name:
                symbols.add(func_name)

        log(f"Extracted {len(symbols)} symbols from {lib_path.name}", verbose)
        return symbols

    except subprocess.TimeoutExpired:
        log(f"Warning: extract_symbols.sh timed out for {lib_path}", verbose)
        return set()
    except Exception as e:
        log(f"Warning: Error running extract_symbols.sh: {e}", verbose)
        return set()


def load_apis_clang(path: Path, verbose: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Load apis_clang.json (JSONL format - one JSON object per line).

    Args:
        path: Path to apis_clang.json file
        verbose: Print progress messages

    Returns:
        Dict mapping function_name to full API info
    """
    if not path.exists():
        log(f"Warning: apis_clang.json not found: {path}", verbose)
        return {}

    apis = {}
    try:
        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    func_name = entry.get('function_name', '')
                    if func_name:
                        apis[func_name] = entry
                except json.JSONDecodeError as e:
                    log(f"Warning: Invalid JSON at line {line_num}: {e}", verbose)
                    continue

        log(f"Loaded {len(apis)} APIs from {path.name}", verbose)
        return apis

    except Exception as e:
        log(f"Error loading apis_clang.json: {e}", verbose)
        return {}


def load_conditions(path: Path, verbose: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Load conditions.json (JSON array format).

    Args:
        path: Path to conditions.json file
        verbose: Print progress messages

    Returns:
        Dict mapping function_name to condition info
    """
    if not path.exists():
        log(f"Warning: conditions.json not found: {path}", verbose)
        return {}

    # Check for empty file
    if path.stat().st_size == 0:
        log(f"Warning: conditions.json is empty (0 bytes)", verbose)
        return {}

    try:
        with open(path, 'r') as f:
            data = json.load(f)

        if not isinstance(data, list):
            log(f"Warning: conditions.json is not a JSON array", verbose)
            return {}

        conditions = {}
        for entry in data:
            func_name = entry.get('function_name', '')
            if func_name:
                conditions[func_name] = entry

        log(f"Loaded {len(conditions)} conditions from {path.name}", verbose)
        return conditions

    except json.JSONDecodeError as e:
        log(f"Error parsing conditions.json: {e}", verbose)
        return {}
    except Exception as e:
        log(f"Error loading conditions.json: {e}", verbose)
        return {}


def extract_schema_functions(proto_path: Path, verbose: bool = False) -> Set[str]:
    """
    Extract function names from generated .proto schema.

    Looks for message patterns like "message FuncName_Params {"

    Args:
        proto_path: Path to .proto file
        verbose: Print progress messages

    Returns:
        Set of function names found in schema
    """
    if not proto_path.exists():
        log(f"Warning: Proto file not found: {proto_path}", verbose)
        return set()

    try:
        content = proto_path.read_text()

        # Match "message <FuncName>_Params {"
        pattern = r'message\s+(\w+)_Params\s*\{'
        matches = re.findall(pattern, content)

        functions = set(matches)
        log(f"Found {len(functions)} functions in schema {proto_path.name}", verbose)
        return functions

    except Exception as e:
        log(f"Error reading proto file: {e}", verbose)
        return set()


def categorize_function_gap(
    func_name: str,
    api_info: Optional[Dict[str, Any]],
    condition_info: Optional[Dict[str, Any]]
) -> List[str]:
    """
    Categorize why a function might be missing at a particular tier.

    Categories detected:
    - "varargs" - function has variable arguments (...)
    - "function_pointer_param" - parameter type contains function pointer "(*)("
    - "no_constraints" - function in apis but not in conditions
    - "complex_type" - parameter has union type or multi-dimensional array
    - "unknown" - no obvious pattern detected

    Args:
        func_name: Name of the function
        api_info: Entry from apis_clang.json (or None)
        condition_info: Entry from conditions.json (or None)

    Returns:
        List of category strings explaining why function may be missing
    """
    categories = []

    if api_info is None:
        # Not in API list at all - can't categorize further
        return ['not_in_apis']

    # Check for varargs in arguments
    args_info = api_info.get('arguments_info', [])

    # Varargs check - look for "..." in type or empty last arg indicating varargs
    # Note: libErator may not explicitly record "..." but we check type patterns
    for arg in args_info:
        type_clang = arg.get('type_clang', '')
        if '...' in type_clang or type_clang == 'va_list':
            categories.append('varargs')
            break

    # Function pointer parameter check
    for arg in args_info:
        type_clang = arg.get('type_clang', '')
        # Match patterns like "void (*)(u_char *, ...)" or "int (*callback)(void*)"
        if '(*)' in type_clang or '(*' in type_clang:
            categories.append('function_pointer_param')
            break

    # Complex type check - unions or multi-dimensional arrays
    for arg in args_info:
        type_clang = arg.get('type_clang', '')
        # Union types
        if 'union ' in type_clang.lower():
            categories.append('complex_type')
            break
        # Multi-dimensional arrays like "int[3][3]" or "char **"
        if type_clang.count('*') > 2 or type_clang.count('[') > 1:
            categories.append('complex_type')
            break

    # No constraints check
    if condition_info is None and api_info is not None:
        categories.append('no_constraints')

    # If no categories found, mark as unknown
    if not categories:
        categories.append('unknown')

    return categories


def categorize_gaps(
    gap_functions: List[str],
    api_functions: Dict[str, Dict[str, Any]],
    condition_functions: Dict[str, Dict[str, Any]],
    verbose: bool = False
) -> Dict[str, List[str]]:
    """
    Categorize all functions in a gap list.

    Args:
        gap_functions: List of function names in the gap
        api_functions: Dict of all API info
        condition_functions: Dict of all condition info
        verbose: Print progress messages

    Returns:
        Dict mapping category name to list of functions
    """
    categories: Dict[str, List[str]] = {}

    for func_name in gap_functions:
        api_info = api_functions.get(func_name)
        condition_info = condition_functions.get(func_name)

        func_categories = categorize_function_gap(func_name, api_info, condition_info)

        for cat in func_categories:
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(func_name)

    # Sort function lists within each category
    for cat in categories:
        categories[cat] = sorted(categories[cat])

    return categories


def analyze_gaps(
    library_symbols: Optional[Set[str]],
    api_functions: Set[str],
    condition_functions: Set[str],
    schema_functions: Optional[Set[str]],
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Perform three-tier gap analysis.

    Tier 1: library_symbols - api_functions (not analyzed by libErator)
    Tier 2: api_functions - condition_functions (analyzed but no constraints)
    Tier 3: condition_functions - schema_functions (constraints but excluded)

    Returns:
        Dict with gaps at each tier
    """
    gaps = {
        'tier1_not_analyzed': [],
        'tier2_no_constraints': [],
        'tier3_excluded_schema': []
    }

    # Tier 1: Library exports not in libErator APIs
    if library_symbols is not None:
        tier1_gap = library_symbols - api_functions
        gaps['tier1_not_analyzed'] = sorted(tier1_gap)
        log(f"Tier 1 gap: {len(tier1_gap)} functions not analyzed", verbose)

    # Tier 2: APIs without constraints
    tier2_gap = api_functions - condition_functions
    gaps['tier2_no_constraints'] = sorted(tier2_gap)
    log(f"Tier 2 gap: {len(tier2_gap)} functions without constraints", verbose)

    # Tier 3: Constraints not in schema
    if schema_functions is not None:
        tier3_gap = condition_functions - schema_functions
        gaps['tier3_excluded_schema'] = sorted(tier3_gap)
        log(f"Tier 3 gap: {len(tier3_gap)} functions excluded from schema", verbose)

    return gaps


def compute_coverage(
    library_count: Optional[int],
    api_count: int,
    condition_count: int,
    schema_count: Optional[int]
) -> Dict[str, Optional[float]]:
    """
    Compute coverage percentages at each tier.

    Returns:
        Dict with coverage percentages (None if denominator is 0 or unavailable)
    """
    coverage = {
        'api_coverage': None,
        'constraint_coverage': None,
        'schema_coverage': None
    }

    # API coverage: what % of library exports are analyzed by libErator
    if library_count is not None and library_count > 0:
        coverage['api_coverage'] = round(100.0 * api_count / library_count, 2)

    # Constraint coverage: what % of APIs have constraints
    if api_count > 0:
        coverage['constraint_coverage'] = round(100.0 * condition_count / api_count, 2)

    # Schema coverage: what % of constrained functions are in schema
    if schema_count is not None and condition_count > 0:
        coverage['schema_coverage'] = round(100.0 * schema_count / condition_count, 2)

    return coverage


def generate_report(
    library: str,
    library_symbols: Optional[Set[str]],
    api_functions: Dict[str, Dict[str, Any]],
    condition_functions: Dict[str, Dict[str, Any]],
    schema_functions: Optional[Set[str]],
    gaps: Dict[str, List[str]],
    categorized_gaps: Dict[str, Dict[str, List[str]]],
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Generate the complete gap analysis report.

    Returns:
        Dict containing the full report structure
    """
    api_set = set(api_functions.keys())
    condition_set = set(condition_functions.keys())

    # Compute counts
    counts = {
        'library_exports': len(library_symbols) if library_symbols is not None else None,
        'liberator_apis': len(api_set),
        'with_constraints': len(condition_set),
        'in_schema': len(schema_functions) if schema_functions is not None else None
    }

    # Compute coverage percentages
    coverage = compute_coverage(
        counts['library_exports'],
        counts['liberator_apis'],
        counts['with_constraints'],
        counts['in_schema']
    )

    report = {
        'library': library,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'counts': counts,
        'gaps': gaps,
        'coverage_pct': coverage,
        'categorized_gaps': categorized_gaps
    }

    return report


def main():
    parser = argparse.ArgumentParser(
        description='Three-tier gap analysis for Proto-libErator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--library', required=True,
                        help='Library name (e.g., cjson)')
    parser.add_argument('--lib-path', type=Path, default=None,
                        help='Path to compiled library (.so or .a)')
    parser.add_argument('--apis-path', type=Path, required=True,
                        help='Path to apis_clang.json')
    parser.add_argument('--conditions-path', type=Path, required=True,
                        help='Path to conditions.json')
    parser.add_argument('--proto-path', type=Path, default=None,
                        help='Path to generated .proto schema (optional)')
    parser.add_argument('--output', type=Path, required=True,
                        help='Output JSON report path')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print progress to stderr')

    args = parser.parse_args()

    # Determine script directory for extract_symbols.sh
    script_dir = Path(__file__).parent.resolve()

    log(f"Starting gap analysis for {args.library}", args.verbose)

    # Load data from all sources
    library_symbols = None
    if args.lib_path:
        library_symbols = extract_library_symbols(args.lib_path, script_dir, args.verbose)
        if not library_symbols:
            library_symbols = None  # Treat empty as unavailable

    api_functions = load_apis_clang(args.apis_path, args.verbose)
    condition_functions = load_conditions(args.conditions_path, args.verbose)

    schema_functions = None
    if args.proto_path:
        schema_functions = extract_schema_functions(args.proto_path, args.verbose)
        if not schema_functions:
            schema_functions = None  # Treat empty as unavailable

    # Perform gap analysis
    gaps = analyze_gaps(
        library_symbols,
        set(api_functions.keys()),
        set(condition_functions.keys()),
        schema_functions,
        args.verbose
    )

    # Categorize gaps to explain WHY functions are missing
    categorized_gaps = {}

    # Categorize tier 2 gaps (APIs without constraints)
    if gaps['tier2_no_constraints']:
        categorized_gaps['tier2_by_category'] = categorize_gaps(
            gaps['tier2_no_constraints'],
            api_functions,
            condition_functions,
            args.verbose
        )
        log(f"Tier 2 categories: {list(categorized_gaps['tier2_by_category'].keys())}", args.verbose)

    # Categorize tier 3 gaps (constraints not in schema) - if we have schema
    if gaps['tier3_excluded_schema']:
        categorized_gaps['tier3_by_category'] = categorize_gaps(
            gaps['tier3_excluded_schema'],
            api_functions,
            condition_functions,
            args.verbose
        )
        log(f"Tier 3 categories: {list(categorized_gaps['tier3_by_category'].keys())}", args.verbose)

    # Generate report
    report = generate_report(
        args.library,
        library_symbols,
        api_functions,
        condition_functions,
        schema_functions,
        gaps,
        categorized_gaps,
        args.verbose
    )

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2)

    log(f"Report written to {args.output}", args.verbose)

    # Print summary to stdout
    print(f"Gap Analysis: {args.library}")
    print(f"  Library exports: {report['counts']['library_exports'] or 'N/A'}")
    print(f"  libErator APIs:  {report['counts']['liberator_apis']}")
    print(f"  With constraints: {report['counts']['with_constraints']}")
    print(f"  In schema:       {report['counts']['in_schema'] or 'N/A'}")
    print(f"  Tier 2 gap:      {len(gaps['tier2_no_constraints'])} functions without constraints")


if __name__ == '__main__':
    main()
