"""S2 option-free regular bond analytics. REQ-BOND-01/02/05, D04/D13."""
from __future__ import annotations

import math
from .result import CalculationResult, Status
from .validation import InputError, UnsupportedInput, UndefinedResult, parse_number, parse_positive_integer, parse_currency
from .core import bond_ytm


def _periods(years: object, frequency: object, mode: str) -> tuple[int, int]:
    f = parse_positive_integer(frequency, "Coupon frequency")
    y = parse_number(years, "Years to maturity")
    if y <= 0:
        raise InputError("Years to maturity must be positive.")
    product = y * f
    if not math.isfinite(product) or abs(product - round(product)) > 1e-10:
        raise UnsupportedInput("Only whole regular coupon periods at a coupon date are supported.")
    n = int(round(product))
    if mode not in {"Standard", "Advanced"}:
        raise InputError("Mode must be Standard or Advanced.")
    if n > (1000 if mode == "Standard" else 10000):
        raise UnsupportedInput("Schedule exceeds the selected mode's row limit.")
    return n, f


def _schedule(face: float, coupon_rate: float, redemption: float, n: int, frequency: int) -> list[dict]:
    coupon = face * coupon_rate / frequency
    return [{"period": t, "years": t / frequency, "coupon": coupon,
             "redemption": redemption if t == n else 0.0,
             "cash_flow": coupon + (redemption if t == n else 0.0)} for t in range(1, n + 1)]


def _price(schedule: list[dict], annual_yield: float, frequency: int) -> tuple[float, list[float]]:
    q = annual_yield / frequency
    if 1 + q <= 0:
        raise InputError("Periodic yield must exceed -100%.")
    logbase = math.log1p(q)
    present = [row["cash_flow"] * math.exp(-row["period"] * logbase) for row in schedule]
    if not all(math.isfinite(x) for x in present):
        raise UnsupportedInput("Discounted cash flow exceeds numeric range.")
    total = math.fsum(present)
    if total <= 0 or not math.isfinite(total):
        raise UnsupportedInput("Bond price is outside supported numeric range.")
    return total, present


