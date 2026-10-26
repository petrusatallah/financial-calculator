"""Readable numerical substitutions for the two manual-return result views.

These strings explain results; calculations always come from the shared service.
"""
from __future__ import annotations

import math


def number(value):
    """Keep small positive variances visible without rounding calculation data."""
    return format(float(value), ".15g")


def _sum(terms):
    return "\n  + ".join(terms)


def individual_steps(result, name):
    """Show entered returns and every intermediate step for one named series."""
    i = result["names"].index(name)
    stat = result["stats"][i]
    values = [row[i] for row in result["returns"]]
    mean = stat["mean"]
    n = len(values)
    lines = [f"{name} — decimal returns per {result['frequency'][:-2] if result['frequency'] == 'yearly' else 'month'}",
             "Entered returns: " + ", ".join(number(x) for x in values),
             f"Mean = (\n  {_sum([number(x) for x in values])}\n) / {n} = {number(mean)}",
             "Sample variance = (\n  " + _sum([f"({number(x)} − {number(mean)})²" for x in values])
             + f"\n) / ({n} − 1) = {number(stat['variance'])}",
             f"Volatility = √({number(stat['variance'])}) = {number(stat['volatility'])}"]
    option = result["option"]
    if option == "Sharpe ratio" or (option == "Portfolio statistics" and result["risk_free_period"] is not None) or (result["kind"] == "Investments" and result["risk_free_period"] is not None):
        rf = result["risk_free_period"]
        if result["risk_free_annual"] is not None:
            q = 12 if result["frequency"] == "monthly" else 1
            lines.append(f"Risk-free per period = (1 + {number(result['risk_free_annual'])})^(1/{q}) − 1 = {number(rf)}")
        lines.append(f"Sharpe = ({number(mean)} − {number(rf)}) / {number(stat['volatility'])} = "
                     + (number(stat["sharpe"]) if stat["sharpe"] is not None else "undefined (zero volatility)"))
    if option in ("Beta", "CAPM required return") or (result["kind"] == "Investments" and result["benchmark_returns"] is not None):
        benchmark = result["benchmark_returns"]
        benchmark_mean = result["benchmark_mean"]
        if benchmark is not None:
            lines.append("Benchmark returns: " + ", ".join(number(x) for x in benchmark))
            lines.append("Benchmark sample variance = (\n  "
                         + _sum([f"({number(x)} − {number(benchmark_mean)})²" for x in benchmark])
                         + f"\n) / ({n} − 1) = {number(result['benchmark_variance'])}")
        if stat["beta"] is None:
            lines.append("Beta is undefined because benchmark variance is exactly zero.")
        else:
            cov = result["benchmark_covariances"][i]
            lines.append("Asset/benchmark sample covariance = (\n  "
                         + _sum([f"({number(x)} − {number(mean)}) × ({number(y)} − {number(benchmark_mean)})"
                                 for x, y in zip(values, benchmark)])
                         + f"\n) / ({n} − 1) = {number(cov)}")
            lines.append(f"Beta = {number(cov)} / {number(result['benchmark_variance'])} = {number(stat['beta'])}")
    if option == "CAPM required return" or (result["kind"] == "Investments" and result["market_period"] is not None):
        q = 12 if result["frequency"] == "monthly" else 1
        if result["kind"] != "Investments":
            lines.append(f"Risk-free per period = (1 + {number(result['risk_free_annual'])})^(1/{q}) − 1 = {number(result['risk_free_period'])}")
        lines.append(f"Expected market per period = (1 + {number(result['market_annual'])})^(1/{q}) − 1 = {number(result['market_period'])}")
        if stat["capm"] is None:
            lines.append("CAPM required return is undefined because beta is undefined.")
        else:
            lines.append(f"CAPM = {number(result['risk_free_period'])} + {number(stat['beta'])} × "
                         f"({number(result['market_period'])} − {number(result['risk_free_period'])})"
                         f" = {number(stat['capm'])} per period")
    lines.append("Displayed numbers are rounded; calculations use full precision.")
    return "\n".join(lines)


def matrix_steps(result, first, second):
    """Expand one covariance/correlation cell using its aligned observations."""
    i, j = result["names"].index(first), result["names"].index(second)
    xs = [row[i] for row in result["returns"]]
    ys = [row[j] for row in result["returns"]]
    mx, my = result["stats"][i]["mean"], result["stats"][j]["mean"]
    vx, vy = result["stats"][i]["volatility"], result["stats"][j]["volatility"]
    cov, corr = result["covariance"][i][j], result["correlation"][i][j]
    n = len(xs)
    lines = [f"{first} and {second} — {n} aligned {result['frequency']} observations",
             "Sample covariance = (\n  "
             + _sum([f"({number(x)} − {number(mx)}) × ({number(y)} − {number(my)})"
                     for x, y in zip(xs, ys)])
             + f"\n) / ({n} − 1) = {number(cov)}",
             f"Correlation = {number(cov)} / ({number(vx)} × {number(vy)}) = "
             + (number(corr) if corr is not None else "undefined (zero volatility)"),
             "Displayed numbers are rounded; calculations use full precision."]
    return "\n".join(lines)


