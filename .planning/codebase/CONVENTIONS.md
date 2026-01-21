# Coding Conventions

**Analysis Date:** 2026-01-21

## Naming Patterns

**Files:**
- PEP 8 lowercase with underscores: `proto_generator.py`, `wrapper_generator.py`, `seed_generator.py`
- Utility modules are concise: `utils.py`, `contracts.py`, `scheduler.py`
- Template files use `.j2` extension: `wrapper.c.j2`, `wrapper_v2.c.j2`, `wrapper_lpm.cc.j2`

**Functions:**
- Lowercase snake_case: `load_json()`, `save_file()`, `to_proto_field_name()`
- Private module functions prefixed with underscore: `_encode_varint()`, `_param_indices()`, `_return_llvm_type()`
- Descriptive names reflecting action: `load_text_lines()`, `sanitize_identifier()`, `normalize_clang_type()`

**Variables:**
- Snake_case for variables and parameters: `proto_header`, `api_sequence`, `max_handles`
- Global constants UPPERCASE: `MSG_FUZZ_INPUT`, `DEFAULT_MAX_ACTIONS`, `WIRE_VARINT`, `WIRE_LEN`
- Module-level private vars: `_TYPE_HASH_RE` (regex pattern)
- Handle/ID variables: `g_handles`, `g_handle_valid`, `g_handle_count`

**Types and Classes:**
- PascalCase: `ProtoMessage`, `ProtoField`, `ProtoOneof`, `ActionVariant`, `DependencyIndex`, `TypeContext`
- Dataclasses documented: `@dataclass` for structured data, frozen versions for immutable types: `@dataclass(frozen=True)`
- Protocol/type aliases: `TypeContext`, `Cmd`

## Code Style

**Formatting:**
- Tool: No explicit formatter enforced, but code follows PEP 8 conventions
- 4-space indentation (Python) and 2-space indentation for generated protobuf/JSON
- Line length: generally under 100 characters
- Module docstrings present at file top: brief description + key purpose

**Linting:**
- Tools in requirements: `black>=23.0.0`, `mypy>=1.0.0`
- Not configured via `.flake8` or `.pylintrc` (not checked into repo)
- Type hints present throughout: `Path`, `Dict[str, Any]`, `Optional[str]`, `List[str]`

**Imports:**
- Standard library imports first, then third-party, then local
- Explicit imports preferred: `from pathlib import Path` not `import pathlib as pl`
- Dynamic imports allowed for optional dependencies: `try/except ImportError` pattern in `dependency_index.py`, `seed_generator.py`, `wrapper_generator.py` for standalone execution

## Import Organization

**Order:**
1. Shebang: `#!/usr/bin/env python3`
2. Module docstring explaining purpose
3. Standard library imports (`json`, `sys`, `argparse`, `re`, `subprocess`)
4. Third-party imports (`jinja2`, `yaml`, `colorama`, `tqdm`)
5. Local imports with try/except for flexibility

**Path Aliases:**
- Explicit relative paths: `from pathlib import Path`
- Module discovery: `SRC_DIR = REPO_ROOT / "src"` pattern in tests
- Fallback sys.path insertion for standalone scripts

**Example from `dependency_index.py` (lines 18-27):**
```python
try:
    from type_mapper import TypeMapper, TypeContext
    from utils import load_json, load_text_lines
    from wrapper_generator import classify_param, conditions_return_is_handle, index_conditions
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent))
    from type_mapper import TypeMapper, TypeContext
    from utils import load_json, load_text_lines
    from wrapper_generator import classify_param, conditions_return_is_handle, index_conditions
```

## Error Handling

**Patterns:**
- Broad `except Exception:` used for graceful degradation (not strict matching)
  - `dependency_index.py:54-56`: catches JSON parsing errors and empty-file cases
  - `run_all.py:83-85`: catches config parsing, logs and continues
- Specific exceptions only when semantically meaningful:
  - `json.JSONDecodeError` in `proto_generator.py:248-254`
  - `subprocess.CalledProcessError` in `run_all.py:238-240`
  - `SyntaxError` in `run_all.py:131-133`

**Validation:**
- Defensive type checks: `isinstance(data, dict)` before accessing keys
- Safe getters with defaults: `entry.get("function_name") or entry.get("functionName")`
- Range validation: `if idx == 0 or idx > g_handle_count: return`

**Exit Strategy:**
- Uses `raise SystemExit()` for fatal errors with message:
  - `run_all.py:518`: "lpm requires v2 schema"
  - `run_all.py:535`: "driver required for v1"
  - `run_all.py:683`: "seeds only for v2"

## Logging

