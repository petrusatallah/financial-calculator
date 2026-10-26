"""Shared boundary parsing. Blank, malformed, and numeric zero are distinct."""

import math


class InputError(ValueError):
    pass


class UnsupportedInput(InputError):
    pass


class UndefinedResult(InputError):
    pass


def parse_number(value: object, label: str) -> float:
    if value is None or isinstance(value, str) and not value.strip():
        raise InputError(f"{label} is required; enter zero explicitly if intended.")
    if isinstance(value, bool):
        raise InputError(f"{label} must be a number.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InputError(f"{label} must be a valid number.") from exc
    if not math.isfinite(result):
        raise InputError(f"{label} must be finite.")
    return result


def parse_optional_number(value: object, label: str) -> float | None:
    if value is None or isinstance(value, str) and not value.strip():
        return None
    return parse_number(value, label)


def parse_positive_integer(value: object, label: str) -> int:
    number = parse_number(value, label)
    if number <= 0 or not number.is_integer():
        raise InputError(f"{label} must be a positive whole number.")
    return int(number)


def regular_period_count(years: object, frequency: object) -> int:
    y = parse_number(years, "Years")
    f = parse_positive_integer(frequency, "Frequency")
    count = y * f
    if y <= 0:
        raise InputError("Years must be positive.")
    if not math.isfinite(count) or abs(count - round(count)) > 1e-10:
        raise UnsupportedInput("Regular payment/coupon schedules require a whole number of periods.")
    return int(round(count))


def parse_currency(value: object) -> str:
    """Require an explicit three-letter currency identifier for S2 money."""
    import re
    if not isinstance(value, str):
        raise InputError("Currency is required as a three-letter code.")
    code = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise InputError("Currency must be a three-letter code such as USD or EUR.")
    return code
