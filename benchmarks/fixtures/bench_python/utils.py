"""Utility functions for benchmark testing."""


def find_max(numbers: list[int]) -> int:
    """Return the maximum number in a list.

    Raises:
        ValueError: If the list is empty.
    """
    if not numbers:
        raise ValueError("Cannot find max of empty list")
    return max(numbers)


def find_min(numbers: list[int]) -> int:
    """Return the minimum number in a list.

    Raises:
        ValueError: If the list is empty.
    """
    if not numbers:
        raise ValueError("Cannot find min of empty list")
    return min(numbers)


def average(numbers: list[float]) -> float:
    """Return the average of a list of numbers.

    Raises:
        ValueError: If the list is empty.
    """
    if not numbers:
        raise ValueError("Cannot average empty list")
    return sum(numbers) / len(numbers)
