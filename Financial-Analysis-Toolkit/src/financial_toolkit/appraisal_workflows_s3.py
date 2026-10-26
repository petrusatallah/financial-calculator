"""S3 project comparison, sensitivity and coherent scenario workflows (D07)."""
from __future__ import annotations

import copy
import math
import time

from .appraisal_s3 import Incomplete, _clock, _limit, analyze_project
from .result import CalculationResult, Status
from .validation import InputError, UnsupportedInput, parse_number


def _result_error(message, status=Status.INVALID):
    return CalculationResult(status, None, "", message=message)


def _apply(base, changes):
    spec = copy.deepcopy(base)
    for name, raw in changes.items():
        value = parse_number(raw, name)
        if name in {"annual_discount_rate", "annual_finance_rate", "annual_reinvestment_rate"}:
            spec[name] = value
        elif name == "future_flow_multiplier":
            spec["cash_flows"] = [(t, amount if i == 0 else parse_number(amount, "Cash flow") * value)
                                  for i, (t, amount) in enumerate(spec["cash_flows"])]
        elif name.startswith("cash_flow:"):
            try:
                index = int(name.split(":", 1)[1])
            except ValueError as exc:
                raise InputError("Cash-flow driver requires a row index.") from exc
            if index < 0 or index >= len(spec["cash_flows"]):
                raise InputError("Cash-flow driver row is outside the schedule.")
            rows = list(spec["cash_flows"])
            rows[index] = (rows[index][0], value)
            spec["cash_flows"] = rows
        else:
            raise InputError(f"Unsupported sensitivity/scenario driver: {name}.")
    return spec


def _profiled(inputs, mode):
    if inputs.get("mode", mode) != mode:
        raise InputError("Project mode conflicts with the selected workflow mode.")
    return {**inputs, "mode": mode}


def _check_result(result):
    if result.status == Status.INVALID:
        raise InputError(f"Project input is invalid: {result.message}")
    if result.status == Status.UNSUPPORTED:
        raise UnsupportedInput(f"Project input is unsupported: {result.message}")
    if result.status != Status.VALID:
        raise Incomplete(f"Scenario could not complete: {result.status}: {result.message}")


def compare_projects(projects, *, repeatable=False, mode="Standard"):
    started = time.monotonic()
    try:
        if not isinstance(projects, (list, tuple)) or len(projects) < 2:
            raise InputError("Compare at least two projects.")
        _limit(mode, len(projects))
        results = []
        for item in projects:
            _clock(started, mode)
            if not isinstance(item, dict) or "name" not in item or "inputs" not in item:
                raise InputError("Each project needs a name and appraisal inputs.")
            result = analyze_project(**_profiled(item["inputs"], mode))
            _check_result(result)
            schedule = result.diagnostics["cash_flow_schedule"]
            results.append({"name": str(item["name"]), "npv": result.value,
                            "irr": result.diagnostics["irr"], "currency": result.unit,
                            "valuation_date": result.assumptions["valuation_date"],
                            "dated": bool(item["inputs"].get("dated", False)),
                            "annual_discount_rate": parse_number(item["inputs"]["annual_discount_rate"], "Discount rate"),
                            "horizon_years": schedule[-1]["years"], "warnings": result.warnings})
        first = results[0]
        common_basis = all((r["currency"], r["valuation_date"], r["dated"], r["annual_discount_rate"]) ==
                           (first["currency"], first["valuation_date"], first["dated"], first["annual_discount_rate"])
                           for r in results)
        equal_horizon = all(abs(r["horizon_years"] - first["horizon_years"]) <= 1e-12 for r in results)
        warnings = []
        if not common_basis:
            warnings.append("Projects differ in currency, valuation date, flow basis or discount rate; no ranking is justified.")
        elif not equal_horizon and not repeatable:
            warnings.append("Unequal project lives require explicit repeatability for an annualized ranking.")
        ranked_by = None
        if common_basis and equal_horizon:
            ranked_by = "NPV"
        elif common_basis and repeatable and all(r["horizon_years"] > 0 for r in results):
            rate = first["annual_discount_rate"]
            if rate <= -1:
                raise InputError("Discount rate must exceed -100%.")
            for row in results:
                years = row["horizon_years"]
                factor = years if rate == 0 else -math.expm1(-years * math.log1p(rate)) / rate
                row["equivalent_annual_annuity"] = row["npv"] / factor
            ranked_by = "equivalent_annual_annuity"
            warnings.append("Equivalent annual annuity assumes each project can be repeated on the same terms.")
        ranking = sorted(results, key=lambda r: r["npv"] if ranked_by == "NPV" else
                         r["equivalent_annual_annuity"], reverse=True) if ranked_by else []
        if ranked_by:
            unique_irrs = [r["irr"]["roots"][0]["annual_effective_rate"] if len(r["irr"]["roots"]) == 1 else None
                           for r in results]
            if all(rate is not None for rate in unique_irrs):
                irr_winner = max(range(len(results)), key=lambda i: unique_irrs[i])
                if results[irr_winner]["name"] != ranking[0]["name"]:
                    warnings.append("IRR and monetary-value rankings conflict; NPV/EAA basis is shown.")
        _clock(started, mode)
        return CalculationResult(Status.VALID, ranking[0]["npv"] if ranking else None, first["currency"],
            warnings=tuple(warnings), assumptions={"ranking_basis": ranked_by, "repeatable": bool(repeatable)},
            diagnostics={"projects": results, "ranking": [r["name"] for r in ranking],
                         "ranked_by": ranked_by})
    except Incomplete as exc:
        return _result_error(str(exc), Status.INCOMPLETE)
    except (InputError, OverflowError, ValueError, ZeroDivisionError) as exc:
        return _result_error(str(exc), Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.INVALID)


