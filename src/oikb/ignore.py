"""Gitignore-style pattern matching for .oikbignore files."""

from __future__ import annotations

import fnmatch
from pathlib import Path


def load_ignore_patterns(root: Path) -> list[str]:
    """Load patterns from .oikbignore file in the given directory.

    Supports gitignore-style patterns:
      - Blank lines and lines starting with # are ignored
      - Standard glob patterns (*, ?, [])
      - Leading / anchors to the root
      - Trailing / matches directories only
      - ! negates a pattern (not yet supported)
    """
    ignore_file = root / ".oikbignore"
    if not ignore_file.exists():
        return []

    patterns: list[str] = []
    with open(ignore_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)

    return patterns


def should_ignore(
    relative_path: str,
    name: str,
    is_dir: bool,
    patterns: list[str],
) -> bool:
    """Check if a file or directory should be ignored based on .oikbignore patterns.

    Args:
        relative_path: Path relative to root (e.g. "docs/api/readme.md").
        name:          Basename (e.g. "readme.md").
        is_dir:        Whether the entry is a directory.
        patterns:      List of gitignore-style patterns.
    """
    for pattern in patterns:
        # Directory-only patterns (trailing /).
        dir_only = pattern.endswith("/")
        if dir_only:
            if not is_dir:
                continue
            pattern = pattern.rstrip("/")

        # Match against both the basename and the full relative path.
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(relative_path, pattern):
            return True

    return False