**Framework:** `print()` statements only (no logging module)

**Patterns:**
- Prefixed output with context tag: `[Proto-libErator]`, `[Orch]`, `[Orch:DRY]`
- Progress messages: `"[Proto-libErator] Generating protobuf schema for {args.library}..."`
- Result messages: `"[Proto-libErator] ✓ Generated: {output_path}"`
- Count reporting: `f"Messages: {len(schema.messages)}"`

**In orchestrator (`run_all.py`):**
- Dry-run prefix: `[Orch:DRY]` when `--dry-run` flag set
- Command echoing: `cmd.to_shell()` for transparency
- Terse output by default (no verbose flag observed)

## Comments

**When to Comment:**
- Module docstrings: Required at file start, explain purpose and contracts
- Class docstrings: Present for classes like `ProtoMessage`, `ProtoField`, `SeedGenerator`
- Function docstrings: Standard format with Args/Returns sections

**Example from `utils.py:11-22`:**
```python
def load_json(file_path: Path) -> Any:
    """
    Load JSON file

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data
    """
    with open(file_path, 'r') as f:
        return json.load(f)
```

**JSDoc/TSDoc:**
- Not used (Python codebase)
- Type hints in function signatures serve the documentation role

**Comments in code:**
- Inline comments minimal, used for algorithm clarity (see `seed_generator.py` wire encoding functions)
- Helper macros documented: `/* Minimal handle table (supports struct-pointer handles as uint32 IDs) */` in Jinja templates
- TODO comments rare: only in `type_mapper.py:479` and `utils.py:266`

## Function Design

**Size:** Generally 10-30 lines, with longer orchestration functions (50+ lines) acceptable for pipeline steps

**Parameters:**
- Keyword-only for clarity: `def schedule_sequence(self, sequence: Iterable[str], *, max_inserts: int = 1)`
- Type hints on all params and returns
- Default args where sensible: `rng_seed: int = 0`, `indent: int = 0`

**Return Values:**
- Explicit return types: `-> Dict[str, Any]`, `-> Optional[str]`, `-> List[str]`
- Tuples for multi-value returns: `Tuple[str, str]` in `_normalize_handle_key()`
- Early returns for guard clauses:
  ```python
  def handle_get(requested, allow_stale, out_selected):
      idx = handle_select(requested)
      if out_selected: *out_selected = idx
      if idx == 0: return None  # guard
      return g_handles[idx]
  ```

## Module Design

**Exports:**
- Classes and functions are public by default
- Module-private conventions via underscore prefix: `_encode_varint()`, `_TYPE_HASH_RE`
- Single-responsibility modules: `contracts.py` (constants only), `utils.py` (helpers)

**Barrel Files:**
- Not used (Python doesn't have barrel exports)
- Imports are explicit from modules

**File Organization Example (`proto_generator.py`):**
1. Shebang + docstring
2. Imports (stdlib, third-party, local)
3. Constants/dataclass definitions: `ProtoField`, `ProtoOneof`, `ProtoMessage`
4. Main class: `ProtoGenerator`
5. CLI entry point: `if __name__ == "__main__"`

## Type System

**Type Hints:**
- Comprehensive use throughout
- From `typing`: `Dict`, `List`, `Optional`, `Tuple`, `Any`, `Iterable`, `Set`
- From `pathlib`: `Path` for all file operations
- From `dataclasses`: `dataclass`, `field`
- Future annotations: `from __future__ import annotations` (in some modules like `dependency_index.py`)

**Generic Types:**
- Dictionary indexing by string: `Dict[str, Dict[str, Any]]`
- Optional parameters: `Optional[Path]`, `Optional[str]`
- Collections: `List[str]`, `Set[str]`, `Iterable[str]`

## Constants and Enums

**Contract Definitions (`contracts.py`):**
```python
MSG_FUZZ_INPUT = "FuzzInput"
MSG_ACTION = "Action"
FIELD_GLOBAL_SEED = "global_seed"
FIELD_ACTIONS = "actions"
FIELD_ACTION_ONEOF = "action"
DEFAULT_MAX_ACTIONS = 64
```

**Local Constants:**
- Wire encoding: `WIRE_VARINT = 0`, `WIRE_LEN = 2` (in `seed_generator.py`)
- Capability flags: `MAX_HANDLES = 1024` in Jinja templates

## Build and Configuration

**No build/config in Python source directly** - delegated to CLI args and templates

**Dataclass for config transport:**
```python
@dataclass(frozen=True)
class Cmd:
    argv: List[str]
    cwd: Optional[Path] = None
    env: Optional[dict] = None
```

---

*Convention analysis: 2026-01-21*
