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
