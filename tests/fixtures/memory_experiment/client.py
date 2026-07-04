"""Client module that depends on service."""

from service import validate_input, process_request


def send_request(payload: dict) -> dict:
    """Send a request through the service."""
    return process_request(payload)


def batch_send(items: list[dict]) -> list[dict]:
    """Send multiple requests."""
    results = []
    for item in items:
        if validate_input(item):
            results.append(process_request(item))
    return results
