"""S2 time-value-of-money engine. REQ-TVM-01..04; D01..D03/D13.

Cash flows are signed from the user's perspective. PV occurs at t=0, each
payment at its displayed time, and FV is the terminal balancing cash flow.
"""
from __future__ import annotations

import math
import time
from datetime import date
from decimal import Decimal

from .result import CalculationResult, Status
from .validation import InputError, UndefinedResult, UnsupportedInput, parse_number, parse_positive_integer, parse_currency
from .roots import positive_roots_with_multiplicity


def _profile(mode: str, rows: int) -> None:
    if mode not in {"Standard", "Advanced"}:
        raise InputError("Mode must be Standard or Advanced.")
    limit = 1000 if mode == "Standard" else 10000
    if rows > limit:
        raise UnsupportedInput(f"{mode} mode supports at most {limit} schedule rows.")


def _date(value: object, label: str) -> date:
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise InputError(f"{label} must be an ISO date (YYYY-MM-DD).") from exc


def periodic_rate(annual_rate: float, payment_frequency: int, compounding_frequency: int, mode: str) -> tuple[float, float]:
    """Convert a nominal annual decimal quote through EAR (D02)."""
    j = parse_number(annual_rate, "Nominal annual rate")
    p = parse_positive_integer(payment_frequency, "Payment frequency")
    m = parse_positive_integer(compounding_frequency, "Compounding frequency")
    if mode == "Standard" and p != m:
        raise UnsupportedInput("Standard mode requires matching payment and compounding frequencies.")
    if 1 + j / m <= 0:
        raise InputError("Nominal rate gives a nonpositive accumulation base.")
    ear = math.expm1(m * math.log1p(j / m))
    per_payment = math.expm1(math.log1p(ear) / p)
    if not all(math.isfinite(x) for x in (ear, per_payment)):
        raise UnsupportedInput("Converted rate exceeds numeric range.")
    return per_payment, ear


def nominal_from_effective(effective_annual_rate: object, compounding_frequency: object) -> float:
    """Inverse of nominal-to-effective conversion, REQ-TVM-02."""
    ear = parse_number(effective_annual_rate, "Effective annual rate")
    m = parse_positive_integer(compounding_frequency, "Compounding frequency")
    if ear <= -1:
        raise InputError("Effective annual rate must exceed -100%.")
    result = m * math.expm1(math.log1p(ear) / m)
    if not math.isfinite(result):
        raise UnsupportedInput("Nominal rate exceeds numeric range.")
    return result

def _growth(rate: float, periods: int) -> tuple[float, float]:
    if rate <= -1 or periods < 0:
        raise InputError("Periodic rate must exceed -100% and periods must be nonnegative.")
    exponent = periods * math.log1p(rate)
    try:
        power = math.exp(exponent)
        annuity = math.expm1(exponent) / rate if rate else float(periods)
    except OverflowError as exc:
        raise UnsupportedInput("Accumulation exceeds numeric range.") from exc
    if not math.isfinite(power) or not math.isfinite(annuity):
        raise UnsupportedInput("Accumulation exceeds numeric range.")
    return power, annuity


def _regular_value(pv: float, fv: float, pmt: float, rate: float, periods: int, due: bool) -> float:
    power, annuity = _growth(rate, periods)
    return pv * power + pmt * annuity * (1 + rate if due else 1) + fv


