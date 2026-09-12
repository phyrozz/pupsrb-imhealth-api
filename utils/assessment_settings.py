"""Validation for values read from the generic application settings table."""


def get_positive_integer(value) -> int | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value.isdecimal():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None