def sensitivity(base, driver_x, values_x, *, driver_y=None, values_y=None, mode="Standard"):
    started = time.monotonic()
    try:
        if not values_x or (driver_y is not None and not values_y):
            raise InputError("Sensitivity requires explicit driver values.")
        y_values = list(values_y) if driver_y is not None else [None]
        _limit(mode, len(values_x) * len(y_values))
        base_result = analyze_project(**_profiled(base, mode))
        _check_result(base_result)
        rows = []
        for x in values_x:
            for y in y_values:
                _clock(started, mode)
                changes = {driver_x: x}
                if driver_y is not None:
                    if driver_y == driver_x:
                        raise InputError("Two-way sensitivity drivers must differ.")
                    changes[driver_y] = y
                result = analyze_project(**_profiled(_apply(base, changes), mode))
                _check_result(result)
                rows.append({"x": parse_number(x, driver_x), "y": None if y is None else parse_number(y, driver_y),
                             "npv": result.value, "irr": result.diagnostics["irr"],
                             "mirr": result.diagnostics["mirr"]})
        _clock(started, mode)
        return CalculationResult(Status.VALID, None, base["currency"],
            diagnostics={"driver_x": driver_x, "driver_y": driver_y, "base_npv": base_result.value, "grid": rows})
    except Incomplete as exc:
        return _result_error(str(exc), Status.INCOMPLETE)
    except (InputError, OverflowError, ValueError, ZeroDivisionError) as exc:
        return _result_error(str(exc), Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.INVALID)


def scenarios(base, cases, *, exclusive_exhaustive=False, mode="Standard"):
    started = time.monotonic()
    try:
        if not isinstance(cases, (list, tuple)) or not cases:
            raise InputError("At least one named scenario is required.")
        _limit(mode, len(cases))
        probability_flags = ["probability" in case for case in cases]
        if any(probability_flags) and not all(probability_flags):
            raise InputError("Either every scenario has a probability or none do.")
        if any(probability_flags) and not exclusive_exhaustive:
            raise InputError("Probability weighting requires explicit mutually exclusive, exhaustive scenarios.")
        probabilities = [parse_number(case["probability"], "Scenario probability") for case in cases] if all(probability_flags) else []
        if probabilities and (any(p < 0 or p > 1 for p in probabilities) or abs(math.fsum(probabilities)-1) > 1e-9):
            raise InputError("Scenario probabilities must be in [0,1] and sum to one.")
        base_result = analyze_project(**_profiled(base, mode))
        _check_result(base_result)
        outputs = []
        names = set()
        for index, case in enumerate(cases):
            _clock(started, mode)
            if not isinstance(case, dict) or "name" not in case or "overrides" not in case:
                raise InputError("Each scenario needs a name and joint driver overrides.")
            name = str(case["name"]).strip()
            if not name or name in names:
                raise InputError("Scenario names must be nonempty and unique.")
            names.add(name)
            result = analyze_project(**_profiled(_apply(base, case["overrides"]), mode))
            _check_result(result)
            outputs.append({"name": name, "overrides": case["overrides"], "npv": result.value,
                            "probability": probabilities[index] if probabilities else None})
        expected = math.fsum(row["npv"] * row["probability"] for row in outputs) if probabilities else None
        _clock(started, mode)
        return CalculationResult(Status.VALID, expected, base["currency"],
            assumptions={"exclusive_exhaustive": bool(exclusive_exhaustive),
                         "probability_weighted": bool(probabilities)},
            diagnostics={"base_npv": base_result.value, "scenarios": outputs, "expected_npv": expected})
    except Incomplete as exc:
        return _result_error(str(exc), Status.INCOMPLETE)
    except (InputError, OverflowError, ValueError, ZeroDivisionError, TypeError) as exc:
        return _result_error(str(exc), Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.INVALID)
