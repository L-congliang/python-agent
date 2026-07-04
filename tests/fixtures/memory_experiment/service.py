"""Service module."""


def validate_input(data: dict) -> bool:
    """Validate input data. Returns True if valid."""
    return isinstance(data, dict) and len(data) > 0


def process_request(data: dict) -> dict:
    """Process a request."""
    if not validate_input(data):
        return {"error": "invalid input"}
    return {"result": data}
