"""Framework-free S1 arithmetic using the legacy positive-asset FV identity.

FV = PV(1+r)^n + PMT * sum((1+r)^k, k=0..n-1). This preserves
legacy behavior while final user-facing sign policy remains D01.
"""

import math
from decimal import Decimal, localcontext

from .roots import positive_roots_with_multiplicity
from .validation import InputError, UndefinedResult, UnsupportedInput, parse_number, regular_period_count


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise InputError("Calculation is not finite.")
    return value


def _growth(rate: float, count: int) -> tuple[float, float]:
    if rate <= -1 or count < 0:
        raise InputError("Rate must exceed -100% and periods cannot be negative.")
    try:
        log_growth = count * math.log1p(rate)
        growth = math.exp(log_growth)
        annuity = math.expm1(log_growth) / rate if rate else float(count)
    except OverflowError as exc:
        raise InputError("Inputs exceed the numeric range.") from exc
    return _finite(growth), _finite(annuity)


def future_value(pv: float, rate: float, count: int, pmt: float = 0.0) -> float:
    pv, rate, pmt = (parse_number(v, n) for v, n in ((pv, "PV"), (rate, "Periodic rate"), (pmt, "PMT")))
    growth, annuity = _growth(rate, count)
    return _finite(pv * growth + pmt * annuity)


def present_value(fv: float, rate: float, count: int, pmt: float = 0.0) -> float:
    fv, rate, pmt = (parse_number(v, n) for v, n in ((fv, "FV"), (rate, "Periodic rate"), (pmt, "PMT")))
    growth, annuity = _growth(rate, count)
    if growth == 0:
        raise UndefinedResult("PV is numerically unidentifiable at this horizon and rate.")
    return _finite((fv - pmt * annuity) / growth)


def required_payment(pv: float, fv: float, rate: float, count: int) -> float:
    pv, fv, rate = (parse_number(v, n) for v, n in ((pv, "PV"), (fv, "FV"), (rate, "Periodic rate")))
    if count <= 0:
        raise InputError("At least one payment period is required.")
    growth, annuity = _growth(rate, count)
    if annuity == 0:
        raise UndefinedResult("Payment cannot be identified from these inputs.")
    return _finite((fv - pv * growth) / annuity)


def periods(pv: float, fv: float, rate: float, pmt: float = 0.0) -> float:
    pv, fv, rate, pmt = (parse_number(v, n) for v, n in ((pv, "PV"), (fv, "FV"), (rate, "Periodic rate"), (pmt, "PMT")))
    if rate <= -1:
        raise InputError("Periodic rate must exceed -100%.")
    if rate == 0:
        if pmt == 0:
            raise UndefinedResult("Periods are not identifiable when both rate and payment are zero.")
        count = (fv - pv) / pmt
    else:
        base = pv + pmt / rate
        terminal = fv + pmt / rate
        if base == 0 or terminal / base <= 0:
            raise UndefinedResult("No real period count satisfies these inputs.")
        count = math.log(terminal / base) / math.log1p(rate)
    if not math.isfinite(count) or count < 0:
        raise UndefinedResult("No nonnegative period count satisfies these inputs.")
    return count


def npv(rate: float, cash_flows: list[float] | tuple[float, ...]) -> float:
    rate = parse_number(rate, "Periodic discount rate")
    if rate <= -1:
        raise InputError("Periodic discount rate must exceed -100%.")
    flows = [parse_number(value, f"Cash flow {i}") for i, value in enumerate(cash_flows)]
    if not flows:
        raise InputError("At least one cash flow is required.")
    return _finite(math.fsum(cf / (1 + rate) ** i for i, cf in enumerate(flows)))


def _candidate_rate_multiplicities(coefficients: list[float], *, variable_is_growth: bool) -> tuple[tuple[float, int], ...]:
    """S1 regular-flow roots with exact multiplicity and residual verification.

    Full long-horizon/root-domain policies remain S2/S3 work. A failed or
    incomplete numerical solve never becomes a success result.
    """
    while len(coefficients) > 1 and coefficients[-1] == 0:
        coefficients.pop()
    if len(coefficients) <= 1:
        raise UndefinedResult("No isolated rate root exists for these cash flows.")
    if len(coefficients) > 101:
        raise UnsupportedInput("S1 root solving supports at most 100 intervals; full policy is pending later stages.")
    if not any(coefficients):
        raise UndefinedResult("Rate is not identifiable from zero amounts.")
    rates: list[tuple[float, int]] = []
    for root, multiplicity in positive_roots_with_multiplicity(coefficients):
        rate = root - 1.0 if variable_is_growth else 1.0 / root - 1.0
        if not math.isfinite(rate) or rate <= -1:
            raise UnsupportedInput("A certified rate root is outside representable precision.")
        rates.append((rate, multiplicity))
    return tuple(sorted(rates))


def _candidate_rates(coefficients: list[float], *, variable_is_growth: bool) -> tuple[float, ...]:
    return tuple(rate for rate, _ in _candidate_rate_multiplicities(coefficients, variable_is_growth=variable_is_growth))


