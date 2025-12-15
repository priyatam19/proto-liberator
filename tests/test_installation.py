#!/usr/bin/env python3
"""
Proto-libErator - Test Installation Script
Verifies all dependencies and components are properly installed
"""

import sys
import subprocess
from pathlib import Path
import importlib.util

def check_python_module(module_name):
    """Check if a Python module is installed"""
    spec = importlib.util.find_spec(module_name)
    return spec is not None

def check_command(command):
    """Check if a command exists"""
    try:
        subprocess.run([command, '--version'], capture_output=True, check=False, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def main():
    print("=" * 70)
    print("Proto-libErator Installation Verification")
    print("=" * 70)
    print()

    errors = []
    warnings = []

    # Check Python version
    print("[1/8] Checking Python version...")
    if sys.version_info >= (3, 8):
        print(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    else:
        print(f"  ✗ Python {sys.version_info.major}.{sys.version_info.minor} (need 3.8+)")
        errors.append("Python version too old")

    # Check system commands
    print("\n[2/8] Checking system commands...")
    commands = {
        'protoc': 'Protocol Buffers compiler',
        'clang-14': 'Clang compiler (LLVM 14)',
        'cmake': 'CMake build system',
    }

    for cmd, description in commands.items():
        if check_command(cmd):
            print(f"  ✓ {cmd} ({description})")
        else:
            print(f"  ✗ {cmd} ({description}) - NOT FOUND")
            warnings.append(f"{cmd} not found")

    # Check Python modules
    print("\n[3/8] Checking Python modules...")
    modules = {
        'jinja2': 'Template engine (REQUIRED)',
        'yaml': 'YAML parser (optional)',
        'tqdm': 'Progress bars (optional)',
    }

    for module, description in modules.items():
        if check_python_module(module):
            print(f"  ✓ {module} ({description})")
        else:
            print(f"  ✗ {module} ({description}) - NOT INSTALLED")
            if 'REQUIRED' in description:
                errors.append(f"Python module '{module}' not installed")
            else:
                warnings.append(f"Optional module '{module}' not installed")

    # Check project structure
    print("\n[4/8] Checking project structure...")
    project_root = Path(__file__).parent.parent
    required_dirs = [
        'src',
        'docs',
        'scripts',
        'examples',
        'external',
    ]

    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"  ✓ {dir_name}/")
        else:
            print(f"  ✗ {dir_name}/ - NOT FOUND")
            errors.append(f"Missing directory: {dir_name}/")

    # Check source files
    print("\n[5/8] Checking source files...")
    required_files = [
        'src/proto_generator.py',
        'src/type_mapper.py',
        'src/utils.py',
        'src/wrapper_generator.py',
    ]

    for file_path in required_files:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} - NOT FOUND")
            errors.append(f"Missing file: {file_path}")

    # Check libprotobuf-mutator
    print("\n[6/8] Checking libprotobuf-mutator...")
    lpm_lib = project_root / 'external/libprotobuf-mutator/build/src/libprotobuf-mutator.a'
    if lpm_lib.exists():
        print(f"  ✓ libprotobuf-mutator built: {lpm_lib}")
    else:
        print(f"  ✗ libprotobuf-mutator not built")
        print(f"    Run: ./scripts/build_dependencies.sh")
        warnings.append("libprotobuf-mutator not built")

    # Check nanopb
    print("\n[7/8] Checking nanopb...")
    nanopb_gen = project_root / 'external/nanopb/generator/nanopb_generator.py'
    if nanopb_gen.exists():
        print(f"  ✓ nanopb generator: {nanopb_gen}")
    else:
        print(f"  ✗ nanopb not set up")
        print(f"    Run: ./scripts/build_dependencies.sh")
        warnings.append("nanopb not set up")

    # Check libErator integration
    print("\n[8/8] Checking libErator integration...")
    liberator_root = Path('/home/priyatam/pin_compete/tools/liberator')
    if liberator_root.exists():
        print(f"  ✓ libErator found: {liberator_root}")

        # Check for cJSON analysis
        cjson_analysis = liberator_root / 'analysis/cjson/work/apipass/conditions.json'
        if cjson_analysis.exists():
            print(f"  ✓ cJSON analysis results available")
        else:
            print(f"  ⚠ cJSON analysis not found - run libErator first")
            warnings.append("libErator cJSON analysis not available")
    else:
        print(f"  ✗ libErator not found at {liberator_root}")
        warnings.append("libErator not found")

    # Summary
    print("\n" + "=" * 70)
    print("Installation Verification Summary")
    print("=" * 70)

    if not errors and not warnings:
        print("✅ All checks passed! Installation is complete.")
        print("\nNext steps:")
        print("  1. Run: ./setup_symlinks.sh")
        print("  2. Try: python3 src/proto_generator.py --help")
        return 0

    if warnings and not errors:
        print("⚠️  Installation mostly complete with warnings:")
        for warning in warnings:
            print(f"   - {warning}")
        print("\nYou can proceed, but some features may be limited.")
        print("\nTo fix warnings:")
        print("  - Run: ./scripts/build_dependencies.sh")
        print("  - Run: pip install -r requirements.txt")
        return 0

    if errors:
        print("❌ Installation incomplete. Errors found:")
        for error in errors:
            print(f"   - {error}")
        print("\nPlease fix these errors before proceeding.")
        print("\nTo fix:")
        print("  - Install missing dependencies")
        print("  - Run: pip install -r requirements.txt")
        print("  - Check README.md for detailed instructions")
        return 1

if __name__ == '__main__':
    sys.exit(main())