def _large_rate_roots(pv: float, fv: float, pmt: float, n: int, due: bool, mode: str) -> tuple[tuple[float, int], ...]:
    """Isolate up to two positive growth roots from the regular-payment coefficient pattern.

    The derivative has at most one positive root by Descartes' rule. Near a
    tangent where finite precision cannot certify multiplicity, fail closed.
    """
    started = time.perf_counter()
    deadline = 10 if mode == "Standard" else 30
    coeff = [fv] + [0.0] * n
    coeff[n] += pv
    for k in range(n):
        coeff[k + (1 if due else 0)] += pmt
    while len(coeff) > 1 and coeff[-1] == 0:
        coeff.pop()
    scale = max(abs(c) for c in coeff)
    if scale == 0:
        raise UndefinedResult("Rate is not identifiable from an identity of zero cash flows.")
    coeff = [c / scale for c in coeff]
    derivative = [k * coeff[k] for k in range(1, len(coeff))]
    lo_z = math.log(math.ulp(1.0) / 2)
    hi_z = math.log(1e300)

    def evaluate(poly: list[float], z: float) -> float:
        if time.perf_counter() - started > deadline:
            raise UnsupportedInput("Rate search exceeded the approved time limit.")
        highest = len(poly) - 1 if z >= 0 else 0
        return math.fsum(c * math.exp((k - highest) * z) for k, c in enumerate(poly) if c)

    def bisect(poly: list[float], left: float, right: float) -> float:
        f_left = evaluate(poly, left)
        for _ in range(180):
            middle = (left + right) / 2
            f_middle = evaluate(poly, middle)
            if middle == left or middle == right:
                return middle
            if (f_left > 0) == (f_middle > 0):
                left, f_left = middle, f_middle
            else:
                right = middle
        return (left + right) / 2

    boundaries = [lo_z, hi_z]
    derivative_signs = (evaluate(derivative, lo_z), evaluate(derivative, hi_z))
    if derivative_signs[0] * derivative_signs[1] < 0:
        boundaries.insert(1, bisect(derivative, lo_z, hi_z))
    roots = []
    for left, right in zip(boundaries, boundaries[1:]):
        f_left, f_right = evaluate(coeff, left), evaluate(coeff, right)
        if f_left * f_right < 0:
            z = bisect(coeff, left, right)
            rate = math.expm1(z)
            if rate <= -1 or not math.isfinite(rate):
                raise UnsupportedInput("Rate root is outside representable precision.")
            roots.append((rate, 1))
    if len(boundaries) == 3:
        at_extremum = evaluate(coeff, boundaries[1])
        if abs(at_extremum) <= 1e-10:
            raise UnsupportedInput("Near-tangent large-horizon rate cannot be certified at approved precision.")
    if not roots and abs(evaluate(coeff, 0.0)) <= 1e-14:
        roots.append((0.0, 1))
    verified = []
    for rate, multiplicity in roots:
        residual = evaluate(coeff, math.log1p(rate))
        if abs(residual) > 1e-10:
            raise UnsupportedInput("Large-horizon rate root failed its normalized residual.")
        verified.append((rate, multiplicity))
    return tuple(verified)

def _rate_roots(pv: float, fv: float, pmt: float, periods: int, due: bool, mode: str) -> tuple[tuple[float, int], ...]:
    """Exact structure for bounded regular schedules; never infer uniqueness by scan."""
    if periods > 100:
        return _large_rate_roots(pv, fv, pmt, periods, due, mode)
    # Sum of end payments pmt*x^k, k=0..n-1, where x=1+r.
    # Due payments shift the sum by x; the terminal signed FV is constant.
    coefficients = [fv] + [0.0] * periods
    coefficients[periods] += pv
    for k in range(periods):
        coefficients[k + (1 if due else 0)] += pmt
    if not any(coefficients):
        raise UndefinedResult("The cash-flow identity holds for every admissible rate; rate is not identifiable.")
    while coefficients and coefficients[-1] == 0:
        coefficients.pop()
    if len(coefficients) <= 1:
        return ()
    roots = positive_roots_with_multiplicity(coefficients)
    results = []
    for growth, multiplicity in roots:
        rate = growth - 1
        residual = _regular_value(pv, fv, pmt, rate, periods, due)
        scale = max(1.0, abs(pv), abs(fv), abs(pmt) * periods)
        if abs(residual) > 1e-10 * scale:
            raise UnsupportedInput("Certified rate root failed its cash-flow residual check.")
        results.append((rate, multiplicity))
    return tuple(sorted(results))


