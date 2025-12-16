"""
Shared constants and contract definitions for proto-liberator.
This file defines the interface between the schema generator (Branch A)
and the harness generator (Branch B).
"""

# Top-level message name
MSG_FUZZ_INPUT = "FuzzInput"
MSG_ACTION = "Action"

# Common field suffixes
SUFFIX_LENGTH = "_length"
SUFFIX_IS_NULL = "_is_null"
SUFFIX_HANDLE = "_handle"
SUFFIX_LENGTH_OVERRIDE = "_length_override"
SUFFIX_MALLOC_OVERRIDE = "_malloc_override"

# Special field names
FIELD_GLOBAL_SEED = "global_seed"
FIELD_ACTIONS = "actions"
FIELD_ACTION_ONEOF = "action"

# v2 defaults
DEFAULT_MAX_ACTIONS = 64
