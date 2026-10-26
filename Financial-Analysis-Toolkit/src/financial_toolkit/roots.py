"""Certified distinct positive roots of decimal-coefficient polynomials.

Exact rational square-free decomposition determines multiplicity. Sturm's
theorem counts and isolates the distinct real roots before floating conversion.
This avoids interpreting companion-matrix splits of repeated roots as IRRs.
"""

from fractions import Fraction

from .validation import UnsupportedInput


Polynomial = tuple[Fraction, ...]  # ascending powers


def _trim(values: list[Fraction] | tuple[Fraction, ...]) -> Polynomial:
    result = list(values)
    while result and result[-1] == 0:
        result.pop()
    return tuple(result)


def _derivative(poly: Polynomial) -> Polynomial:
    return _trim([index * value for index, value in enumerate(poly)][1:])


def _divide(numerator: Polynomial, denominator: Polynomial) -> tuple[Polynomial, Polynomial]:
    if not denominator:
        raise ZeroDivisionError("Zero polynomial divisor.")
    remainder = list(numerator)
    quotient = [Fraction(0)] * max(0, len(numerator) - len(denominator) + 1)
    while len(remainder) >= len(denominator):
        offset = len(remainder) - len(denominator)
        coefficient = remainder[-1] / denominator[-1]
        quotient[offset] = coefficient
        for index, value in enumerate(denominator):
            remainder[offset + index] -= coefficient * value
        remainder = list(_trim(remainder))
    return _trim(quotient), _trim(remainder)


def _monic(poly: Polynomial) -> Polynomial:
    return tuple(value / poly[-1] for value in poly) if poly else ()


def _gcd(left: Polynomial, right: Polynomial) -> Polynomial:
    while right:
        _, remainder = _divide(left, right)
        left, right = right, remainder
    return _monic(left)


def _exact_quotient(left: Polynomial, right: Polynomial) -> Polynomial:
    quotient, remainder = _divide(left, right)
    if remainder:
        raise UnsupportedInput("Exact polynomial decomposition failed.")
    return quotient


def _square_free_parts(poly: Polynomial) -> tuple[tuple[Polynomial, int], ...]:
    """Yun's characteristic-zero decomposition: each factor has one multiplicity."""
    common = _gcd(poly, _derivative(poly))
    remaining = _exact_quotient(poly, common)
    multiplicity = 1
    parts: list[tuple[Polynomial, int]] = []
    while len(remaining) > 1:
        shared = _gcd(remaining, common)
        factor = _exact_quotient(remaining, shared)
        if len(factor) > 1:
            parts.append((_monic(factor), multiplicity))
        remaining = shared
        common = _exact_quotient(common, shared)
        multiplicity += 1
    return tuple(parts)


def _evaluate(poly: Polynomial, value: Fraction) -> Fraction:
    result = Fraction(0)
    for coefficient in reversed(poly):
        result = result * value + coefficient
    return result


def _sturm(poly: Polynomial) -> tuple[Polynomial, ...]:
    sequence = [poly, _derivative(poly)]
    while sequence[-1]:
        _, remainder = _divide(sequence[-2], sequence[-1])
        if not remainder:
            break
        negative = tuple(-value for value in remainder)
        # Scaling by a positive factor preserves every Sturm sign.
        scale = abs(negative[-1])
        sequence.append(tuple(value / scale for value in negative))
    return tuple(item for item in sequence if item)


def _sign_at_right(poly: Polynomial, value: Fraction) -> int:
    current = poly
    while current:
        evaluation = _evaluate(current, value)
        if evaluation:
            return 1 if evaluation > 0 else -1
        current = _derivative(current)
    return 0


def _variations(sequence: tuple[Polynomial, ...], value: Fraction) -> int:
    signs = [_sign_at_right(poly, value) for poly in sequence]
    return sum(left != right for left, right in zip(signs, signs[1:]))


def _split(left: Fraction, right: Fraction, sequence: tuple[Polynomial, ...]) -> Fraction:
    # Keep the split off roots of every Sturm member so counts add exactly.
    for denominator in range(2, 100):
        split = left + (right - left) / denominator
        if all(_evaluate(poly, split) for poly in sequence):
            return split
    raise UnsupportedInput("Could not isolate polynomial roots safely.")


def _isolated_roots(poly: Polynomial) -> tuple[Fraction, ...]:
    sequence = _sturm(poly)
    leading = abs(poly[-1])
    bound = 1 + max(abs(value) / leading for value in poly[:-1])
    start, end = Fraction(0), bound
    queue = [(start, end, _variations(sequence, start), _variations(sequence, end))]
    intervals: list[tuple[Fraction, Fraction, int, int]] = []
    while queue:
        left, right, left_count, right_count = queue.pop()
        count = left_count - right_count
        if count == 1:
            intervals.append((left, right, left_count, right_count))
        elif count > 1:
            split = _split(left, right, sequence)
            middle_count = _variations(sequence, split)
            queue.extend(((left, split, left_count, middle_count), (split, right, middle_count, right_count)))

    roots: list[Fraction] = []
    for left, right, left_count, right_count in intervals:
        for _ in range(256):
            split = (left + right) / 2
            if _evaluate(poly, split) == 0:
                left = right = split
                break
            middle_count = _variations(sequence, split)
            if left_count - middle_count:
                right, right_count = split, middle_count
            else:
                left, left_count = split, middle_count
            # Conversion to binary64 is now stable; exact isolation supplied
            # the root count and multiplicity, not a distance threshold.
            if float(left) == float(right):
                break
        else:
            raise UnsupportedInput("Polynomial root isolation did not converge.")
        roots.append((left + right) / 2)
    return tuple(sorted(roots))


def positive_roots_with_multiplicity(coefficients: list[float]) -> tuple[tuple[float, int], ...]:
    """Return positive distinct roots; fail closed on unresolved exact structure."""
    values = _trim([Fraction(str(value)) for value in coefficients])
    while values and values[0] == 0:
        values = values[1:]  # x=0 is outside either rate transformation.
    if len(values) <= 1:
        return ()
    parts = _square_free_parts(_monic(values))
    roots = [(float(root), multiplicity) for factor, multiplicity in parts for root in _isolated_roots(factor)]
    return tuple(sorted((root, multiplicity) for root, multiplicity in roots if root > 0))