def _payment_schedule(pv: float, pmt: float, rate: float, periods: int, due: bool) -> tuple[list[dict], float]:
    schedule = []
    balance = pv
    for index in range(1, periods + 1):
        time = index - 1 if due else index
        beginning = balance
        if due:
            after_payment = beginning + pmt
            interest = after_payment * rate
            balance = after_payment + interest
        else:
            interest = beginning * rate
            balance = beginning + interest + pmt
        schedule.append({"period": index, "time": time, "payment": pmt,
                         "balance_begin": beginning, "interest": interest,
                         "balance_end": balance,
                         "future_value_at_end": pmt * (1 + rate) ** (periods - time)})
    return schedule, balance

def solve_regular(
    target: str, *, pv: object = None, fv: object = None, pmt: object = None,
    periods: object = None, annual_rate: object = None, payment_frequency: object = 1,
    compounding_frequency: object = 1, timing: str = "end", mode: str = "Standard", currency: object = None, execution_profile: str | None = None,
) -> CalculationResult:
    """Solve one unknown in PV*(1+r)^n + PMT*A_n*(1+r*w) + FV = 0."""
    unit = "decimal nominal annual rate" if target == "rate" else "payment periods" if target == "periods" else "currency"
    try:
        currency_code = parse_currency(currency)
        resource_mode = execution_profile or mode
        if mode not in {"Standard", "Advanced"}:
            raise InputError("Invalid financial controls mode.")
        if target not in {"pv", "fv", "pmt", "periods", "rate", "auto", None}:
            raise InputError("Choose one unknown: pv, fv, pmt, periods, rate, or auto.")
        if timing not in {"end", "beginning"}:
            raise InputError("Payment timing must be end or beginning.")
        fields = {"pv": pv, "fv": fv, "pmt": pmt, "periods": periods, "rate": annual_rate}
        blanks = [key for key, value in fields.items() if value is None or isinstance(value, str) and not value.strip()]
        if target in {"auto", None}:
            if len(blanks) != 1:
                raise InputError("Auto selection requires exactly one blank unknown.")
            target = blanks[0]
        if blanks != [target]:
            raise InputError("Exactly the selected unknown must be blank; enter zero explicitly elsewhere.")
        unit = "decimal nominal annual rate" if target == "rate" else "payment periods" if target == "periods" else currency_code
        p = parse_positive_integer(payment_frequency, "Payment frequency")
        m = parse_positive_integer(compounding_frequency, "Compounding frequency")
        if mode == "Standard" and p != m:
            raise UnsupportedInput("Standard mode requires matching frequencies.")
        due = timing == "beginning"
        if target == "periods":
            n = None
        else:
            n = parse_positive_integer(periods, "Payment periods")
            _profile(resource_mode, n)
        values = {k: parse_number(v, k.upper()) for k, v in fields.items() if k not in (target, "periods", "rate")}
        if target == "rate":
            roots = _rate_roots(values["pv"], values["fv"], values["pmt"], n, due, resource_mode)
            if not roots:
                raise UndefinedResult("No admissible rate satisfies the cash flows.")
            annual = tuple(m * math.expm1(p * math.log1p(r) / m) for r, _ in roots)
            warnings = []
            if len(roots) > 1:
                warnings.append("Multiple admissible rates; no single rate was chosen.")
            if any(mult > 1 for _, mult in roots):
                warnings.append("A repeated rate root was detected.")
            root_scenarios = []
            scale = max(1.0, abs(values["pv"]), abs(values["fv"]), abs(values["pmt"]) * n)
            for (periodic, multiplicity), nominal in zip(roots, annual):
                residual = _regular_value(values["pv"], values["fv"], values["pmt"], periodic, n, due)
                schedule, balance = _payment_schedule(values["pv"], values["pmt"], periodic, n, due)
                if abs(residual) > 1e-10 * scale or abs(balance + values["fv"]) > 1e-8 + 1e-10 * scale:
                    raise UnsupportedInput("Rate root failed substitution or schedule reconciliation.")
                root_scenarios.append({"periodic_rate": periodic, "nominal_annual_rate": nominal,
                    "multiplicity": multiplicity, "substitution_residual": residual,
                    "terminal_balance": balance, "schedule": schedule})
            cash_flow_timeline = [{"time": 0, "kind": "present value", "amount": values["pv"]}]
            cash_flow_timeline.extend({"time": index - 1 if due else index, "kind": "recurring payment", "amount": values["pmt"]} for index in range(1, n + 1))
            cash_flow_timeline.append({"time": n, "kind": "terminal cash flow", "amount": values["fv"]})
            interpretation = ("Multiple rates satisfy these signed cash flows; there is no unique implied rate."
                              if len(roots) > 1 else "This rate balances the stated signed cash flows at the selected payment times.")
            return CalculationResult(Status.VALID, annual if len(annual) > 1 else annual[0], unit,
                warnings=tuple(warnings), assumptions={"cash_flow_sign": "signed inflow positive; outflow negative",
                "currency": currency_code, "timing": timing,
                "rate_basis": "nominal annual compounded at stated frequency"},
                diagnostics={"periodic_roots": tuple(r for r, _ in roots),
                             "multiplicities": tuple(mult for _, mult in roots),
                             "formula": "PV*(1+r)^n + PMT*A_n(r)*(1+r*w) + FV = 0",
                             "interpretation": interpretation, "cash_flow_timeline": cash_flow_timeline,
                             "root_scenarios": root_scenarios})
        r, ear = periodic_rate(parse_number(annual_rate, "Nominal annual rate"), p, m, mode)
        factor = 1 + r if due else 1
        if target == "periods":
            a, b, c = values["pv"], values["fv"], values["pmt"]
            if r == 0:
                if c == 0:
                    raise UndefinedResult("Periods are not identifiable with zero rate and zero payment.")
                count = -(a + b) / c
            else:
                denominator = a + c * factor / r
                numerator = c * factor / r - b
                if denominator == 0 or numerator / denominator <= 0:
                    raise UndefinedResult("No real period count satisfies these cash flows.")
                count = math.log(numerator / denominator) / math.log1p(r)
            if not math.isfinite(count) or count <= 0:
                raise UndefinedResult("No positive period count satisfies these cash flows.")
            if abs(count - round(count)) > 1e-9:
                raise UnsupportedInput("A regular payment schedule requires a whole number of periods.")
            n = int(round(count))
            _profile(resource_mode, n)
            result = float(n)
        else:
            power, annuity = _growth(r, n)
            if target == "pv":
                result = -(values["fv"] + values["pmt"] * annuity * factor) / power
            elif target == "fv":
                result = -(values["pv"] * power + values["pmt"] * annuity * factor)
            else:
                if annuity * factor == 0:
                    raise UndefinedResult("Payment is not identifiable.")
                result = -(values["pv"] * power + values["fv"]) / (annuity * factor)
        if not math.isfinite(result):
            raise UnsupportedInput("Result exceeds numeric range.")
        solved = {**values, target: result}
        if target == "periods":
            solved["periods"] = n
        residual = _regular_value(solved["pv"], solved["fv"], solved["pmt"], r, n, due)
        scale = max(1.0, abs(solved["pv"]), abs(solved["fv"]), abs(solved["pmt"]) * n)
        if abs(residual) > 1e-10 * scale:
            raise UnsupportedInput("Solved value failed its cash-flow residual check.")
        schedule, balance = _payment_schedule(solved["pv"], solved["pmt"], r, n, due)
        if abs(balance + solved["fv"]) > 1e-8 + 1e-10 * scale:
            raise UnsupportedInput("Payment schedule did not reconcile to the terminal cash flow.")
        return CalculationResult(Status.VALID, result, unit,
            assumptions={"cash_flow_sign": "signed inflow positive; outflow negative", "currency": currency_code, "timing": timing,
                         "rate_basis": "nominal annual compounded at stated frequency", "effective_annual_rate": ear},
            diagnostics={"periodic_rate": r, "residual": residual, "schedule": schedule,
                         "formula": "PV*(1+r)^n + PMT*A_n(r)*(1+r*w) + FV = 0"})
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        status = Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.UNDEFINED if isinstance(exc, UndefinedResult) else Status.INVALID
        return CalculationResult(status, None, unit, message=str(exc))


