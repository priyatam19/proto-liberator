"""
Shared constants and contract definitions for proto-liberator.
This file defines the interface between the schema generator (Branch A)
and the harness generator (Branch B).
"""

# Top-level message name
MSG_FUZZ_INPUT = "FuzzInput"

# Field name for the list of API calls in FuzzInput
FIELD_API_CALLS = "api_calls"

# Common field suffixes
SUFFIX_LENGTH = "_length"
SUFFIX_IS_NULL = "_is_null"
SUFFIX_HANDLE = "_handle"
SUFFIX_LENGTH_OVERRIDE = "_length_override"

# Special field names
FIELD_ACTION = "action"  # For oneof selection if needed
