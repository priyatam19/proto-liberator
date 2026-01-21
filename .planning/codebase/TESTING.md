# Testing Patterns

**Analysis Date:** 2026-01-21

## Test Framework

**Runner:**
- unittest (Python standard library)
- Config: No explicit test config file (setup.cfg/pytest.ini not checked in)
- Can also run with pytest: `pytest>=7.0.0` in requirements.txt

**Assertion Library:**
- unittest.TestCase assertions: `assertEqual()`, `assertTrue()`, `assertFalse()`, `assertIn()`

**Run Commands:**
```bash
python3 -m pytest tests/ -v                    # Run all tests with pytest
python3 -m unittest discover tests -v          # Run all tests with unittest
python3 tests/test_proto_generator.py           # Run specific test file
python3 -m pytest tests/test_proto_generator.py -v  # Run with pytest verbose
```

**Coverage:**
```bash
pytest tests/ --cov=src --cov-report=html      # Generate HTML coverage report
pytest tests/ --cov=src --cov-report=term-missing  # Terminal coverage with gaps
```

## Test File Organization

**Location:**
- Tests co-located in `tests/` directory at repo root
- One test file per module: `tests/test_proto_generator.py`, `tests/test_wrapper_generator.py`, `tests/test_seed_generator.py`
- Fixtures in `tests/fixtures/` directory

**Naming:**
- Test files: `test_<module_name>.py` (e.g., `test_proto_generator.py`)
- Test classes: `Test<ModuleName>` (e.g., `TestProtoGenerator`)
- Test methods: `test_<feature_or_scenario>()` (e.g., `test_minimal_golden()`)

**File Structure:**
```
tests/
├── __init__.py                    # (if needed)
├── fixtures/                      # Fixture data
│   ├── minimal_conditions.json
│   ├── minimal_apis_clang.jsonl
│   ├── expected_minimal.proto
│   ├── expected_minimal_v2.proto
│   ├── cjsonish_conditions.json
│   └── handle_conditions.json
├── test_proto_generator.py        # Schema generation tests
├── test_wrapper_generator.py      # (Missing - no harness tests)
├── test_seed_generator.py         # Seed corpus generation
├── test_dependency_index.py       # Dependency index builder
├── test_scheduler.py              # Dependency scheduler
├── test_run_all.py                # Orchestrator integration
└── test_installation.py           # Dependency verification
```

## Test Structure

**Suite Organization (from `test_proto_generator.py`):**
```python
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(SRC_DIR))

from proto_generator import ProtoGenerator

class TestProtoGenerator(unittest.TestCase):
    def test_minimal_golden(self):
        # Setup
        conditions = FIXTURES / "minimal_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"
        expected = (FIXTURES / "expected_minimal.proto").read_text()

        # Execute
        gen = ProtoGenerator(
            conditions_path=conditions,
            apis_path=apis,
            schema_mode="v1",
            max_calls_per_api=4,
            max_bytes_size=65536,
        )
        schema = gen.generate_schema("demo")
        actual = schema.serialize()

        # Assert
        self.assertEqual(actual.strip() + "\n", expected.strip() + "\n")
```

**Patterns:**
- Path discovery: `REPO_ROOT = Path(__file__).resolve().parents[1]` (go up to repo root)
- Fixture loading: `FIXTURES / "minimal_conditions.json"`
- Import path insertion: `sys.path.insert(0, str(SRC_DIR))`
- Setup-Execute-Assert organization: separate fixture loading, action, and assertion phases
- String normalization: `actual.strip() + "\n"` for consistent newline handling

## Golden File Testing

**Approach:**
- Verify generated output matches expected golden file
- Golden files checked into repo: `expected_minimal.proto`, `expected_minimal_v2.proto`, `expected_cjsonish_v2.proto`
- Used by `test_proto_generator.py` for schema validation

