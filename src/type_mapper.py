#!/usr/bin/env python3
"""
Type Mapper - LLVM IR Type to Protobuf Type Mapping
Deterministic, rule-based type conversion
"""

from typing import Dict, Tuple


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
        clean_type = llvm_type_str.replace('const ', '')
        clean_type = clean_type.replace('volatile ', '')
        clean_type = clean_type.replace('restrict ', '')
        clean_type = clean_type.strip()

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
        if len(clean_type) == 32 and all(c in '0123456789abcdef' for c in clean_type):
            # Check if it's a known hash
            if clean_type in TypeMapper.LLVM_TO_PROTO:
                return TypeMapper.LLVM_TO_PROTO[clean_type]
            # Unknown hash → assume pointer/handle
            return 'uint32'

        # Default fallback
        return 'bytes'

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
