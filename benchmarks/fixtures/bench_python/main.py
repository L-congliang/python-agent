"""Simple module for benchmark testing."""


def add(a: int, b: int) -> int:
    """Return the sum of two numbers."""
    return a + b


def multiply(a: int, b: int) -> int:
    """Return the product of two numbers."""
    return a * b


def subtract(a: int, b: int) -> int:
    """Return the difference of two numbers."""
    return a - b


def divide(a: float, b: float) -> float:
    """Return the division of two numbers.

    Raises:
        ZeroDivisionError: If b is zero.
    """
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b
