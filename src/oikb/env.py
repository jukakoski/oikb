"""Centralized environment variable resolution for oikb.

Mirrors the open-terminal env.py pattern with Docker-secrets _FILE support.
"""

import os


def _resolve_file_env(var: str, default: str = "") -> str:
    """Resolve an environment variable with Docker-secrets ``_FILE`` support.

    If ``<var>_FILE`` is set, its value is treated as a path whose contents
    supply the variable's value (trailing whitespace is stripped).  Setting
    *both* ``<var>`` and ``<var>_FILE`` is an error.
    """
    value = os.environ.get(var)
    file_path = os.environ.get(f"{var}_FILE")

    if value is not None and file_path is not None:
        raise ValueError(
            f"Both {var} and {var}_FILE are set, but they are mutually exclusive."
        )

    if file_path:
        with open(file_path) as f:
            return f.read().strip()

    return value if value is not None else default


API_KEY = _resolve_file_env("OIKB_API_KEY")
