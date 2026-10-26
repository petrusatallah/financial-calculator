"""S3 investment appraisal under approved D03/D07/D13 conventions."""
from __future__ import annotations

import math
import time
from datetime import date
from collections import defaultdict

from .result import CalculationResult, Status
from .roots import positive_roots_with_multiplicity
from .validation import InputError, UnsupportedInput, parse_currency, parse_number, parse_positive_integer


class Incomplete(InputError):
    pass


def _clock(started, mode):
    if time.monotonic() - started > (10 if mode == "Standard" else 30):
        raise Incomplete(f"{mode} appraisal exceeded its approved time limit.")


def _limit(mode, rows):
    if mode not in {"Standard", "Advanced"}:
        raise InputError("Mode must be Standard or Advanced.")
    bound = 1000 if mode == "Standard" else 10000
    if rows > bound:
        raise UnsupportedInput(f"{mode} supports at most {bound} cash-flow rows or evaluations.")
    memory_limit = (256 if mode == "Standard" else 512) * 1024 * 1024
    if rows * 4096 > memory_limit:
        raise Incomplete(f"{mode} appraisal exceeds its estimated working-memory limit.")


def _date(raw):
    try:
        if isinstance(raw, date) and not hasattr(raw, "hour"):
            return raw
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError) as exc:
        raise InputError("Dates must be ISO YYYY-MM-DD values.") from exc


def _rows(cash_flows, dated, valuation_date, frequency, mode):
    if not isinstance(cash_flows, (list, tuple)) or not cash_flows:
        raise InputError("At least one signed cash flow is required.")
    _limit(mode, len(cash_flows))
    base = _date(valuation_date) if dated else None
    freq = None if dated else parse_positive_integer(frequency, "Periods per year")
    rows = []
    last = None
    for index, item in enumerate(cash_flows):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise InputError(f"Cash-flow row {index} needs a time/date and amount.")
        raw_time, raw_amount = item
        if any(isinstance(value, str) and len(value) > 128 for value in (raw_time, raw_amount)):
            raise UnsupportedInput("Cash-flow field exceeds the bounded input length.")
        amount = parse_number(raw_amount, f"Cash flow {index}")
        if dated:
            when = _date(raw_time)
            if when < base:
                raise InputError("Cash-flow date precedes valuation date.")
            if last is not None and when < last:
                raise InputError("Dated cash flows must be chronological; same-day rows are allowed.")
            last = when
            elapsed = (when - base).days / 365
            label = when.isoformat()
        else:
            point = parse_number(raw_time, f"Cash flow {index} time")
            if not point.is_integer() or int(point) != index:
                raise UnsupportedInput("Regular cash flows require consecutive whole periods beginning at t=0.")
            elapsed = index / freq
            label = index
        rows.append({"time": label, "years": elapsed, "amount": amount})
    if rows[0]["years"] != 0:
        raise InputError("The first cash flow must be at the valuation time.")
    return rows, base, freq


def _discount(amount, rate, years):
    return amount * math.exp(-years * math.log1p(rate))


def _irr_regular(rows, frequency, started, mode):
    # x=(1+annual_rate)^(-1/frequency)>0; polynomial coefficients are C_t.
    if len(rows) > 21:
        return _irr_exponential(rows, started, mode)
    coefficients = [row["amount"] for row in rows]
    roots = positive_roots_with_multiplicity(coefficients)
    answers = []
    for x, multiplicity in roots:
        _clock(started, mode)
        annual = math.expm1(-frequency * math.log(x))
        if not math.isfinite(annual) or annual <= -1:
            raise Incomplete("IRR root is outside representable precision.")
        answers.append((annual, multiplicity))
    return sorted(answers)


