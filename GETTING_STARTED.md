# Getting Started with Proto-libErator

Quick start guide for setting up and using Proto-libErator.

---

## Prerequisites

### System Requirements

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    clang-14 llvm-14 \
    protobuf-compiler libprotobuf-dev \
    cmake ninja-build \
    python3 python3-pip \
    git
```

### Python Requirements

```bash
cd /home/priyatam/pin_compete/tools/proto-liberator
pip3 install -r requirements.txt
```

---

## Installation

### Step 1: Build Dependencies

```bash
# Build libprotobuf-mutator and nanopb
./scripts/build_dependencies.sh
```

This will:
- Clone libprotobuf-mutator to `external/`
- Build libprotobuf-mutator static library
- Clone and setup nanopb

**Expected output:**
```
✓ libprotobuf-mutator: external/libprotobuf-mutator/build/src/libprotobuf-mutator.a
✓ nanopb: external/nanopb
```

### Step 2: Setup libErator Integration

```bash
# Create symlinks to libErator analysis results
./setup_symlinks.sh
```

This links:
- `examples/cjson/input/conditions.json` → libErator analysis
- `examples/cjson/input/driver*.meta` → libErator drivers

### Step 3: Verify Installation

```bash
python3 tests/test_installation.py
```

---

## Quick Tutorial: cJSON Example

### Step 1: Generate Protobuf Schema

```bash
python3 src/proto_generator.py \
  --conditions examples/cjson/input/conditions.json \
  --apis examples/cjson/input/apis_clang.json \
  --output examples/cjson/generated/cjson_params.proto \
  --library cjson
```

**Output:** `examples/cjson/generated/cjson_params.proto`

### Step 2: Generate Fuzzing Wrapper

```bash
python3 src/wrapper_generator.py \
  --proto examples/cjson/generated/cjson_params.proto \
  --driver examples/cjson/input/driver0.meta \
  --conditions examples/cjson/input/conditions.json \
  --output examples/cjson/generated/driver0_proto.c
```

**Output:** `examples/cjson/generated/driver0_proto.c`

### Step 3: Build Fuzzer (TODO)

```bash
# TODO: Implement build_proto_fuzzer.sh
./scripts/build_proto_fuzzer.sh \
  --library cjson \
  --wrapper examples/cjson/generated/driver0_proto.c \
  --proto examples/cjson/generated/cjson_params.proto
```

### Step 4: Run Fuzzing (TODO)

```bash
# TODO: Implement run_adaptive_fuzzing.sh
./scripts/run_adaptive_fuzzing.sh \
  --fuzzer build/cjson_proto_fuzzer \
  --duration 3600 \
  --iterations 5
```

---

## Project Structure Overview

```
proto-liberator/
├── src/                    # Source code (Python)
│   ├── proto_generator.py  # conditions.json → .proto
│   ├── wrapper_generator.py # .proto + driver.meta → C
│   ├── type_mapper.py      # LLVM → Protobuf type mapping
│   └── utils.py            # Utilities
│
├── scripts/                # Build & run scripts
│   ├── build_dependencies.sh
│   ├── build_proto_fuzzer.sh  (TODO)
│   └── run_adaptive_fuzzing.sh (TODO)
│
├── examples/               # Example targets
│   └── cjson/
│       ├── input/          # libErator results (symlinked)
│       └── generated/      # Generated proto + wrappers
│
├── external/               # External dependencies
│   ├── libprotobuf-mutator/
│   ├── nanopb/
│   └── liberator/          (symlink)
│
└── docs/                   # Documentation
    ├── LIBERATOR_COMPLETE_MANUAL.md
    ├── LLM_FREE_ARCHITECTURE.md
    └── ...
```

---

## Development Workflow

### 1. Add New Target (e.g., libTIFF)

```bash
# Run libErator analysis first
cd /home/priyatam/pin_compete/tools/liberator
./targets/libtiff/analyze.sh

# Return to proto-liberator
cd /home/priyatam/pin_compete/tools/proto-liberator

# Create example directory
mkdir -p examples/libtiff/input examples/libtiff/generated

# Symlink analysis results
ln -s ../liberator/analysis/libtiff/work/apipass/conditions.json \
      examples/libtiff/input/

# Generate proto
python3 src/proto_generator.py \
  --conditions examples/libtiff/input/conditions.json \
  --apis examples/libtiff/input/apis_clang.json \
  --output examples/libtiff/generated/libtiff_params.proto \
  --library libtiff
```

### 2. Modify Templates

```bash
# Edit wrapper template
vim templates/wrapper.c.j2

# Regenerate wrapper
python3 src/wrapper_generator.py \
  --proto examples/cjson/generated/cjson_params.proto \
  --driver examples/cjson/input/driver0.meta \
  --conditions examples/cjson/input/conditions.json \
  --output examples/cjson/generated/driver0_proto.c
```

### 3. Run Tests

```bash
# Unit tests
python3 -m pytest tests/

# Integration test
./tests/test_full_pipeline.sh cjson
```

---

## Troubleshooting

### Issue: "conditions.json not found"

**Solution:** Run libErator analysis first:
```bash
cd /home/priyatam/pin_compete/tools/liberator
./run_liberator_cjson.sh
```

### Issue: "libprotobuf-mutator.a not found"

**Solution:** Build dependencies:
```bash
./scripts/build_dependencies.sh
```

### Issue: "Module 'jinja2' not found"

**Solution:** Install Python dependencies:
```bash
pip3 install -r requirements.txt
```

### Issue: Generated .proto has syntax errors

**Solution:** Validate with protoc:
```bash
protoc --proto_path=examples/cjson/generated \
       --decode_raw < /dev/null \
       examples/cjson/generated/cjson_params.proto
```

---

## Next Steps

1. **Implement TODO items** - See [PROJECT_STATUS.md](PROJECT_STATUS.md)
2. **Add more examples** - libTIFF, libXML2, libpng
3. **Write tests** - Unit and integration tests
4. **Benchmark** - Compare vs vanilla libErator

---

## Resources

- **Full Manual**: [docs/LIBERATOR_COMPLETE_MANUAL.md](docs/LIBERATOR_COMPLETE_MANUAL.md)
- **Architecture**: [docs/LLM_FREE_ARCHITECTURE.md](docs/LLM_FREE_ARCHITECTURE.md)
- **Status**: [PROJECT_STATUS.md](PROJECT_STATUS.md)
- **libErator**: `/home/priyatam/pin_compete/tools/liberator`

---

## Getting Help

- Check [PROJECT_STATUS.md](PROJECT_STATUS.md) for known issues
- Read [docs/LLM_FREE_ARCHITECTURE.md](docs/LLM_FREE_ARCHITECTURE.md) for design details
- Review libErator manual for background

---

**Happy Fuzzing!**
