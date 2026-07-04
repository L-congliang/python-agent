"""Main application module"""


MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30


def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers."""
    return a + b


def main() -> None:
    """Entry point."""
    result = calculate_sum(1, 2)
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
