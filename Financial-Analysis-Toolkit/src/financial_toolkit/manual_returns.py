"""Manual, aligned return analysis for the Investments and Portfolio screens.

The accepted S4 covariance validator and Markowitz solver remain the source of
portfolio mathematics. Values at this boundary are percentages; engine values
are decimal simple returns per observation period.
"""
from __future__ import annotations

from datetime import date
import math

import numpy as np

from .optimization_s4 import optimize_portfolio
from .portfolio_s4 import _covariance, analyze_portfolio
from .validation import InputError


INVESTMENT_OPTIONS = (
    "Average historical return", "Variance", "Volatility (standard deviation)", "Risk Analysis",
    "Covariance matrix", "Correlation matrix", "Sharpe ratio", "Beta",
    "CAPM required return",
)
PORTFOLIO_OPTIONS = (
    "Portfolio statistics", "Covariance and correlation matrix", "Compare portfolios",
    "Markowitz optimization — Minimum variance",
    "Markowitz optimization — Maximum Sharpe ratio",
    "Markowitz optimization — Target return", "Efficient frontier",
)


def _percent(value, label):
    try:
        number = float(str(value).strip().removesuffix("%")) / 100
    except (TypeError, ValueError) as exc:
        raise InputError(f"{label} must be a percentage number.") from exc
    if not math.isfinite(number):
        raise InputError(f"{label} must be finite.")
    if number < -1:
        raise InputError(f"{label} cannot be below -100% for a simple return.")
    return number


def _annual_rate(value, label):
    rate = _percent(value, label)
    if rate <= -1:
        raise InputError(f"{label} must exceed -100% for period conversion.")
    return rate


def investment_weight_total(weights, cash_weight=None):
    """Return the displayed allocation total in percent, or None for incomplete input."""
    try:
        entries = [*weights.values()]
        if cash_weight is not None:
            entries.append(cash_weight)
        if not entries or any(str(value).strip() == "" for value in entries):
            return None
        parsed = [float(str(value).strip().removesuffix("%")) for value in entries]
        return math.fsum(parsed) if all(math.isfinite(value) for value in parsed) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _observations(names, rows, frequency):
    if frequency not in ("monthly", "yearly"):
        raise InputError("Choose Monthly or Yearly frequency.")
    if not names or any(not isinstance(x, str) or not x.strip() for x in names):
        raise InputError("Every column needs a name.")
    names = [x.strip() for x in names]
    if len(names) != len(set(names)):
        raise InputError("Investment or portfolio names must be unique.")
    if len(rows) < 2:
        raise InputError("At least two aligned return periods are required.")
    dates, values = [], []
    for index, row in enumerate(rows, 1):
        raw_date = str(row.get("Date", "")).strip()
        try:
            day = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise InputError(f"Row {index}: enter a valid YYYY-MM-DD date.") from exc
        if dates and day <= dates[-1]:
            raise InputError("Dates must be unique and increasing.")
        dates.append(day)
        values.append([_percent(row.get(name, ""), f"{name} on {raw_date}") for name in names])
    periods = [(d.year, d.month) if frequency == "monthly" else d.year for d in dates]
    if len(set(periods)) != len(periods):
        raise InputError("Enter at most one observation per selected month or year.")
    return names, [d.isoformat() for d in dates], np.asarray(values, dtype=float)


def _allocation(names, weights, cash_weight, mode, lower_bounds, upper_bounds,
                gross_cap, net_min, net_max, allow_short):
    """Validate an explicit complete allocation using the approved S4 tolerances."""
    if not isinstance(weights, dict) or set(weights) != set(names):
        raise InputError("Enter a Weight (%) for every identified investment.")

    def weight(value, label):
        try:
            parsed = float(str(value).strip().removesuffix("%")) / 100
        except (TypeError, ValueError) as exc:
            raise InputError(f"{label} must be a percentage number.") from exc
        if not math.isfinite(parsed):
            raise InputError(f"{label} must be finite.")
        return parsed

    w = np.asarray([weight(weights[name], f"Weight for {name}") for name in names])
    cash = weight(cash_weight, "Cash weight")
    if abs(math.fsum([*w, cash]) - 1) > 1e-7:
        raise InputError("Investment weights must total 100%." if mode == "Standard" else
                         "Investment weights plus cash weight must total 100%.")
    if mode == "Standard":
        if np.any(w < 0) or cash < 0:
            raise InputError("Standard weights, including cash, cannot be negative.")
    else:
        if not isinstance(lower_bounds, dict) or not isinstance(upper_bounds, dict) or set(lower_bounds) != set(names) or set(upper_bounds) != set(names):
            raise InputError("Advanced bounds must cover every investment.")
        if any(value is None for value in (gross_cap, net_min, net_max)):
            raise InputError("Enter Advanced gross and net exposure limits.")
        lower = np.asarray([weight(lower_bounds[name], f"Lower bound for {name}") for name in names])
        upper = np.asarray([weight(upper_bounds[name], f"Upper bound for {name}") for name in names])
        if np.any(lower > upper) or np.any(w < lower - 1e-7) or np.any(w > upper + 1e-7):
            raise InputError("Entered weights violate the Advanced investment bounds.")
        if not allow_short and np.any(w < 0):
            raise InputError("Negative investment weights require Allow short positions.")
        gross = weight(gross_cap, "Gross exposure cap")
        net_low = weight(net_min, "Minimum net exposure")
        net_high = weight(net_max, "Maximum net exposure")
        net = math.fsum(w)
        if gross < 0 or net_low > net_high or math.fsum(abs(x) for x in w) > gross + 1e-7 or net < net_low - 1e-7 or net > net_high + 1e-7:
            raise InputError("Entered weights violate the Advanced gross or net exposure limits.")
    return w, cash


