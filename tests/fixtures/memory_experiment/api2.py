"""API client module."""

import os
from config2 import API_KEY, MAX_ITEMS


DEFAULT_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def call_api(endpoint: str, data: dict) -> dict:
    """Call the API endpoint."""
    return {"status": "ok", "endpoint": endpoint, "data": data}