def schedule_value(
    cash_flows: list[tuple[object, object]], *, annual_rate: object, payment_frequency: object = 1,
    compounding_frequency: object = 1, valuation_date: object = None,
    dated: bool = False, growth_rate: object = None, mode: str = "Advanced", currency: object = None, execution_profile: str | None = None,
) -> CalculationResult:
    """Present value of explicit signed regular or dated cash flows (D02/D03)."""
    try:
        currency_code = parse_currency(currency)
        resource_mode = execution_profile or mode
        if mode not in {"Standard", "Advanced"}:
            raise InputError("Invalid financial controls mode.")
        if not cash_flows:
            raise InputError("At least one cash flow is required.")
        _profile(resource_mode, len(cash_flows))
        if mode == "Standard" and (dated or growth_rate is not None):
            raise UnsupportedInput("Dated and growing schedules require Advanced mode.")
        p = parse_positive_integer(payment_frequency, "Payment frequency")
        m = parse_positive_integer(compounding_frequency, "Compounding frequency")
        rate, ear = periodic_rate(parse_number(annual_rate, "Nominal annual rate"), p, m, mode)
        base_date = _date(valuation_date, "Valuation date") if dated else None
        growth = parse_number(growth_rate, "Growth rate") if growth_rate is not None else None
        if growth is not None and growth <= -1:
            raise InputError("Growth rate must exceed -100%.")
        rows = []
        for index, (time_raw, amount_raw) in enumerate(cash_flows):
            amount = parse_number(amount_raw, f"Cash flow {index}")
            if dated:
                when = _date(time_raw, f"Cash flow {index} date")
                days = (when - base_date).days
                if days < 0:
                    raise InputError("Cash-flow date precedes valuation date.")
                exponent = days / 365
                label = when.isoformat()
                discount = math.exp(exponent * math.log1p(ear))
            else:
                time = parse_number(time_raw, f"Cash flow {index} time")
                if time < 0 or not time.is_integer():
                    raise UnsupportedInput("Regular custom times must be nonnegative whole payment periods.")
                exponent = int(time)
                label = int(time)
                discount = math.exp(exponent * math.log1p(rate))
            if growth is not None:
                if dated or exponent < 1:
                    raise UnsupportedInput("Growing schedule starts at regular period 1.")
                amount *= (1 + growth) ** (exponent - 1)
            pv = amount / discount
            if not math.isfinite(pv):
                raise UnsupportedInput("Discounted cash flow exceeds numeric range.")
            rows.append({"time": label, "amount": amount, "present_value": pv})
        total = math.fsum(row["present_value"] for row in rows)
        if not math.isfinite(total):
            raise UnsupportedInput("Present value exceeds numeric range.")
        return CalculationResult(Status.VALID, total, currency_code, assumptions={
            "cash_flow_sign": "signed inflow positive; outflow negative", "currency": currency_code, "date_basis": "actual/365" if dated else "regular payment periods",
            "valuation_date": base_date.isoformat() if dated else None, "effective_annual_rate": ear},
            diagnostics={"schedule": rows, "formula": "sum(C_t / accumulation(t))"})
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        status = Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.UNDEFINED if isinstance(exc, UndefinedResult) else Status.INVALID
        return CalculationResult(status, None, "currency", message=str(exc))
