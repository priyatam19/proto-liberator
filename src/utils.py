#!/usr/bin/env python3
"""
Utility functions for Proto-libErator
"""

import json
from pathlib import Path
from typing import Any, Dict, List


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


def save_file(file_path: Path, content: str):
    """
    Save content to file

    Args:
        file_path: Output file path
        content: Content to write
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        f.write(content)


def load_text_lines(file_path: Path) -> List[str]:
    """
    Load text file as list of lines

    Args:
        file_path: Path to text file

    Returns:
        List of lines (stripped)
    """
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def format_c_comment(text: str, indent: int = 0) -> str:
    """
    Format text as C-style comment

    Args:
        text: Comment text
        indent: Indentation level

    Returns:
        Formatted comment string
    """
    ind = "  " * indent
    lines = text.split('\n')
    if len(lines) == 1:
        return f"{ind}// {text}"
    else:
        result = [f"{ind}/*"]
        for line in lines:
            result.append(f"{ind} * {line}")
        result.append(f"{ind} */")
        return "\n".join(result)


def sanitize_identifier(name: str) -> str:
    """
    Sanitize name for use as C/protobuf identifier

    Args:
        name: Original name

    Returns:
        Sanitized identifier
    """
    # Replace invalid characters with underscore
    sanitized = ""
    for char in name:
        if char.isalnum() or char == '_':
            sanitized += char
        else:
            sanitized += '_'

    # Ensure doesn't start with digit
    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized

    return sanitized


def to_snake_case(name: str) -> str:
    """
    Convert a name to snake_case.

    Examples:
      - "cJSON_AddItemToArray" -> "cjson_add_item_to_array"
      - "FooBar" -> "foo_bar"
    """
    if not name:
        return ""

    import re

    # Insert underscores before capitals, handling acronym boundaries reasonably well.
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    # Replace non-identifier characters with underscores and normalize.
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", s)
    s = s.strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.lower()


def to_proto_field_name(name: str) -> str:
    """
    Convert an arbitrary name into a protobuf field name:
    - snake_case
    - sanitized
    - does not start with a digit
    """
    snake = to_snake_case(name)
    sanitized = sanitize_identifier(snake).lower()
    if sanitized and sanitized[0].isdigit():
        sanitized = "_" + sanitized
    return sanitized


def unique_proto_field_names(names: List[str]) -> Dict[str, str]:
    """Return stable, unique protobuf field names for API function names."""
    result: Dict[str, str] = {}
    used = set()
    for name in sorted(set(names)):
        base = to_proto_field_name(name)
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        result[name] = candidate
        used.add(candidate)
    return result


def humanize_bytes(size_bytes: int) -> str:
    """
    Convert byte count to human-readable string

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable string (e.g., "1.5 KB", "2.3 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


# TODO: Add more utility functions as needed
# - File hash computation
# - Template rendering helpers
# - Logging configuration
# - Progress bar utilities