def analyze_regular_bond(*, face: object, coupon_rate: object, years: object, frequency: object,
                         annual_yield: object = None, observed_price: object = None,
                         redemption: object = None, scenario_yields: object = (),
                         bump: object = 0.0001, mode: str = "Standard", currency: object = None) -> CalculationResult:
    """Price or invert one observed full coupon-date quote, then compute risk."""
    try:
        currency_code = parse_currency(currency)
        n, f = _periods(years, frequency, mode)
        F = parse_number(face, "Face")
        c = parse_number(coupon_rate, "Annual coupon rate")
        K = F if redemption is None else parse_number(redemption, "Redemption")
        if F <= 0 or c < 0 or K <= 0:
            raise InputError("Face and redemption must be positive; coupon rate cannot be negative.")
        has_yield = annual_yield is not None and not (isinstance(annual_yield, str) and not annual_yield.strip())
        has_price = observed_price is not None and not (isinstance(observed_price, str) and not observed_price.strip())
        if has_yield == has_price:
            raise InputError("Enter exactly one of nominal annual yield or observed full price.")
        rows = _schedule(F, c, K, n, f)
        if has_price:
            price_input = parse_number(observed_price, "Observed full price")
            if price_input <= 0:
                raise InputError("Observed full price must be positive.")
            if K != F:
                # The S1 helper assumes par redemption; avoid a false inverse.
                annual = _ytm_for_schedule(rows, price_input, f)
            else:
                annual = bond_ytm(F, c, price_input, n / f, f)
        else:
            annual = parse_number(annual_yield, "Nominal annual yield")
            price_input = None
        theoretical, present = _price(rows, annual, f)
        if price_input is not None and abs(theoretical - price_input) > 1e-8 + 1e-10 * abs(price_input):
            raise UndefinedResult("YTM did not reprice the observed full price.")
        for row, pv in zip(rows, present):
            row["present_value"] = pv
        q = annual / f
        macaulay = math.fsum(row["years"] * pv for row, pv in zip(rows, present)) / theoretical
        modified = macaulay / (1 + q)
        convexity = math.fsum(row["cash_flow"] * row["period"] * (row["period"] + 1) *
                              math.exp(-(row["period"] + 2) * math.log1p(q)) / (f * f)
                              for row in rows) / theoretical
        shock = parse_number(bump, "Yield bump")
        if shock <= 0 or annual / f - shock / f <= -1:
            raise InputError("Yield bump must be positive and keep the lower periodic yield above -100%.")
        down, _ = _price(rows, annual - shock, f)
        up, _ = _price(rows, annual + shock, f)
        effective_duration = (down - up) / (2 * theoretical * shock)
        effective_convexity = (down + up - 2 * theoretical) / (theoretical * shock * shock)
        scenarios = []
        for index, raw in enumerate(scenario_yields or ()):
            if isinstance(raw, dict):
                label = str(raw.get("label", f"Scenario {index + 1}"))
                yield_value = parse_number(raw.get("yield"), f"Scenario {index + 1} yield")
            else:
                label = f"Scenario {index + 1}"
                yield_value = parse_number(raw, f"Scenario {index + 1} yield")
            scenario_price, _ = _price(rows, yield_value, f)
            scenarios.append({"label": label, "nominal_annual_yield": yield_value,
                              "periodic_yield": yield_value / f, "full_theoretical_price": scenario_price,
                              "price_change": scenario_price - theoretical,
                              "percentage_change": scenario_price / theoretical - 1,
                              "duration_convexity_approximation": -modified * (yield_value - annual) +
                                  .5 * convexity * (yield_value - annual) ** 2})
        result = {
            "full_theoretical_price": theoretical, "observed_full_price": price_input,
            "nominal_annual_yield": annual, "coupon_per_period": F * c / f,
            "redemption": K, "classification": "par" if abs(theoretical - F) <= 1e-8 else
                "premium" if theoretical > F else "discount",
            "macaulay_duration_years": macaulay, "modified_duration_years": modified,
            "convexity_years_squared": convexity, "effective_duration_years": effective_duration,
            "effective_convexity_years_squared": effective_convexity,
            "price_if_yield_down": down, "price_if_yield_up": up,
        }
        return CalculationResult(Status.VALID, annual if has_price else theoretical,
            "decimal nominal annual yield" if has_price else f"{currency_code} per stated face",
            assumptions={"currency": currency_code, "quote": "full price at coupon date; no accrual", "yield_basis": "nominal annual compounded at coupon frequency",
                         "cash_flows": "fixed, option-free", "bump": shock},
            diagnostics={"bond": result, "schedule": rows, "scenarios": scenarios})
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        status = Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.UNDEFINED if isinstance(exc, UndefinedResult) else Status.INVALID
        return CalculationResult(status, None, "bond analysis", message=str(exc))


def _ytm_for_schedule(rows: list[dict], price: float, frequency: int) -> float:
    def difference(y: float) -> float:
        return _price(rows, y, frequency)[0] - price
    lo, hi = -0.5 * frequency, frequency * 0.5
    for _ in range(100):
        if difference(lo) >= 0:
            break
        lo = (lo - frequency) / 2
    else:
        raise UnsupportedInput("Yield is too close to the lower domain boundary.")
    for _ in range(100):
        if difference(hi) <= 0:
            break
        hi = hi * 2 + frequency
    else:
        raise UnsupportedInput("Yield exceeds supported numeric range.")
    for _ in range(200):
        mid = (lo + hi) / 2
        error = difference(mid)
        if abs(error) <= 1e-8 + 1e-10 * price:
            return mid
        if error > 0:
            lo = mid
        else:
            hi = mid
        if (lo + hi) / 2 == lo or (lo + hi) / 2 == hi:
            break
    raise UndefinedResult("Yield solver did not meet its price residual.")