**Example (lines 17-32 of `test_proto_generator.py`):**
```python
def test_minimal_golden(self):
    conditions = FIXTURES / "minimal_conditions.json"
    apis = FIXTURES / "minimal_apis_clang.jsonl"
    expected = (FIXTURES / "expected_minimal.proto").read_text()

    gen = ProtoGenerator(
        conditions_path=conditions,
        apis_path=apis,
        schema_mode="v1",
        max_calls_per_api=4,
        max_bytes_size=65536,
    )
    schema = gen.generate_schema("demo")
    actual = schema.serialize()

    self.assertEqual(actual.strip() + "\n", expected.strip() + "\n")
```

## Mocking

**Framework:** No explicit mocking library used (unittest.mock not imported)

**Strategy:**
- No mocks in current test suite (tests are integration-focused)
- Real file I/O: tests load actual fixture JSON/JSONL files
- No external API stubbing needed

**What to Mock (if extending):**
- File system calls: use `unittest.mock.patch('pathlib.Path')`
- Subprocess calls: `unittest.mock.patch('subprocess.check_call')`
- Jinja2 template rendering: `unittest.mock.patch('jinja2.Environment')`

**What NOT to Mock:**
- Proto schema generation (core logic to test)
- Type mapping (deterministic, should be tested against real LLVM types)
- Dependency index building (semantic correctness is critical)

## Fixtures and Test Data

**Test Data Location:**
- `tests/fixtures/` directory
- JSON fixtures: `minimal_conditions.json`, `cjsonish_conditions.json`, `handle_conditions.json`
- JSONL fixtures: `minimal_apis_clang.jsonl`
- Expected outputs: `expected_minimal.proto`, `expected_minimal_v2.proto`, `expected_cjsonish_v2.proto`

**Fixture Format:**

**minimal_conditions.json** (simple function with struct parameter):
```json
[
  {
    "function_name": "Foo",
    "param_0": {
      "param_type": "%struct.Bar*",
      "access_type_set": [{"access": "use"}]
    }
  }
]
```

**minimal_apis_clang.jsonl** (JSONL format, one per line):
```json
{"function_name":"Foo","signature":"void Foo(struct Bar*)","param_types":["struct Bar*"],"return_type":"void"}
```

**Expected outputs:** `.proto` files with exact expected protobuf schema

**Fixture Loading Pattern:**
```python
conditions = FIXTURES / "minimal_conditions.json"
apis = FIXTURES / "minimal_apis_clang.jsonl"
expected = (FIXTURES / "expected_minimal.proto").read_text()

# Used directly in tests:
gen = ProtoGenerator(conditions_path=conditions, apis_path=apis, ...)
```

## Test Types

**Unit Tests:**
- **Schema Generation** (`test_proto_generator.py`):
  - Input: libErator `conditions.json` + `apis_clang.jsonl`
  - Output: `.proto` file syntax
  - Scope: Type mapping, field naming, message generation
  - Example: `test_minimal_golden()`, `test_cjsonish_golden_v2()`

- **Dependency Indexing** (`test_dependency_index.py`):
  - Input: `conditions.json`
  - Output: Dependency graph (APIs, handles, consumers)
  - Scope: Handle type detection, consumer/producer tracking
  - Example: `test_minimal_conditions()` checks API counts and parameter types

- **Seed Generation** (`test_seed_generator.py`):
  - Input: `conditions.json`
  - Output: Binary wire-encoded protobuf
  - Scope: Wire encoding, action variant creation
  - Example: `test_wire_seed_minimal_one_action()` verifies byte sequences

- **Scheduler** (`test_scheduler.py`):
  - Input: Dependency index + API sequence
  - Output: Scheduled sequence with insertions
  - Scope: Handle dependency satisfaction, setup insertion
  - Example: `test_inserts_single_setup_call()` verifies prerequisite injection

