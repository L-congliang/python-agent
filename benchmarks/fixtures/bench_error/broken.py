"""Module with intentional errors for error-recovery benchmarks."""


def parse_config(text: str) -> dict[str, str]:
    """Parse a simple config file.

    This function has an intentional bug: it doesn't handle empty lines.
    """
    config = {}
    for line in text.split("\n"):
        key, value = line.split("=")  # Bug: crashes on empty lines
        config[key.strip()] = value.strip()
    return config


def calculate_discount(price: float, discount: float) -> float:
    """Calculate discounted price.

    This function has an intentional bug: negative discount increases price.
    """
    return price * (1 - discount / 100)


def merge_lists(list_a: list[str], list_b: list[str]) -> list[str]:
    """Merge two lists without duplicates.

    This function has an intentional bug: order is not preserved.
    """
    return list(set(list_a + set(list_b)))  # Bug: set() loses order
