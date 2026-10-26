"""One interface-neutral adapter for both legacy UIs.

Only the calculator's existing regular-period workflows are in S1. D01,
D02, D04 and D12 still gate final V1 conventions and file contracts.
"""

import math
from decimal import Decimal

from . import core
from .result import CalculationResult, Status
from .validation import InputError, UndefinedResult, UnsupportedInput, parse_number, parse_optional_number, parse_positive_integer, regular_period_count


def _failure(exc: Exception, unit: str) -> CalculationResult:
    status = Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.UNDEFINED if isinstance(exc, UndefinedResult) else Status.INVALID
    return CalculationResult(status, None, unit, message=str(exc))


def calculate_compounding(
    target: str, *, pv: object = None, fv: object = None, annual_rate_percent: object = None,
    years: object = None, pmt: object = None, frequency: object = 1,
) -> CalculationResult:
    """Preserve legacy positive-asset FV identity pending final D01 mapping."""
    unit = "percent annual" if target == "Rate" else "years" if target == "Years" else "currency/period" if target == "PMT" else "currency"
    try:
        if target not in {"PV", "FV", "PMT", "Rate", "Years"}:
            raise InputError("Select exactly one supported unknown.")
        fields = {"PV": pv, "FV": fv, "PMT": pmt, "Rate": annual_rate_percent, "Years": years}
        if fields[target] is not None and not isinstance(fields[target], str) or isinstance(fields[target], str) and fields[target].strip():
            raise InputError(f"{target} is selected as unknown and must be blank.")
        parsed = {name: parse_optional_number(value, name) for name, value in fields.items()}
        missing = [name for name, value in parsed.items() if value is None]
        if missing != [target]:
            raise InputError("Exactly the selected unknown must be blank; enter zero explicitly elsewhere.")
        freq = parse_positive_integer(frequency, "Frequency")
        assumptions = {"cash_flow_sign": "legacy positive-asset identity; final display policy D01 pending", "rate_basis": "legacy annual percent divided by frequency; D02 pending", "payment_timing": "end of regular period"}
        if target == "Years":
            rate = parsed["Rate"] / 100 / freq
            count = core.periods(parsed["PV"], parsed["FV"], rate, parsed["PMT"])
            if parsed["PMT"] != 0 and abs(count - round(count)) > 1e-9:
                raise UnsupportedInput("Fractional regular payment periods require an approved S2 schedule convention.")
            value = count / freq
        else:
            count = regular_period_count(parsed["Years"], freq)
            if target == "Rate":
                roots = core.rate_roots(parsed["PV"], parsed["FV"], count, parsed["PMT"])
                if not roots:
                    raise UndefinedResult("No admissible rate passed the solver residual check.")
                if len(roots) != 1:
                    return CalculationResult(Status.UNDEFINED, None, unit, message=f"{len(roots)} admissible rate roots; no unique rate.", diagnostics={"periodic_roots": roots})
                value = roots[0] * freq * 100
            else:
                rate = parsed["Rate"] / 100 / freq
                if target == "FV":
                    value = core.future_value(parsed["PV"], rate, count, parsed["PMT"])
                elif target == "PV":
                    value = core.present_value(parsed["FV"], rate, count, parsed["PMT"])
                else:
                    value = core.required_payment(parsed["PV"], parsed["FV"], rate, count)
        if not math.isfinite(value):
            raise InputError("Result is not finite.")
        return CalculationResult(Status.VALID, value, unit, assumptions=assumptions)
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        return _failure(exc, unit)


def calculate_npv(rate_percent: object, cash_flows: list[object]) -> CalculationResult:
    try:
        rate = parse_number(rate_percent, "Discount rate (%)") / 100
        value = core.npv(rate, cash_flows)
        return CalculationResult(Status.VALID, value, "currency", assumptions={"first_flow": "t=0", "rate_basis": "percent per regular period"})
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        return _failure(exc, "currency")


def calculate_irr(cash_flows: list[object]) -> CalculationResult:
    try:
        root_records = core.irr_root_multiplicities(cash_flows)
        roots = tuple(rate for rate, _ in root_records)
        if not roots:
            raise UndefinedResult("No admissible IRR passed the residual check.")
        warnings: list[str] = []
        if len(roots) > 1:
            warnings.append("Multiple distinct IRRs; no single rate should be selected silently.")
        if any(multiplicity > 1 for _, multiplicity in root_records):
            warnings.append("A repeated IRR root was detected.")
        return CalculationResult(Status.VALID, roots, "decimal rate per regular period", warnings=tuple(warnings), assumptions={"first_flow": "t=0", "admissible_domain": "rate > -100%"})
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        return _failure(exc, "decimal rate per regular period")


def calculate_bond(*, face: object, coupon_percent: object, years: object, frequency: object, yield_percent: object = None, price: object = None) -> CalculationResult:
    target = "price" if price is None or isinstance(price, str) and not price.strip() else "yield"
    unit = "currency per stated face" if target == "price" else "percent nominal annual"
    try:
        f = parse_number(face, "Face")
        c = float(Decimal(str(parse_number(coupon_percent, "Coupon rate (%)"))) / Decimal(100))
        y = parse_optional_number(yield_percent, "YTM (%)")
        p = parse_optional_number(price, "Bond price")
        yr = parse_number(years, "Years")
        freq = parse_positive_integer(frequency, "Frequency")
        if (y is None) == (p is None):
            raise InputError("Enter exactly one of yield or price; leave the other blank.")
        assumptions = {"quote": "legacy coupon-date full theoretical price; final D04 quote policy pending", "yield_basis": "nominal annual percent compounded at coupon frequency"}
        if p is None:
            yield_fraction = float(Decimal(str(y)) / Decimal(100))
            value = core.bond_price(f, c, yield_fraction, yr, freq)
        else:
            annual_yield = core.bond_ytm(f, c, p, yr, freq)
            value = float(Decimal(str(annual_yield)) * Decimal(100))
        return CalculationResult(Status.VALID, value, unit, assumptions=assumptions)
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        return _failure(exc, unit)