**Integration Tests:**
- **Orchestrator** (`test_run_all.py`):
  - Input: CLI arguments
  - Output: Dry-run command trace (no actual execution with `--dry-run`)
  - Scope: Pipeline flow, flag handling
  - Example: `test_dry_run_v2()` checks that proto + wrapper + seed commands are invoked

**E2E Tests:**
- Not present in current suite
- Could test: Full pipeline (schema → nanopb compile → harness compile → fuzzer run)
- Would require: libErator outputs, C compiler, external dependencies

## Common Patterns

**Path Management:**
```python
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SRC_DIR))
```

**Fixture Access:**
```python
conditions = FIXTURES / "minimal_conditions.json"
expected = (FIXTURES / "expected_minimal.proto").read_text()
```

**Constructor with Kwargs:**
```python
gen = ProtoGenerator(
    conditions_path=conditions,
    apis_path=apis,
    schema_mode="v1",
    max_calls_per_api=4,
    max_bytes_size=65536,
)
```

**Golden Comparison:**
```python
actual = schema.serialize()
self.assertEqual(actual.strip() + "\n", expected.strip() + "\n")
```

**Wire Encoding Verification (from `test_seed_generator.py`):**
```python
def test_wire_seed_minimal_one_action(self):
    conditions = FIXTURES / "minimal_conditions.json"
    gen = SeedGenerator(conditions_path=conditions, rng_seed=0)

    variant = gen.action_for_function("Foo")
    data = gen.encode_fuzz_input([variant], global_seed=0)

    # Expected wire:
    # global_seed = 0 -> 08 00
    # actions (field 2) -> 12 <len>
    # Action.oneof Foo tag=1 -> 0A 00 (empty params)
    expected = bytes([0x08, 0x00, 0x12, 0x02, 0x0A, 0x00])
    self.assertEqual(data, expected)
```

**Subprocess Integration (from `test_run_all.py`):**
```python
proc = subprocess.run(
    [
        sys.executable,
        str(SRC_DIR / "run_all.py"),
        "--library", "demo",
        "--conditions", str(conditions),
        "--apis", str(apis),
        "--out-dir", str(out_dir),
        "--schema-mode", "v2",
        "--dry-run",
        "--generate-seeds",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    check=True,
)

self.assertIn("proto_generator.py", proc.stdout)
self.assertIn("wrapper_generator.py", proc.stdout)
```

## Coverage

**Requirements:** No explicit coverage target enforced

**View Coverage:**
```bash
pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

**Coverage Limitations:**
- Wrapper generation not tested (no `test_wrapper_generator.py`)
- E2E fuzzing not in test suite
- Template rendering tested only indirectly (via golden file comparison)

**Gap Areas (prioritized for testing):**
1. **Wrapper template rendering** - high impact, currently untested
2. **C code compilation** - only verified via dry-run
3. **Handle management** - tested at algorithm level, not in harness
4. **EMI guard generation** - untested

## Test Data Management

**Fixture Reuse:**
- `minimal_conditions.json` used by: `test_proto_generator`, `test_dependency_index`, `test_seed_generator`
- `minimal_apis_clang.jsonl` used by: `test_proto_generator`
- `handle_conditions.json` used by: `test_scheduler`

**Golden File Patterns:**
- Versioned by schema mode: `expected_minimal.proto` (v1), `expected_minimal_v2.proto` (v2)
- Library-specific: `expected_cjsonish_v2.proto`

## Running Tests

**Individual Test:**
```bash
python3 -m unittest tests.test_proto_generator.TestProtoGenerator.test_minimal_golden -v
```

**All Tests in File:**
```bash
python3 tests/test_proto_generator.py -v
```

**All Tests:**
```bash
python3 -m pytest tests/ -v
python3 -m unittest discover tests -v
```

**With Coverage:**
```bash
pytest tests/ --cov=src --cov-report=term-missing
```

**Continuous Integration Simulation:**
```bash
python3 -m pytest tests/ -v --tb=short
```

---

*Testing analysis: 2026-01-21*
