"""Utility functions"""

import os


def get_env(key: str, default: str = "") -> str:
    """Get environment variable."""
    return os.environ.get(key, default)


def format_output(text: str) -> str:
    """Format output text."""
    return f">>> {text}"
