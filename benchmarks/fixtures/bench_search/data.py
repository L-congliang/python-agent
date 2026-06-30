"""Data models for benchmark testing."""


class User:
    """A simple user model."""

    def __init__(self, name: str, email: str, age: int) -> None:
        self.name = name
        self.email = email
        self.age = age

    def is_adult(self) -> bool:
        """Check if user is 18 or older."""
        return self.age >= 18

    def to_dict(self) -> dict[str, str | int]:
        """Convert user to dictionary."""
        return {"name": self.name, "email": self.email, "age": self.age}


class Product:
    """A simple product model."""

    def __init__(self, name: str, price: float, stock: int) -> None:
        self.name = name
        self.price = price
        self.stock = stock

    def is_available(self) -> bool:
        """Check if product is in stock."""
        return self.stock > 0

    def apply_discount(self, percent: float) -> None:
        """Apply a discount to the product price."""
        self.price *= (1 - percent / 100)