def solve_simple_bond(*, bond_type: str, target: str, face: object = None,
                      coupon_rate: object = None, annual_yield: object = None,
                      years: object = None, frequency: object = 1,
                      price: object = None, mode: str = "Standard") -> CalculationResult:
    """Solve one regular coupon-date bond unknown with par redemption.

    Rates are decimal nominal annual rates. Zero-coupon quotes compound annually.
    The existing schedule, price and YTM helpers remain the calculation authority.
    """
    unit = ("decimal nominal annual yield" if target == "yield" else
            "decimal nominal annual coupon rate" if target == "coupon" else
            "years" if target == "years" else "currency units")
    try:
        if bond_type not in {"fixed", "zero"}:
            raise InputError("Choose a fixed-rate or zero-coupon bond.")
        choices = {"price", "face", "yield", "years"}
        if bond_type == "fixed":
            choices.add("coupon")
        if target not in choices:
            raise InputError("Choose a supported bond value to solve.")
        f = 1 if bond_type == "zero" else parse_positive_integer(frequency, "Coupon frequency")
        if mode not in {"Standard", "Advanced"}:
            raise InputError("Choose Standard or Advanced execution profile.")
        F = None if target == "face" else parse_number(face, "Face value")
        c = 0.0 if bond_type == "zero" else (
            None if target == "coupon" else parse_number(coupon_rate, "Coupon rate"))
        Y = None if target == "yield" else parse_number(annual_yield, "Yield to maturity")
        P = None if target == "price" else parse_number(price, "Bond price")
        if F is not None and F <= 0:
            raise InputError("Face value must be positive.")
        if c is not None and c < 0:
            raise InputError("Coupon rate cannot be negative.")
        if P is not None and P <= 0:
            raise InputError("Bond price must be positive.")
        if Y is not None and Y / f <= -1:
            raise InputError("Periodic yield must exceed -100%.")
        if target == "years":
            q = Y / f
            coupon = F * c / f
            if q == 0:
                if coupon == 0:
                    raise UndefinedResult("Price is independent of maturity; years are not unique.")
                count = (P - F) / coupon
            else:
                perpetuity = coupon / q
                if math.isclose(F, perpetuity, rel_tol=1e-12, abs_tol=0.0):
                    if math.isclose(P, F, rel_tol=1e-10):
                        raise UndefinedResult("Price equals face at every maturity; years are not unique.")
                    raise UndefinedResult("No maturity matches the stated bond price.")
                ratio = (P - perpetuity) / (F - perpetuity)
                if ratio <= 0:
                    raise UndefinedResult("No positive maturity matches the stated bond price.")
                count = -math.log(ratio) / math.log1p(q)
            if not math.isfinite(count) or count <= 0:
                raise UndefinedResult("No positive maturity matches the stated bond price.")
            if abs(count - round(count)) > 1e-8:
                raise UnsupportedInput("Maturity does not contain a whole number of coupon periods.")
            n = int(round(count))
            _periods(n / f, f, mode)
            years_value = n / f
        else:
            n, f = _periods(years, f, mode)
            years_value = n / f
        if target == "yield":
            Y = bond_ytm(F, c, P, years_value, f)
        elif target == "face":
            unit_price = _price(_schedule(1.0, c, 1.0, n, f), Y, f)[0]
            F = P / unit_price
            if not math.isfinite(F) or F <= 0:
                raise UnsupportedInput("Solved face value is outside the supported numeric range.")
        elif target == "coupon":
            q = Y / f
            base = math.log1p(q)
            principal_factor = math.exp(-n * base)
            annuity = math.fsum(math.exp(-t * base) for t in range(1, n + 1))
            c = f * (P / F - principal_factor) / annuity
            if not math.isfinite(c) or c < -1e-12:
                raise UndefinedResult("No nonnegative coupon rate matches the stated price.")
            c = max(0.0, c)
        rows = _schedule(F, c, F, n, f)
        theoretical, present = _price(rows, Y, f)
        if P is not None and abs(theoretical - P) > 1e-8 + 1e-10 * abs(P):
            raise UndefinedResult("Solved bond value does not reprice the stated bond price.")
        for row, value in zip(rows, present):
            row["present_value"] = value
        solved = {"price": theoretical, "face": F, "coupon": c,
                  "yield": Y, "years": years_value}[target]
        return CalculationResult(Status.VALID, solved, unit,
            assumptions={"redemption": "100% of face at maturity", "quote": "full price at a coupon date; no accrued interest",
                         "yield_basis": "nominal annual, compounded at coupon frequency",
                         "frequency": f},
            diagnostics={"schedule": rows, "coupon_per_period": F * c / f,
                         "solved_face": F, "solved_coupon_rate": c,
                         "solved_nominal_yield": Y, "solved_years": years_value,
                         "theoretical_price": theoretical,
                         "formula": "P = sum[(F*c/f)/(1+Y/f)^t] + F/(1+Y/f)^N",
                         "interpretation": "The stated full price is the present value of regular coupons and face redemption."})
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        status = Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else (
            Status.UNDEFINED if isinstance(exc, UndefinedResult) else Status.INVALID)
        return CalculationResult(status, None, unit, message=str(exc))