def _irr_exponential(rows, started, mode):
    # All dated exponents are integer day counts over 365. If their greatest
    # common day step yields a small degree, exact polynomial root counts
    # distinguish near-tangent no-root and two-root cases.
    if rows and isinstance(rows[0]["time"], str):
        origin = _date(rows[0]["time"])
        days = [(_date(row["time"]) - origin).days for row in rows]
        step = math.gcd(*days)
        if step and max(days) // step <= 20:
            coefficients = [0.0] * (max(days) // step + 1)
            for day, row in zip(days, rows):
                coefficients[day // step] += row["amount"]
            return sorted((math.expm1(-365 / step * math.log(x)), multiplicity)
                          for x, multiplicity in positive_roots_with_multiplicity(coefficients))
    # Generalized Descartes bounds the distinct positive roots by sign
    # changes. Uncertified near-tangencies return INCOMPLETE.
    grouped = defaultdict(float)
    for row in rows:
        grouped[row["years"]] += row["amount"]
    terms = [(t, c) for t, c in sorted(grouped.items()) if c]
    if not terms:
        return []
    if all(float(t).is_integer() for t, _ in terms) and terms[-1][0] <= 20:
        coefficients = [0.0] * (int(terms[-1][0]) + 1)
        for year, amount in terms:
            coefficients[int(year)] = amount
        return sorted((math.expm1(-math.log(x)), multiplicity)
                      for x, multiplicity in positive_roots_with_multiplicity(coefficients))
    signs = sum((a[1] > 0) != (b[1] > 0) for a, b in zip(terms, terms[1:]))
    if signs == 0:
        return []
    if signs > 1 and len(terms) > 40:
        raise Incomplete("Complete multi-root dated IRR search exceeded the certified term bound.")
    scale = max(abs(c) for _, c in terms)
    terms = [(t, c / scale) for t, c in terms]

    def evaluate(items, z):
        _clock(started, mode)
        anchor = max(t * z for t, _ in items)
        return math.fsum(c * math.exp(t * z - anchor) for t, c in items)

    def bisect(items, left, right):
        fleft = evaluate(items, left)
        for _ in range(220):
            mid = (left + right) / 2
            fmid = evaluate(items, mid)
            if mid in (left, right):
                break
            if (fleft > 0) == (fmid > 0):
                left, fleft = mid, fmid
            else:
                right = mid
        return (left + right) / 2

    def critical(items):
        if len(items) <= 2:
            return []
        first_t = items[0][0]
        derivative = [(t - first_t, c * (t - first_t)) for t, c in items[1:]]
        return isolate(derivative)

    def isolate(items):
        _clock(started, mode)
        if len(items) == 2:
            (t0, c0), (t1, c1) = items
            if c0 * c1 >= 0:
                return []
            root = math.log(-c0 / c1) / (t1 - t0)
            return [(root, 1)] if -690 < root < 690 else []
        extrema = critical(items)
        bounds = [-690.0, *(z for z, _ in extrema), 690.0]
        candidates = []
        for z, multiplicity in extrema:
            if abs(evaluate(items, z)) <= 1e-12:
                raise Incomplete("Near-tangent IRR cannot be certified from a small floating residual.")
        for left, right in zip(bounds, bounds[1:]):
            a, b = evaluate(items, left), evaluate(items, right)
            if a * b < 0:
                candidates.append((bisect(items, left, right), 1))
        unique = []
        for root in sorted(candidates):
            if not unique or abs(root[0] - unique[-1][0]) > 1e-8:
                unique.append(root)
            else:
                unique[-1] = max(unique[-1], root, key=lambda item: item[1])
        return unique

    if signs == 1:
        left, right = -690.0, 690.0
        if evaluate(terms, left) * evaluate(terms, right) >= 0:
            raise Incomplete("Single-sign-change IRR lies outside the certified numeric domain.")
        z_roots = [(bisect(terms, left, right), 1)]
    else:
        z_roots = isolate(terms)
    answers = []
    for z, multiplicity in z_roots:
        annual = math.expm1(-z)
        if not math.isfinite(annual) or annual <= -1:
            raise Incomplete("IRR root is outside representable precision.")
        answers.append((annual, multiplicity))
    return sorted(answers)


def _recovery(grouped, dated, discount_rate=None):
    cumulative = 0.0
    balances = []
    crossings = []
    previous_time = 0.0
    for index, (label, years, amount) in enumerate(grouped):
        value = _discount(amount, discount_rate, years) if discount_rate is not None else amount
        before = cumulative
        cumulative += value
        balances.append(cumulative)
        if index and before < 0 <= cumulative and value > 0:
            crossing = label if dated else previous_time + (years - previous_time) * (-before / value)
            crossings.append((crossing, index))
        previous_time = years
    minimum_from = [0.0] * len(balances)
    minimum = math.inf
    for index in range(len(balances) - 1, -1, -1):
        minimum = min(minimum, balances[index])
        minimum_from[index] = minimum
    first_crossing = crossings[0][0] if crossings else None
    sustained = next((crossing for crossing, index in crossings
                      if minimum_from[index] >= -1e-10), None)
    reversal = bool(crossings and sustained != first_crossing)
    return {"first": first_crossing, "sustained": sustained, "reversal": reversal,
            "status": Status.VALID.value if first_crossing is not None else Status.UNDEFINED.value,
            "unit": "ISO date" if dated else "years"}

def analyze_project(cash_flows, *, annual_discount_rate, currency, dated=False,
                    valuation_date=None, frequency=1, annual_finance_rate=None,
                    annual_reinvestment_rate=None, mode="Standard") -> CalculationResult:
    started = time.monotonic()
    try:
        code = parse_currency(currency)
        rows, base, freq = _rows(cash_flows, dated, valuation_date, frequency, mode)
        discount = parse_number(annual_discount_rate, "Annual effective discount rate")
        finance = parse_number(annual_finance_rate if annual_finance_rate is not None else discount,
                               "Annual effective finance rate")
        reinvest = parse_number(annual_reinvestment_rate if annual_reinvestment_rate is not None else discount,
                                "Annual effective reinvestment rate")
        if min(discount, finance, reinvest) <= -1:
            raise InputError("Discount, finance and reinvestment rates must exceed -100%.")
        for row in rows:
            _clock(started, mode)
            row["discounted"] = _discount(row["amount"], discount, row["years"])
        npv = math.fsum(row["discounted"] for row in rows)
        if not math.isfinite(npv):
            raise UnsupportedInput("NPV exceeds numeric range.")
        warnings = []
        amounts = [row["amount"] for row in rows]
        sign_changes = sum((a > 0) != (b > 0) for a, b in zip([x for x in amounts if x], [x for x in amounts if x][1:]))
        if sign_changes > 1:
            warnings.append("Multiple cash-flow sign changes: IRR may be nonunique.")
        if any(row["amount"] < 0 and row["years"] > 0 for row in rows):
            warnings.append("Later investment outflows are included in PI and every cash-flow metric.")
        grouped_for_irr = defaultdict(list)
        for row in rows:
            grouped_for_irr[row["years"]].append(row["amount"])
        identity = all(math.fsum(values) == 0 for values in grouped_for_irr.values())
        if identity:
            irr = {"status": Status.UNDEFINED.value, "roots": [],
                   "message": "NPV is zero for every admissible rate; IRR is indeterminate."}
        else:
            roots = (_irr_exponential(rows, started, mode) if dated else _irr_regular(rows, freq, started, mode))
            checked = []
            scale = max(1.0, math.fsum(abs(x) for x in amounts))
            for rate, multiplicity in roots:
                residual = math.fsum(_discount(row["amount"], rate, row["years"]) for row in rows)
                if abs(residual) > 1e-10 * scale:
                    raise Incomplete("IRR candidate failed normalized residual certification.")
                checked.append({"annual_effective_rate": rate, "multiplicity": multiplicity,
                                "normalized_residual": residual / scale})
            irr = {"status": Status.VALID.value if checked else Status.UNDEFINED.value,
                   "roots": checked, "message": "All admissible roots reported." if checked else "No admissible IRR root."}
            if len(checked) > 1:
                warnings.append("Multiple admissible IRRs; no single IRR was chosen.")
            if any(root["multiplicity"] > 1 for root in checked):
                warnings.append("Repeated IRR root detected.")
        terminal = rows[-1]["years"]
        positives = math.fsum(row["amount"] * math.exp((terminal-row["years"])*math.log1p(reinvest))
                              for row in rows if row["amount"] > 0)
        negatives = math.fsum(_discount(row["amount"], finance, row["years"])
                              for row in rows if row["amount"] < 0)
        mirr = (math.expm1(math.log(positives / -negatives) / terminal)
                if terminal > 0 and positives > 0 and negatives < 0 else None)
        pv_positive = math.fsum(row["discounted"] for row in rows if row["amount"] > 0)
        pv_negative = -math.fsum(row["discounted"] for row in rows if row["amount"] < 0)
        pi = pv_positive / pv_negative if pv_negative > 0 else None
        grouped_map = defaultdict(float)
        for row in rows:
            grouped_map[(row["time"], row["years"])] += row["amount"]
        grouped = [(label, years, amount) for (label, years), amount in grouped_map.items()]
        payback = _recovery(grouped, dated)
        discounted_grouped = [(label, years, amount) for label, years, amount in grouped]
        discounted_payback = _recovery(discounted_grouped, dated, discount)
        if payback["reversal"] or discounted_payback["reversal"]:
            warnings.append("First recovery is reversed by a later loss; sustained recovery is shown separately.")
        _clock(started, mode)
        return CalculationResult(Status.VALID, npv, code, warnings=tuple(warnings),
            assumptions={"currency": code, "cash_flow_sign": "signed inflow positive; outflow negative",
                         "date_basis": "actual/365" if dated else f"{freq} regular periods per year",
                         "rate_basis": "annual effective", "valuation_date": base.isoformat() if base else None,
                         "finance_rate": finance, "reinvestment_rate": reinvest},
            diagnostics={"npv": npv, "irr": irr, "mirr": {"status": Status.VALID.value if mirr is not None else Status.UNDEFINED.value,
                         "annual_effective_rate": mirr}, "payback": payback,
                         "discounted_payback": discounted_payback,
                         "profitability_index": {"status": Status.VALID.value if pi is not None else Status.UNDEFINED.value,
                                                 "value": pi}, "cash_flow_schedule": rows,
                         "formula": "NPV = sum(C_i/(1+r)^years_i)"})
    except Incomplete as exc:
        return CalculationResult(Status.INCOMPLETE, None, "", message=str(exc))
    except (InputError, ValueError, OverflowError, ZeroDivisionError) as exc:
        status = Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.INVALID
        return CalculationResult(status, None, "", message=str(exc))