def portfolio_steps(result, solution):
    """Expand wᵀμ and wᵀΣw using the actual solver inputs and output weights."""
    names = result["names"]
    weights = [solution["weights"][name] for name in names]
    means_by_name = result.get("optimization_means") or {s["name"]: s["mean"] for s in result["stats"]}
    means = [means_by_name[name] for name in names]
    covariance = result.get("optimization_covariance") or result["covariance"]
    expected = solution.get("expected_return", solution.get("return"))
    variance = solution.get("variance", solution["volatility"] ** 2)
    lines = ["Portfolio allocation between entered portfolios",
             "Names: " + ", ".join(names),
             "w = [" + ", ".join(number(x) for x in weights) + "]",
             "μ = [" + ", ".join(number(x) for x in means) + "]",
             "Expected return = wᵀμ =\n  "
             + _sum([f"{number(w)} × {number(m)}" for w, m in zip(weights, means)])
             + f"\n  = {number(expected)} per period",
             "Σ (sample covariance, decimal return squared) ="]
    lines.extend("  [" + ", ".join(number(x) for x in row) + "]" for row in covariance)
    sigma_w = [math.fsum(covariance[i][j] * weights[j] for j in range(len(names))) for i in range(len(names))]
    lines.append("Σw = [" + ", ".join(number(x) for x in sigma_w) + "]")
    lines.append("Portfolio variance = wᵀΣw =\n  "
                 + _sum([f"{number(w)} × {number(x)}" for w, x in zip(weights, sigma_w)])
                 + f"\n  = {number(variance)}")
    lines.append(f"Portfolio volatility = √({number(variance)}) = {number(solution['volatility'])}")
    lines.append("Displayed numbers are rounded; calculations use full precision.")
    return "\n".join(lines)


def investments_portfolio_steps(result):
    """Numerical substitutions for the one portfolio of entered investments."""
    names, p = result["names"], result["portfolio"]
    weights = [result["weights"][name] for name in names]
    means = [s["mean"] for s in result["stats"]]
    covariance = result["covariance"]
    cash = result["cash_weight"]
    terms = [f"{number(w)} × {number(m)}" for w, m in zip(weights, means)]
    terms.append(f"{number(cash)} × {number(p['cash_period_return'])} (cash)")
    lines = ["Whole portfolio of individual investments", p["assumption"],
             "Investment weights = [" + ", ".join(number(x) for x in weights) + "]",
             f"Cash weight = {number(cash)}; cash return per period = {number(p['cash_period_return'])}",
             "Portfolio period returns:"]
    for day, row, actual in zip(result["dates"], result["returns"], p["returns"]):
        parts = [f"{number(w)} × {number(r)}" for w, r in zip(weights, row)]
        parts.append(f"{number(cash)} × {number(p['cash_period_return'])}")
        lines.append(f"  {day}: " + " + ".join(parts) + f" = {number(actual)}")
    lines += ["Portfolio expected return estimate = wᵀμ =\n  " + _sum(terms) + f"\n  = {number(p['mean'])}",
              "Investment Σ (sample covariance, decimal return squared) ="]
    lines.extend("  [" + ", ".join(number(x) for x in row) + "]" for row in covariance)
    sigma_w = [math.fsum(covariance[i][j] * weights[j] for j in range(len(names))) for i in range(len(names))]
    lines.append("Σw = [" + ", ".join(number(x) for x in sigma_w) + "]")
    lines.append("Portfolio sample variance = wᵀΣw =\n  "
                 + _sum([f"{number(w)} × {number(x)}" for w, x in zip(weights, sigma_w)])
                 + f"\n  = {number(p['variance'])}")
    lines.append(f"Portfolio volatility = √({number(p['variance'])}) = {number(p['volatility'])}")
    if result["risk_free_period"] is not None:
        lines.append(f"Portfolio Sharpe = ({number(p['mean'])} − {number(result['risk_free_period'])}) / {number(p['volatility'])} = "
                     + (number(p["sharpe"]) if p["sharpe"] is not None else "undefined (zero volatility)"))
    if result["benchmark_returns"] is not None:
        if p["beta"] is None:
            lines.append("Portfolio beta is undefined because benchmark variance is exactly zero.")
        else:
            cov = math.fsum(weights[i] * result["benchmark_covariances"][i] for i in range(len(names)))
            lines.append(f"Portfolio/benchmark covariance = " + " + ".join(
                f"{number(weights[i])} × {number(result['benchmark_covariances'][i])}" for i in range(len(names)))
                + f" = {number(cov)}")
            lines.append(f"Portfolio beta = {number(cov)} / {number(result['benchmark_variance'])} = {number(p['beta'])}")
    if result["market_period"] is not None:
        lines.append("Portfolio CAPM = " + (f"{number(result['risk_free_period'])} + {number(p['beta'])} × "
                     f"({number(result['market_period'])} − {number(result['risk_free_period'])}) = {number(p['capm'])}"
                     if p["capm"] is not None else "undefined (benchmark variance is zero)"))
    lines.append("Displayed numbers are rounded; calculations use full precision.")
    return "\n".join(lines)
