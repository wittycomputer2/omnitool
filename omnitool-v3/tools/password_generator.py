"""Cryptographically secure password generation."""

import secrets
import string


LOWERCASE = string.ascii_lowercase
UPPERCASE = string.ascii_uppercase
NUMBERS = string.digits
SYMBOLS = '!"#$%&/()=?¡*¨][_><|@·~½¬{[]}\\.'


def generate(length: int) -> str:
    """Generate a password containing every requested character category."""
    if length < 4:
        raise ValueError("Password length must be at least 4 characters.")
    if length > 4096:
        raise ValueError("Password length must not exceed 4096 characters.")

    categories = (LOWERCASE, UPPERCASE, NUMBERS, SYMBOLS)
    password = [secrets.choice(category) for category in categories]
    alphabet = "".join(categories)
    password.extend(secrets.choice(alphabet) for _ in range(length - len(password)))
    secrets.SystemRandom().shuffle(password)
    return "".join(password)
