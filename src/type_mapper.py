#!/usr/bin/env python3
"""
Type Mapper - LLVM IR Type to Protobuf Type Mapping
Deterministic, rule-based type conversion
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Optional, Set


_TYPE_HASH_RE = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class TypeContext:
    """
    Per-target type context loaded from libErator apipass artifacts.

    Intended inputs (all optional):
      - enum_types.txt
      - incomplete_types.txt
      - data_layout.txt
      - apis_llvm.json (JSONL) for varargs detection
    """

    enum_types: Set[str] = field(default_factory=set)
    incomplete_types: Set[str] = field(default_factory=set)
    struct_sizes: Dict[str, int] = field(default_factory=dict)
    vararg_functions: Set[str] = field(default_factory=set)

    @staticmethod
    def _read_lines(path: Path) -> Iterable[str]:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            yield line

    @staticmethod
    def _parse_data_layout(path: Path) -> Dict[str, int]:
        """
        Parse `data_layout.txt` lines like:
          struct.aom_codec_dec_cfg 128 <hash> <flag>
        into a mapping with multiple keys:
          - "struct.aom_codec_dec_cfg" -> 128
          - "aom_codec_dec_cfg" -> 128
        """
        out: Dict[str, int] = {}
        for line in TypeContext._read_lines(path):
            parts = line.split()
            if len(parts) < 2:
                continue
            name, size_s = parts[0], parts[1]
            if not name.startswith("struct."):
                continue
            try:
                size = int(size_s)
            except ValueError:
                continue
            out[name] = size
            out[name.removeprefix("struct.")] = size
        return out

    @staticmethod
    def _parse_varargs_from_apis_llvm(path: Path) -> Set[str]:
        """
        Parse `apis_llvm.json` JSONL rows to collect vararg APIs.

        Row format includes:
          {"function_name": "...", "is_vararg": true/false, ...}
        """
        out: Set[str] = set()
        for line in TypeContext._read_lines(path):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("is_vararg") is True and isinstance(row.get("function_name"), str):
                out.add(row["function_name"])
        return out

    @classmethod
    def from_apipass_dir(cls, apipass_dir: Path) -> "TypeContext":
        enum_types_path = apipass_dir / "enum_types.txt"
        incomplete_types_path = apipass_dir / "incomplete_types.txt"
        data_layout_path = apipass_dir / "data_layout.txt"
        apis_llvm_path = apipass_dir / "apis_llvm.json"

        enum_types: Set[str] = set()
        incomplete_types: Set[str] = set()
        struct_sizes: Dict[str, int] = {}
        vararg_functions: Set[str] = set()

        if enum_types_path.exists():
            enum_types = set(cls._read_lines(enum_types_path))

        if incomplete_types_path.exists():
            # Keep raw names; additional normalization can be layered later.
            incomplete_types = set(cls._read_lines(incomplete_types_path))

        if data_layout_path.exists():
            struct_sizes = cls._parse_data_layout(data_layout_path)

        if apis_llvm_path.exists():
            vararg_functions = cls._parse_varargs_from_apis_llvm(apis_llvm_path)

        return cls(
            enum_types=enum_types,
            incomplete_types=incomplete_types,
            struct_sizes=struct_sizes,
            vararg_functions=vararg_functions,
        )

    def struct_size_for(self, struct_name: str) -> Optional[int]:
        """
        Lookup struct size by either "struct.NAME" or "NAME".
        """
        if not struct_name:
            return None
        if struct_name in self.struct_sizes:
            return self.struct_sizes[struct_name]
        k = struct_name.removeprefix("struct.")
        return self.struct_sizes.get(k)


@dataclass(frozen=True)
class TypeClassification:
    """
    Rich classification for an LLVM type string.

    `type_key` is a stable identifier intended to key typed handle tables:
      - struct pointers -> "struct:<name>"
      - primitive pointers -> "ptr:<base>"
      - type hashes -> "hash:<hex>"
      - scalars -> "scalar:<proto_type>"
    """

    kind: str  # scalar|bytes|bytes_array|struct_blob|handle
    proto_type: str
    type_key: str
    llvm_type: str
    is_nullable: bool
    struct_name: str = ""
    struct_size: Optional[int] = None
    is_enum: bool = False
    is_incomplete: bool = False


class TypeMapper:
    """
    Maps LLVM IR types to Protobuf types
    Based on libErator's type_string format and type hashes
    """

    # Static mapping table from LLVM to Protobuf
    LLVM_TO_PROTO = {
        # Integer types
        'i8': 'int32',
        'i16': 'int32',
        'i32': 'int32',
        'i64': 'int64',
        'i128': 'bytes',  # No native i128 in protobuf

        # Unsigned (LLVM doesn't distinguish, but we can infer)
        'u8': 'uint32',
        'u16': 'uint32',
        'u32': 'uint32',
        'u64': 'uint64',

        # Floating point
        'float': 'float',
        'double': 'double',

        # Pointers
        'i8*': 'bytes',
        'i16*': 'bytes',
        'i32*': 'bytes',
        'i64*': 'bytes',
        'float*': 'bytes',
        'double*': 'bytes',
        'void*': 'bytes',

        # Common C types (from clang)
        'char': 'int32',
        'unsigned char': 'uint32',
        'short': 'int32',
        'unsigned short': 'uint32',
        'int': 'int32',
        'unsigned int': 'uint32',
        'long': 'int64',
        'unsigned long': 'uint64',
        'char*': 'bytes',
        'const char*': 'bytes',

        # Type hashes from libErator conditions.json
        'c86ee0d9d7ed3e7b4fdbf486fa6c0ebb': 'int32',   # i32 hash
        'c23fa9996925b610710d93e28c59a3e2': 'double',  # double hash
        '8b336322cb5b10c8b7dac308c85cff15': 'bytes',   # i8* hash
        '13e78f7269fb4001160f783455a4ca4d': 'uint32',  # %struct.cJSON* hash → handle
    }

    @staticmethod
    def map_llvm_to_proto(llvm_type_str: str) -> str:
        """
        Map LLVM type string to protobuf type

        Args:
            llvm_type_str: Type string from conditions.json
                          Examples: "i8*", "%struct.cJSON*", "c86ee0d9d7ed3e7b4fdbf486fa6c0ebb"

        Returns:
            Protobuf type string (e.g., "bytes", "int32", "uint32")
        """
        # Remove qualifiers
        clean_type = TypeMapper.normalize_llvm_type(llvm_type_str)

        # Check direct mapping
        if clean_type in TypeMapper.LLVM_TO_PROTO:
            return TypeMapper.LLVM_TO_PROTO[clean_type]

        # Pointer types
        if clean_type.endswith('*'):
            return TypeMapper._map_pointer_type(clean_type)

        # Struct types
        if clean_type.startswith('%struct.'):
            return 'uint32'  # Struct handle ID

        # Array types
        if '[' in clean_type and ']' in clean_type:
            return 'bytes'  # Arrays as byte buffers

        # Function pointers
        if '(' in clean_type and ')' in clean_type:
            return 'bytes'  # Function pointers as opaque bytes

        # Type hash (40-char hex string)
        if _TYPE_HASH_RE.match(clean_type or ""):
            # Check if it's a known hash
            if clean_type in TypeMapper.LLVM_TO_PROTO:
                return TypeMapper.LLVM_TO_PROTO[clean_type]
            # Unknown hash → assume pointer/handle
            return 'uint32'

        # Default fallback
        return 'bytes'

    @staticmethod
    def normalize_llvm_type(llvm_type_str: str) -> str:
        clean_type = str(llvm_type_str or "")
        clean_type = clean_type.replace("const ", "")
        clean_type = clean_type.replace("volatile ", "")
        clean_type = clean_type.replace("restrict ", "")
        return " ".join(clean_type.strip().split())

    @staticmethod
    def _map_pointer_type(pointer_type: str) -> str:
        """
        Map pointer types specifically

        Args:
            pointer_type: Type string ending with '*'

        Returns:
            Protobuf type
        """
        base_type = pointer_type[:-1].strip()

        # Struct pointers → Handle IDs
        if base_type.startswith('%struct.'):
            return 'uint32'

        # Char pointer → bytes (string/buffer)
        if base_type in ['i8', 'char', 'unsigned char']:
            return 'bytes'

        # Void pointer → bytes
        if base_type == 'void':
            return 'bytes'

        # Primitive pointer → bytes (buffer of primitives)
        if base_type in ['i16', 'i32', 'i64', 'float', 'double']:
            return 'bytes'

        # Generic pointer → bytes
        return 'bytes'

    @staticmethod
    def is_handle_type(llvm_type_str: str) -> bool:
        """
        Check if type should be represented as a handle (uint32)

        Args:
            llvm_type_str: LLVM type string

        Returns:
            True if this is a struct pointer (handle type)
        """
        clean_type = llvm_type_str.replace('const ', '').strip()

        # Struct pointers are handles
        if clean_type.endswith('*'):
            base = clean_type[:-1].strip()
            if base.startswith('%struct.'):
                return True

        # Known struct type hashes
        if clean_type == '13e78f7269fb4001160f783455a4ca4d':  # cJSON*
            return True

        return False

    @staticmethod
    def extract_struct_name(llvm_type_str: str) -> str:
        """
        Extract struct name from LLVM type

        Args:
            llvm_type_str: e.g., "%struct.cJSON*" or "%struct.mg_mqtt_opts"

        Returns:
            Struct name (e.g., "cJSON", "mg_mqtt_opts") or empty string
        """
        clean_type = llvm_type_str.replace('const ', '').replace('*', '').strip()

        if clean_type.startswith('%struct.'):
            return clean_type.replace('%struct.', '')

        return ""

    @staticmethod
    def type_key(llvm_type_str: str) -> str:
        """
        Stable ID per “object type” so different pointer kinds can't be mixed.
        """
        clean = TypeMapper.normalize_llvm_type(llvm_type_str)
        if _TYPE_HASH_RE.match(clean or ""):
            return f"hash:{clean}"

        if clean.startswith("%struct."):
            name = TypeMapper.extract_struct_name(clean)
            return f"struct:{name}" if name else "struct:<unknown>"

        if clean.endswith("*"):
            base = clean[:-1].strip()
            if base.startswith("%struct."):
                name = TypeMapper.extract_struct_name(base)
                return f"struct:{name}" if name else "struct:<unknown>"
            base = base.replace(" ", "")
            return f"ptr:{base}"

        proto = TypeMapper.map_llvm_to_proto(clean)
        return f"scalar:{proto}"

    @staticmethod
    def classify_llvm_type(
        llvm_type_str: str,
        *,
        context: Optional[TypeContext] = None,
        is_array: bool = False,
    ) -> TypeClassification:
        """
        Richer classification than `map_llvm_to_proto()`.
        """
        clean = TypeMapper.normalize_llvm_type(llvm_type_str)
        is_nullable = bool(is_array or clean.endswith("*") or clean.startswith("%struct."))

        if is_array:
            # Arrays are always bytes payload + length controls at the message level.
            return TypeClassification(
                kind="bytes_array",
                proto_type="bytes",
                type_key=TypeMapper.type_key(clean),
                llvm_type=clean,
                is_nullable=True,
            )

        # Enum handling: treat as scalar, but preserve enum-ness for later codegen.
        is_enum = bool(context and clean in context.enum_types)
        if is_enum:
            return TypeClassification(
                kind="scalar",
                proto_type="int32",
                type_key=f"enum:{clean}",
                llvm_type=clean,
                is_nullable=False,
                is_enum=True,
            )

        # Struct pointers: prefer struct blob when layout is known; otherwise handle.
        if clean.startswith("%struct."):
            struct_name = TypeMapper.extract_struct_name(clean)
            size = context.struct_size_for(struct_name) if context and struct_name else None
            kind = "struct_blob" if size is not None else "handle"
            proto_type = "bytes" if kind == "struct_blob" else "uint32"
            return TypeClassification(
                kind=kind,
                proto_type=proto_type,
                type_key=TypeMapper.type_key(clean),
                llvm_type=clean,
                is_nullable=True,
                struct_name=struct_name,
                struct_size=size,
            )

        if clean.endswith("*"):
            base = clean[:-1].strip()
            if base.startswith("%struct."):
                struct_name = TypeMapper.extract_struct_name(base)
                size = context.struct_size_for(struct_name) if context and struct_name else None
                kind = "struct_blob" if size is not None else "handle"
                proto_type = "bytes" if kind == "struct_blob" else "uint32"
                return TypeClassification(
                    kind=kind,
                    proto_type=proto_type,
                    type_key=TypeMapper.type_key(clean),
                    llvm_type=clean,
                    is_nullable=True,
                    struct_name=struct_name,
                    struct_size=size,
                )
            # Non-struct pointers are bytes by default.
            return TypeClassification(
                kind="bytes",
                proto_type="bytes",
                type_key=TypeMapper.type_key(clean),
                llvm_type=clean,
                is_nullable=True,
            )

        proto = TypeMapper.map_llvm_to_proto(clean)
        kind = "scalar" if proto != "bytes" else "bytes"
        return TypeClassification(
            kind=kind,
            proto_type=proto,
            type_key=TypeMapper.type_key(clean),
            llvm_type=clean,
            is_nullable=is_nullable,
        )

    @staticmethod
    def is_pointer_like_llvm(llvm_type_str: str) -> bool:
        clean = TypeMapper.normalize_llvm_type(llvm_type_str)
        if not clean:
            return False
        if clean.endswith("*"):
            return True
        if clean.startswith("%struct."):
            return True
        if "[" in clean and "]" in clean:
            return True
        if "(" in clean and ")" in clean:
            return True
        return False

    @staticmethod
    def is_integral_proto_type(proto_type: str) -> bool:
        return proto_type in {
            "int32",
            "int64",
            "uint32",
            "uint64",
            "sint32",
            "sint64",
            "fixed32",
            "fixed64",
            "sfixed32",
            "sfixed64",
        }

    @staticmethod
    def is_scalar_producer_return(llvm_type_str: str) -> bool:
        """
        True for scalar (non-pointer, non-void) integral returns suitable for
        value-flow binding into downstream scalar params.
        """
        clean = TypeMapper.normalize_llvm_type(llvm_type_str)
        if not clean or clean == "void":
            return False
        if TypeMapper.is_pointer_like_llvm(clean):
            return False
        # Unknown 32-hex hashes are treated as pointer-like/opaque.
        if _TYPE_HASH_RE.match(clean or "") and clean not in TypeMapper.LLVM_TO_PROTO:
            return False
        proto = TypeMapper.map_llvm_to_proto(clean)
        return TypeMapper.is_integral_proto_type(proto)

    @staticmethod
    def is_unsupported_vararg(function_name: str, *, context: Optional[TypeContext] = None) -> bool:
        """
        Placeholder policy: treat all vararg APIs as unsupported unless explicitly modeled.
        """
        return bool(context and function_name in context.vararg_functions)

    @staticmethod
    def infer_label(llvm_type_str: str, is_array: bool) -> str:
        """
        Infer protobuf field label (optional/required/repeated)

        Args:
            llvm_type_str: LLVM type string
            is_array: Flag from conditions.json

        Returns:
            'optional', 'required', or 'repeated'
        """
        # Arrays → optional bytes (with separate length field)
        if is_array:
            return 'optional'

        # Pointers → optional (can be null)
        if llvm_type_str.endswith('*'):
            return 'optional'

        # Primitives → optional (for fuzzing flexibility)
        return 'optional'


# TODO: Add comprehensive test cases
def test_type_mapper():
    """Unit tests for TypeMapper"""
    mapper = TypeMapper()

    # Test basic types
    assert mapper.map_llvm_to_proto('i32') == 'int32'
    assert mapper.map_llvm_to_proto('i64') == 'int64'
    assert mapper.map_llvm_to_proto('float') == 'float'
    assert mapper.map_llvm_to_proto('double') == 'double'

    # Test pointers
    assert mapper.map_llvm_to_proto('i8*') == 'bytes'
    assert mapper.map_llvm_to_proto('const char*') == 'bytes'
    assert mapper.map_llvm_to_proto('%struct.cJSON*') == 'uint32'

    # Test type hashes
    assert mapper.map_llvm_to_proto('c86ee0d9d7ed3e7b4fdbf486fa6c0ebb') == 'int32'
    assert mapper.map_llvm_to_proto('13e78f7269fb4001160f783455a4ca4d') == 'uint32'

    # Typed handle keys
    assert mapper.type_key('%struct.cJSON*') == 'struct:cJSON'
    assert mapper.type_key('i8*') == 'ptr:i8'

    # Rich classification basics
    c = mapper.classify_llvm_type('%struct.cJSON*')
    assert c.kind == 'handle'
    assert c.proto_type == 'uint32'

    ctx = TypeContext(struct_sizes={'cJSON': 256})
    c2 = mapper.classify_llvm_type('%struct.cJSON*', context=ctx)
    assert c2.kind == 'struct_blob'
    assert c2.proto_type == 'bytes'
    assert c2.struct_size == 256

    # Test handle detection
    assert mapper.is_handle_type('%struct.cJSON*') == True
    assert mapper.is_handle_type('i32') == False
    assert mapper.is_handle_type('i8*') == False

    # Test struct name extraction
    assert mapper.extract_struct_name('%struct.cJSON*') == 'cJSON'
    assert mapper.extract_struct_name('%struct.mg_mqtt_opts') == 'mg_mqtt_opts'
    assert mapper.extract_struct_name('i32') == ''

    print("✓ All TypeMapper tests passed")


if __name__ == '__main__':
    test_type_mapper()