def irr_root_multiplicities(cash_flows: list[float] | tuple[float, ...]) -> tuple[tuple[float, int], ...]:
    flows = [parse_number(value, f"Cash flow {i}") for i, value in enumerate(cash_flows)]
    if len(flows) < 2:
        raise InputError("At least two cash flows are required for IRR.")
    if all(flow == 0 for flow in flows):
        raise UndefinedResult("All-zero flows have no unique IRR.")
    if all(flow >= 0 for flow in flows) or all(flow <= 0 for flow in flows):
        raise UndefinedResult("Same-sign cash flows have no admissible IRR.")
    roots = _candidate_rate_multiplicities(flows.copy(), variable_is_growth=False)
    for rate, _ in roots:
        if abs(npv(rate, flows)) > 1e-10 * max(abs(cf) for cf in flows) * len(flows):
            raise UnsupportedInput("Certified IRR did not pass the cash-flow residual check.")
    return roots


def irr_roots(cash_flows: list[float] | tuple[float, ...]) -> tuple[float, ...]:
    return tuple(rate for rate, _ in irr_root_multiplicities(cash_flows))


def rate_roots(pv: float, fv: float, count: int, pmt: float = 0.0) -> tuple[float, ...]:
    pv, fv, pmt = (parse_number(v, n) for v, n in ((pv, "PV"), (fv, "FV"), (pmt, "PMT")))
    if count <= 0:
        raise InputError("At least one period is required.")
    coefficients = [pmt - fv] + [pmt] * (count - 1) + [pv]
    roots = _candidate_rates(coefficients, variable_is_growth=True)
    return tuple(rate for rate in roots if abs(future_value(pv, rate, count, pmt) - fv) <= 1e-8 * max(1.0, abs(pv), abs(fv), abs(pmt)))


def bond_price(face: float, coupon_rate: float, yield_rate: float, years: float, frequency: int) -> float:
    face, coupon_rate, yield_rate = (parse_number(v, n) for v, n in ((face, "Face"), (coupon_rate, "Annual coupon rate"), (yield_rate, "Annual yield")))
    count = regular_period_count(years, frequency)
    if face <= 0 or coupon_rate < 0:
        raise InputError("Face must be positive and coupon rate nonnegative.")
    periodic = yield_rate / frequency
    if periodic <= -1:
        raise InputError("Periodic yield must exceed -100%.")
    if 1 + periodic < 1e-4:
        # Binary64 loses relative digits in 1+q as q approaches -1. Exact
        # decimal input reconstruction protects the contractual money sum.
        with localcontext() as context:
            context.prec = 50
            decimal_face = Decimal(str(face))
            decimal_coupon = decimal_face * Decimal(str(coupon_rate)) / Decimal(frequency)
            base = 1 + Decimal(str(yield_rate)) / Decimal(frequency)
            if base <= 0:
                raise InputError("Periodic yield must exceed -100%.")
            decimal_price = sum(decimal_coupon / base ** t for t in range(1, count + 1)) + decimal_face / base ** count
            return _finite(float(decimal_price))
    coupon = face * coupon_rate / frequency
    return _finite(math.fsum(coupon / (1 + periodic) ** t for t in range(1, count + 1)) + face / (1 + periodic) ** count)


def bond_ytm(face: float, coupon_rate: float, price: float, years: float, frequency: int) -> float:
    face = parse_number(face, "Face")
    coupon_rate = parse_number(coupon_rate, "Annual coupon rate")
    price = parse_number(price, "Price")
    count = regular_period_count(years, frequency)
    if face <= 0 or coupon_rate < 0 or price <= 0:
        raise InputError("Face and price must be positive; coupon rate nonnegative.")

    def repriced(periodic: float) -> float:
        return bond_price(face, coupon_rate, periodic * frequency, years, frequency)

    tolerance = 1e-10 * max(1.0, price)
    if coupon_rate == 0:
        # P = F/(1+q)^N; the direct inverse covers valid q very close to -1.
        periodic = face / price - 1.0 if count == 1 else math.expm1((math.log(face) - math.log(price)) / count)
        if periodic <= -1 or not math.isfinite(periodic):
            raise UnsupportedInput("Zero-coupon yield is outside representable precision.")
        if abs(repriced(periodic) - price) > tolerance:
            raise UndefinedResult("Zero-coupon YTM failed its price residual check.")
        return periodic * frequency

    at_zero = repriced(0.0)
    if abs(at_zero - price) <= tolerance:
        return 0.0
    if price > at_zero:
        high = 0.0
        low = -0.5
        while repriced(low) < price:
            next_low = (low - 1.0) / 2.0
            if next_low == low or next_low <= -1:
                raise UnsupportedInput("YTM is too close to -100% for representable precision.")
            low = next_low
    else:
        low = 0.0
        high = 1.0
        while repriced(high) > price:
            next_high = high * 2.0
            if not math.isfinite(next_high):
                raise UnsupportedInput("YTM exceeds representable precision.")
            high = next_high

    if repriced(low) < price or repriced(high) > price:
        raise UndefinedResult("YTM search did not bracket the input price.")
    for _ in range(200):
        mid = (low + high) / 2
        if mid == low or mid == high:
            break
        difference = repriced(mid) - price
        if abs(difference) <= tolerance:
            return mid * frequency
        if difference > 0:
            low = mid
        else:
            high = mid
    for endpoint in (low, high):
        if abs(repriced(endpoint) - price) <= tolerance:
            return endpoint * frequency
    raise UndefinedResult("YTM solver did not meet its price residual.")