def calculate_manual_returns(*, kind, names, rows, frequency, option,
                             risk_free_annual=None, benchmark=None,
                             expected_market_annual=None, target_return=None,
                             financial_mode="Standard", lower_bounds=None,
                             upper_bounds=None, gross_cap=None, net_min=None,
                             net_max=None, allow_short=False, weights=None,
                             cash_weight=None, cash_annual_yield=None,
                             funding_annual_rate=None):
    """Return display-ready results with unrounded decimal calculations."""
    if kind not in ("Investments", "Portfolio"):
        raise InputError("Choose Investments or Portfolio.")
    options = INVESTMENT_OPTIONS if kind == "Investments" else PORTFOLIO_OPTIONS
    if option not in options:
        raise InputError("Choose a calculation from the dropdown.")
    if financial_mode not in ("Standard", "Advanced"):
        raise InputError("Select Standard or Advanced financial controls.")
    max_names, max_rows = (50, 5000) if financial_mode == "Standard" else (200, 20000)
    if len(names) > max_names or len(rows) > max_rows:
        raise InputError(f"{financial_mode} supports at most {max_names} columns and {max_rows} return periods.")
    names, dates, matrix = _observations(names, rows, frequency)
    allocation = None
    if kind == "Investments":
        allocation = _allocation(names, weights, cash_weight, financial_mode,
                                 lower_bounds, upper_bounds, gross_cap, net_min,
                                 net_max, allow_short)
    # Center about an observed value before computing moments. This keeps small
    # differences resolvable when returns have a much larger common level.
    offsets = matrix[0].copy()
    shifted = matrix - offsets
    covariance, eig_min, _, scale = _covariance(shifted)
    mean = offsets + shifted.mean(axis=0)
    variance = np.diag(covariance).copy()
    volatility = np.sqrt(np.maximum(variance, 0))
    sensitivity_floor = 1e-12 * max(1.0, float(np.max(np.abs(matrix))))
    denominator = np.outer(volatility, volatility)
    correlation = np.divide(covariance, denominator,
                            out=np.full_like(covariance, np.nan), where=denominator > 0)
    np.clip(correlation, -1, 1, out=correlation, where=np.isfinite(correlation))
    q = 12 if frequency == "monthly" else 1
    cash_period = 0.0
    if allocation is not None:
        _, cash = allocation
        if cash > 0:
            if cash_annual_yield in (None, ""):
                raise InputError("Positive cash weight requires an explicit annual effective cash yield.")
            cash_period = (1 + _annual_rate(cash_annual_yield, "Cash annual effective yield")) ** (1 / q) - 1
        elif cash < 0:
            if funding_annual_rate in (None, ""):
                raise InputError("Negative cash weight requires an explicit annual effective funding rate.")
            cash_period = (1 + _annual_rate(funding_annual_rate, "Funding annual effective rate")) ** (1 / q) - 1
    requires_rf = option in ("Sharpe ratio", "CAPM required return",
                             "Markowitz optimization — Maximum Sharpe ratio")
    uses_rf = requires_rf or (kind == "Portfolio" and option == "Portfolio statistics")
    risk_free = None if not uses_rf or risk_free_annual in (None, "") else _annual_rate(risk_free_annual, "Annual effective risk-free rate")
    risk_free_period = None if risk_free is None else (1 + risk_free) ** (1 / q) - 1
    if requires_rf and risk_free is None:
        raise InputError("Enter an annual effective risk-free rate for this calculation.")
    benchmark_values = None
    benchmark_mean = None
    beta = None
    benchmark_var = None
    benchmark_covariances = None
    if option in ("Beta", "CAPM required return"):
        if benchmark is None:
            raise InputError("Enter matching historical benchmark returns.")
        try:
            benchmark_values = np.asarray([_percent(benchmark[d], f"Benchmark on {d}") for d in dates])
        except KeyError as exc:
            raise InputError(f"Benchmark is missing a return for {exc.args[0]}.") from exc
        shifted_benchmark = benchmark_values - benchmark_values[0]
        benchmark_mean = float(benchmark_values[0] + shifted_benchmark.mean())
        benchmark_var = float(np.var(shifted_benchmark, ddof=1))
        if benchmark_var > 0:
            benchmark_covariances = np.array([np.cov(shifted[:, i], shifted_benchmark, ddof=1)[0, 1]
                                              for i in range(len(names))])
            beta = benchmark_covariances / benchmark_var
    market_period = None
    market_annual = None
    capm = None
    if option == "CAPM required return":
        if expected_market_annual in (None, ""):
            raise InputError("Enter the expected annual market return for CAPM.")
        market_annual = _annual_rate(expected_market_annual, "Expected annual market return")
        market_period = (1 + market_annual) ** (1 / q) - 1
        if beta is not None:
            capm = risk_free_period + beta * (market_period - risk_free_period)
    sharpe = None if risk_free_period is None else np.divide(mean-risk_free_period, volatility,
        out=np.full_like(mean, np.nan), where=volatility > 0)
    warnings = []
    parsed_dates = [date.fromisoformat(day) for day in dates]
    periods = [day.year*12+day.month if frequency == "monthly" else day.year for day in parsed_dates]
    if any(b-a != 1 for a, b in zip(periods, periods[1:])):
        warnings.append("Dates skip selected periods; rate conversion assumes each entered return covers one month or year.")
    if len(dates) < 4:
        warnings.append("Few observations: volatility, beta and optimized weights may be unreliable.")
    if eig_min <= 1e-10 * scale:
        warnings.append("Covariance is singular or nearly singular; optimized weights may be unstable.")
    if np.any(volatility == 0):
        warnings.append("Correlation and Sharpe are undefined for zero-volatility series.")
    if np.any((volatility > 0) & (volatility <= sensitivity_floor)):
        warnings.append("Some return series have small positive volatility; correlation and Sharpe estimates may be numerically sensitive.")
    if option in ("Beta", "CAPM required return") and beta is None:
        warnings.append("Beta and CAPM are undefined because benchmark variance is zero.")
    elif benchmark_var is not None and math.sqrt(benchmark_var) <= 1e-12 * max(1.0, float(np.max(np.abs(benchmark_values)))):
        warnings.append("Benchmark variance is positive but very small; beta and CAPM estimates may be numerically sensitive.")
    if np.any(matrix == -1):
        warnings.append("A -100% return is a complete loss; its log return is undefined.")
    stats = []
    for i, name in enumerate(names):
        stats.append({"name": name, "mean": float(mean[i]), "variance": float(variance[i]),
                      "volatility": float(volatility[i]),
                      "sharpe": None if sharpe is None or not np.isfinite(sharpe[i]) else float(sharpe[i]),
                      "beta": None if beta is None else float(beta[i]),
                      "capm": None if capm is None else float(capm[i])})
    result = {"kind": kind, "option": option, "frequency": frequency, "dates": dates,
              "names": names, "returns": matrix.tolist(), "stats": stats,
              "covariance": covariance.tolist(),
              "correlation": [[None if not np.isfinite(x) else float(x) for x in line] for line in correlation],
              "risk_free_period": risk_free_period, "market_period": market_period,
              "risk_free_annual": risk_free, "market_annual": market_annual,
              "benchmark_variance": benchmark_var,
              "benchmark_mean": benchmark_mean,
              "benchmark_returns": None if benchmark_values is None else benchmark_values.tolist(),
              "benchmark_covariances": None if benchmark_covariances is None else benchmark_covariances.tolist(),
              "warnings": warnings, "optimization": None, "frontier": [],
              "optimization_covariance": None, "optimization_means": None,
              "weights": None, "cash_weight": None, "portfolio": None}
    if allocation is not None:
        w, cash = allocation
        portfolio_mean = float(math.fsum([*(float(w[i] * mean[i]) for i in range(len(names))), cash * cash_period]))
        portfolio_variance = float(w @ covariance @ w)
        if portfolio_variance < -1e-10 * scale:
            raise InputError("Weighted portfolio variance is invalid.")
        portfolio_variance = max(portfolio_variance, 0.0)
        portfolio_volatility = math.sqrt(portfolio_variance)
        portfolio_returns = [float(math.fsum([*(float(w[i] * matrix[j, i]) for i in range(len(names))), cash * cash_period]))
                             for j in range(len(dates))]
        if any(value < -1 - 1e-12 for value in portfolio_returns):
            raise InputError("A leveraged portfolio period return fell below -100%; inspect allocation and funding inputs.")
        portfolio_sharpe = None if risk_free_period is None or portfolio_volatility == 0 else (portfolio_mean - risk_free_period) / portfolio_volatility
        portfolio_beta = None if beta is None else float(w @ beta)
        portfolio_capm = None if portfolio_beta is None or market_period is None else risk_free_period + portfolio_beta * (market_period - risk_free_period)
        if portfolio_volatility == 0:
            warnings.append("Whole-portfolio Sharpe is undefined because portfolio volatility is zero.")
        elif portfolio_volatility <= sensitivity_floor:
            warnings.append("Whole-portfolio volatility is small but positive; risk ratios may be numerically sensitive.")
        result["weights"] = dict(zip(names, w.tolist()))
        result["cash_weight"] = cash
        result["portfolio"] = {"name": "Whole portfolio", "returns": portfolio_returns,
                               "mean": portfolio_mean, "variance": portfolio_variance,
                               "volatility": portfolio_volatility,
                               "sharpe": portfolio_sharpe, "beta": portfolio_beta,
                               "capm": portfolio_capm, "cash_period_return": cash_period,
                               "assumption": "Entered target weights are restored at the start of every period (constant-weight rebalancing)."}
    if kind == "Portfolio" and (option.startswith("Markowitz") or option == "Efficient frontier"):
        if len(names) < 2:
            raise InputError("Optimization needs at least two entered portfolios.")
        if financial_mode not in ("Standard", "Advanced"):
            raise InputError("Select Standard or Advanced financial controls.")
        assets = [{"id": name, "currency": "USD", "frequency": frequency,
                   "kind": "returns", "adjustment": "manually entered total portfolio returns",
                   "observations": [[day, float(matrix[j, i])] for j, day in enumerate(dates)]}
                  for i, name in enumerate(names)]
        analysis = analyze_portfolio(assets=assets, weights={name: 1/len(names) for name in names},
                                     currency="USD", frequency=frequency)
        if not analysis.ok:
            raise InputError(analysis.message)
        result["optimization_covariance"] = analysis.diagnostics["covariance"]
        result["optimization_means"] = analysis.diagnostics["expected_asset_returns"]
        result["warnings"].append("Optimization uses arithmetic historical means as expected-return estimates; these are not forward forecasts.")
        opts = {"mode": financial_mode, "allow_cash": False,
                "risk_free_annual_rate": risk_free}
        if financial_mode == "Advanced":
            if lower_bounds is None or upper_bounds is None or gross_cap is None or net_min is None or net_max is None:
                raise InputError("Advanced mode requires bounds and exposure limits.")
            opts.update(lower_bounds=lower_bounds, upper_bounds=upper_bounds,
                        gross_cap=gross_cap, net_min=net_min, net_max=net_max,
                        allow_short=allow_short)
        objective_map = {"Markowitz optimization — Minimum variance": "minimum_variance",
                         "Markowitz optimization — Maximum Sharpe ratio": "maximum_estimated_sharpe",
                         "Markowitz optimization — Target return": "target_return_minimum_variance"}
        if option == "Efficient frontier":
            low, high = float(np.min(mean)), float(np.max(mean))
            for target in np.linspace(low, high, 21):
                solved = optimize_portfolio(analysis, objective="target_return_minimum_variance",
                                            target_return=float(target), **opts)
                if solved.ok:
                    result["frontier"].append({"target": float(target),
                        "return": solved.diagnostics["expected_return"],
                        "volatility": solved.diagnostics["volatility"],
                        "weights": solved.diagnostics["weights"]})
            if not result["frontier"]:
                raise InputError("No feasible efficient-frontier points were found.")
        else:
            if option.endswith("Target return"):
                if target_return in (None, ""):
                    raise InputError("Enter a target return per selected period.")
                opts["target_return"] = _percent(target_return, "Target return")
            solved = optimize_portfolio(analysis, objective=objective_map[option], **opts)
            if not solved.ok:
                raise InputError(solved.message)
            result["optimization"] = solved.diagnostics
            result["warnings"].extend(solved.warnings)
    return result
