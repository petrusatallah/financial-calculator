"""S4 portfolio analytics under approved D08/D13 conventions.

REQ-PORT-01 through REQ-PORT-04. Inputs are manual or typed observations;
provider integration belongs to S5.
"""
from __future__ import annotations

from datetime import date
import math
import time

import numpy as np

from .result import CalculationResult, Status
from .validation import InputError, UnsupportedInput, parse_currency, parse_number

PER_YEAR = {"daily": 252, "weekly": 52, "monthly": 12, "quarterly": 4, "yearly": 1}


class Incomplete(InputError):
    pass


def _profile(mode, asset_count, row_count, started, *, aligned=True):
    if mode not in {"Standard", "Advanced"}:
        raise InputError("Mode must be Standard or Advanced.")
    max_assets, max_rows, seconds, memory = (50, 5000, 10, 256) if mode == "Standard" else (200, 20000, 30, 512)
    if asset_count > max_assets or aligned and row_count > max_rows:
        raise UnsupportedInput(f"{mode} supports at most {max_assets} assets and {max_rows} aligned rows.")
    if row_count * asset_count * 32 + asset_count * asset_count * 64 > memory * 1024 * 1024:
        raise Incomplete(f"{mode} exceeds its estimated {memory} MiB working-memory limit.")
    if time.monotonic() - started > seconds:
        raise Incomplete(f"{mode} exceeded its {seconds}-second limit.")


def _failure(exc):
    status = Status.INCOMPLETE if isinstance(exc, Incomplete) else Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.INVALID
    return CalculationResult(status, None, "portfolio", message=str(exc))


def _observations(asset, frequency, currency):
    if not isinstance(asset, dict):
        raise InputError("Each asset must be a typed record.")
    identity = asset.get("id")
    if not isinstance(identity, str) or not identity.strip() or len(identity) > 128:
        raise InputError("Each asset needs a short, nonblank identity.")
    if parse_currency(asset.get("currency")) != currency:
        raise UnsupportedInput("All assets must have the same declared currency.")
    if asset.get("frequency") != frequency:
        raise UnsupportedInput("All assets must have the same declared observation frequency.")
    kind = asset.get("kind")
    if kind not in {"returns", "price", "total"}:
        raise InputError("Asset kind must be returns, price or total.")
    adjustment = asset.get("adjustment")
    if not isinstance(adjustment, str) or not adjustment.strip():
        raise InputError("Declare the price or return adjustment basis.")
    observations = asset.get("observations")
    if not isinstance(observations, (list, tuple)) or len(observations) < (1 if kind == "returns" else 2):
        raise InputError("Enter dated observations for each asset.")
    seen = set()
    parsed = []
    for row in observations:
        if not isinstance(row, (list, tuple)) or len(row) != (3 if kind == "total" else 2):
            raise InputError("Observation fields must match the declared kind.")
        try:
            when = date.fromisoformat(str(row[0])).isoformat()
        except ValueError as exc:
            raise InputError("Observation dates must be ISO YYYY-MM-DD.") from exc
        if when in seen:
            raise InputError("Duplicate observation dates are not allowed.")
        seen.add(when)
        raw = row[1]
        if raw is None or isinstance(raw, str) and not raw.strip():
            parsed.append((when, None, None))
            continue
        value = parse_number(raw, "Observation")
        distribution = parse_number(row[2], "Distribution") if kind == "total" else 0.0
        if kind != "returns" and value <= 0:
            raise InputError("Prices must be positive.")
        if kind == "returns" and value < -1:
            raise InputError("Unlevered simple returns cannot be below -100%.")
        parsed.append((when, value, distribution))
    if [row[0] for row in parsed] != sorted(seen):
        raise InputError("Observation dates must be increasing.")
    returns, prices = {}, {}
    previous = None
    for when, value, distribution in parsed:
        if kind == "returns":
            if value is not None:
                returns[when] = value
        elif value is not None:
            prices[when] = value
            if previous is not None and distribution is not None:
                returns[when] = (value + distribution) / previous - 1
            previous = value
        else:
            previous = None  # never bridge a missing price
    return identity.strip(), returns, prices, kind, adjustment


def _covariance(matrix):
    covariance = np.cov(matrix, rowvar=False, ddof=1)
    covariance = np.atleast_2d(covariance)
    # A column of exactly identical observations has mathematically zero
    # variance. np.cov can leave a round-off residue after mean subtraction.
    constant = np.all(matrix == matrix[0:1, :], axis=0)
    covariance[constant, :] = 0.0
    covariance[:, constant] = 0.0
    scale = max(float(np.max(np.abs(covariance))), 1e-15)
    if not np.all(np.isfinite(covariance)) or np.max(np.abs(covariance-covariance.T)) > 1e-10*scale:
        raise InputError("Covariance matrix is not finite and symmetric.")
    eigenvalues = np.linalg.eigvalsh(covariance)
    if eigenvalues[0] < -1e-10*scale:
        raise InputError("Covariance matrix is not positive semidefinite.")
    return covariance, float(eigenvalues[0]), float(eigenvalues[-1]), scale


def analyze_portfolio(*, assets, weights, currency, frequency, mode="Standard", cash_weight=0,
                      cash_annual_yield=None, funding_annual_rate=None, risk_free_annual_rate=None, benchmark=None,
                      market_expected_annual_return=None, expected_returns=None, execution_profile=None):
    """Calculate aligned asset and portfolio statistics; all rates are decimals."""
    started = time.monotonic()
    try:
        currency = parse_currency(currency)
        resource_mode = execution_profile or mode
        if mode not in {"Standard", "Advanced"}:
            raise InputError("Invalid financial controls mode.")
        if frequency not in PER_YEAR:
            raise InputError("Frequency must be daily, weekly, monthly, quarterly or yearly.")
        if not isinstance(assets, (list, tuple)) or not assets:
            raise InputError("At least one asset is required.")
        _profile(resource_mode, len(assets), max(len(a.get("observations", [])) for a in assets if isinstance(a, dict)), started, aligned=False)
        records = [_observations(asset, frequency, currency) for asset in assets]
        ids = [record[0] for record in records]
        if len(set(ids)) != len(ids):
            raise InputError("Asset identities must be unique.")
        if not isinstance(weights, dict) or set(weights) != set(ids):
            raise InputError("Weights must map exactly to the identified assets.")
        w = np.array([parse_number(weights[identity], f"Weight {identity}") for identity in ids])
        cash = parse_number(cash_weight, "Cash weight")
        if abs(float(sum(w)+cash-1)) > 1e-7:
            raise InputError("Asset and cash weights must sum to one.")
        if mode == "Standard" and (np.min(w) < -1e-7 or cash < -1e-7):
            raise InputError("Standard weights and cash must be nonnegative.")
        if cash > 0 and cash_annual_yield is None:
            raise InputError("A cash position requires an explicit annual effective cash yield.")
        cash_annual = 0 if cash_annual_yield is None else parse_number(cash_annual_yield, "Cash annual yield")
        if cash_annual <= -1:
            raise InputError("Cash annual effective yield must exceed -100%.")
        rf_annual = None if risk_free_annual_rate is None else parse_number(risk_free_annual_rate, "Risk-free annual rate")
        if rf_annual is not None and rf_annual <= -1:
            raise InputError("Risk-free annual effective rate must exceed -100%.")
        q = PER_YEAR[frequency]
        if cash < 0 and funding_annual_rate is None:
            raise InputError("Negative cash requires an explicit annual effective funding rate.")
        funding_annual = None if funding_annual_rate is None else parse_number(funding_annual_rate, "Annual funding rate")
        if funding_annual is not None and funding_annual <= -1:
            raise InputError("Annual effective funding rate must exceed -100%.")
        cash_period = (1+(funding_annual if cash < 0 else cash_annual))**(1/q)-1
        rf_period = None if rf_annual is None else (1+rf_annual)**(1/q)-1
        common = set.intersection(*(set(record[1]) for record in records))
        market = None
        if benchmark is not None:
            market = _observations(benchmark, frequency, currency)
            if market[0] in ids:
                raise InputError("Benchmark identity must differ from portfolio assets.")
            common &= set(market[1])
        dates = sorted(common)
        _profile(resource_mode, len(assets), len(dates), started)
        if len(dates) < 2:
            raise InputError("At least two aligned complete return observations are required.")
        R = np.array([[record[1][day] for record in records] for day in dates], dtype=float)
        covariance, min_eigen, max_eigen, scale = _covariance(R)
        means = np.mean(R, axis=0)
        if expected_returns is not None:
            if not isinstance(expected_returns, dict) or set(expected_returns) != set(ids):
                raise InputError("Expected returns must map exactly to the asset identities.")
            mu = np.array([parse_number(expected_returns[identity], f"Expected return {identity}") for identity in ids])
        else:
            mu = means
        historical = R @ w + cash*cash_period
        estimated = float(mu @ w + cash*cash_period)
        var = float(w @ covariance @ w)
        if var < -1e-10*scale:
            raise InputError("Portfolio variance is invalid.")
        var = max(var, 0.0)
        risk_floor = 1e-12 * max(1.0, float(np.max(np.abs(R))), abs(cash_period))
        volatility = math.sqrt(var)
        std = np.sqrt(np.maximum(np.diag(covariance), 0))
        correlations = np.divide(covariance, np.outer(std, std), out=np.full_like(covariance, np.nan), where=np.outer(std,std)>0)
        compounded = float(np.prod(1+historical)-1)
        if np.any(historical < -1):
            raise InputError("Portfolio simple return fell below -100%; inspect leverage assumptions.")
        geometric = float(np.prod(1+historical)**(1/len(historical))-1)
        cum_path = np.cumprod(1+historical)-1
        market_values = None
        beta = capm = None
        if market is not None:
            market_values = np.array([market[1][day] for day in dates])
            market_variance = 0.0 if np.all(market_values == market_values[0]) else float(np.var(market_values, ddof=1))
            market_floor = 1e-12 * max(1.0, float(np.max(np.abs(market_values))))
            if market_variance > 0:
                beta = float(np.cov(historical, market_values, ddof=1)[0,1]/market_variance)
                if rf_period is not None and market_expected_annual_return is not None:
                    market_annual = parse_number(market_expected_annual_return, "Expected market annual return")
                    if market_annual <= -1:
                        raise InputError("Expected market annual return must exceed -100%.")
                    market_period = (1+market_annual)**(1/q)-1
                    capm = rf_period+beta*(market_period-rf_period)
        sharpe = None if rf_period is None or volatility <= 0 else (estimated-rf_period)/volatility
        warnings = ["Annualized volatility uses square-root-of-time scaling and assumes sufficiently regular returns."]
        if min_eigen <= 1e-10*scale:
            warnings.append("Covariance is singular or nearly singular; optimized weights may be nonunique or unstable.")
        if np.any(std == 0):
            warnings.append("Correlation is undefined for any zero-volatility asset.")
        if 0 < volatility <= risk_floor or np.any((std > 0) & (std <= risk_floor)):
            warnings.append("Some positive variances are numerically sensitive; the displayed nonzero values should be interpreted cautiously.")
        if benchmark is not None and beta is None:
            warnings.append("Beta and CAPM are undefined because benchmark variance is zero.")
        elif benchmark is not None and 0 < market_variance <= market_floor**2:
            warnings.append("Benchmark variance is positive but numerically sensitive; beta and CAPM may be unreliable.")
        if rf_period is not None and sharpe is None:
            warnings.append("Sharpe is undefined because portfolio volatility is zero.")
        diagnostics = {
            "assets": ids, "currency": currency, "frequency": frequency, "dates": dates,
            "return_basis": {record[0]: {"kind": record[3], "adjustment": record[4]} for record in records},
            "return_series": {identity: R[:, index].tolist() for index, identity in enumerate(ids)},
            "price_series": {record[0]: record[2] for record in records},
            "portfolio_returns": historical.tolist(), "cumulative_path": cum_path.tolist(), "portfolio_log_returns": [None if x <= -1 else float(math.log1p(x)) for x in historical],
            "arithmetic_mean": float(np.mean(historical)), "geometric_mean": geometric,
            "cumulative_return": compounded, "annualized_geometric_return": (1+geometric)**q-1,
            "variance": var, "volatility": volatility, "annualized_volatility": volatility*math.sqrt(q), "diversification_benefit": float(np.abs(w)@std-volatility),
            "asset_means": dict(zip(ids, means.tolist())), "asset_cumulative_returns": {identity: float(np.prod(1+R[:,i])-1) for i,identity in enumerate(ids)}, "asset_annualized_returns": {identity: float(np.prod(1+R[:,i])**(q/len(dates))-1) for i,identity in enumerate(ids)}, "asset_log_returns": {identity: [None if x <= -1 else float(math.log1p(x)) for x in R[:,i]] for i,identity in enumerate(ids)}, "asset_geometric_means": {identity: float(np.prod(1+R[:,i])**(1/len(dates))-1) for i,identity in enumerate(ids)},
            "expected_asset_returns": dict(zip(ids, mu.tolist())), "expected_portfolio_return": estimated,
            "covariance": covariance.tolist(), "correlation": [[None if not math.isfinite(x) else float(x) for x in row] for row in correlations],
            "asset_volatility": dict(zip(ids,std.tolist())), "weights": dict(zip(ids,w.tolist())),
            "cash_weight": cash, "cash_yield_declared": cash_annual_yield is not None, "funding_rate_declared": funding_annual_rate is not None, "cash_period_return": cash_period, "risk_free_period_return": rf_period,
            "beta": beta, "capm_expected_period_return": capm, "sharpe_period": sharpe,
            "benchmark_returns": None if market_values is None else market_values.tolist(),
            "dropped_rows": sorted(set.union(*(set(record[1]) for record in records))-set(dates)),
            "sample_count": len(dates), "covariance_min_eigenvalue": min_eigen,
        }
        _profile(resource_mode, len(assets), len(dates), started)
        return CalculationResult(Status.VALID, estimated, "decimal return per period", warnings=tuple(warnings),
            assumptions={"portfolio_return": "beginning-of-period target weights, rebalanced each period", "covariance": "sample n-1 on listwise complete dates", "annualization_periods": q, "currency": currency}, diagnostics=diagnostics)
    except (InputError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        return _failure(exc)


def analyze_optimization_inputs(*, names, frequency, expected_returns=None, covariance=None,
                                dates=None, returns=None, current_weights=None,
                                risk_free_annual_rate=None, mode="Standard"):
    """Validate period-matched historical or estimate inputs for the shared optimizer.

    Values at this boundary are decimal simple returns and decimal-return-squared
    covariance. A summary-only input never acquires fabricated observations.
    """
    try:
        if frequency not in ("monthly", "yearly") or mode not in ("Standard", "Advanced"):
            raise InputError("Select monthly or yearly frequency and a valid controls mode.")
        if not isinstance(names, (list, tuple)) or len(names) < 2 or len(names) > (50 if mode == "Standard" else 200):
            raise InputError("Enter between 2 and the mode's maximum number of investments.")
        names = [str(name).strip() for name in names]
        if any(not name or len(name) > 128 for name in names) or len(set(names)) != len(names):
            raise InputError("Investment names must be nonblank and unique.")
        observed = returns is not None
        if observed:
            if not isinstance(dates, (list, tuple)) or not isinstance(returns, (list, tuple)) or len(dates) != len(returns) or len(dates) < 2:
                raise InputError("At least two complete dated return rows are required.")
            parsed_dates = [date.fromisoformat(str(day)).isoformat() for day in dates]
            if parsed_dates != sorted(set(parsed_dates)):
                raise InputError("Dates must be unique and increasing.")
            if len(parsed_dates) > (5000 if mode == "Standard" else 20000):
                raise UnsupportedInput("Too many return rows for the selected execution mode.")
            matrix = np.asarray(returns, dtype=float)
            if matrix.shape != (len(dates), len(names)) or not np.all(np.isfinite(matrix)) or np.any(matrix < -1):
                raise InputError("Return rows must be complete, finite, and at least -100%.")
            sigma, eig_min, eig_max, scale = _covariance(matrix)
            mu = np.mean(matrix, axis=0)
            if expected_returns is not None or covariance is not None:
                raise InputError("Do not mix historical observations with separate estimate inputs.")
        else:
            parsed_dates = []
            matrix = None
            if not isinstance(expected_returns, dict) or set(expected_returns) != set(names):
                raise InputError("Expected returns must match every investment name.")
            mu = np.asarray([float(expected_returns[name]) for name in names], dtype=float)
            sigma = np.asarray(covariance, dtype=float)
            if sigma.shape != (len(names), len(names)) or not np.all(np.isfinite(sigma)) or not np.all(np.isfinite(mu)):
                raise InputError("Expected returns and covariance must be finite and dimensionally aligned.")
            scale = max(float(np.max(np.abs(sigma))), 1e-15)
            if np.max(np.abs(sigma-sigma.T)) > 1e-10*scale:
                raise InputError("Covariance must be symmetric.")
            if np.min(np.diag(sigma)) < -1e-10*scale:
                raise InputError("Covariance diagonal contains a negative variance.")
            eigenvalues = np.linalg.eigvalsh(sigma)
            eig_min, eig_max = float(eigenvalues[0]), float(eigenvalues[-1])
            if eig_min < -1e-10*scale:
                raise InputError("Covariance must be positive semidefinite.")
        weights = None
        if current_weights is not None:
            if not isinstance(current_weights, dict) or set(current_weights) != set(names):
                raise InputError("Current weights must match every investment name.")
            weights = {name: float(current_weights[name]) for name in names}
            if not all(math.isfinite(value) for value in weights.values()) or abs(sum(weights.values())-1) > 1e-7:
                raise InputError("Current weights must be finite and total 100%.")
            if mode == "Standard" and any(value < -1e-10 for value in weights.values()):
                raise InputError("Standard current weights cannot be negative.")
        rf = None
        if risk_free_annual_rate is not None:
            annual = float(risk_free_annual_rate)
            if not math.isfinite(annual) or annual <= -1:
                raise InputError("Annual effective risk-free rate must exceed -100%.")
            rf = (1+annual)**(1/PER_YEAR[frequency])-1
        std = np.sqrt(np.maximum(np.diag(sigma), 0))
        denom = np.outer(std, std)
        correlation = np.divide(sigma, denom, out=np.full_like(sigma, np.nan), where=denom>0)
        warnings = []
        if eig_min <= 1e-10*scale:
            warnings.append("Covariance is singular or nearly singular; optimized weights may be unstable.")
        elif eig_max > 0 and eig_min / eig_max < 1e-6:
            warnings.append("Covariance is ill-conditioned (eigenvalue ratio below 0.000001); small estimate changes may substantially change optimized weights.")
        if observed and len(parsed_dates) < 3:
            warnings.append("Only two observations: risk and optimized weights are highly uncertain.")
        elif observed and len(parsed_dates) <= len(names):
            warnings.append("The number of observations is no greater than the number of investments; sample covariance is rank-deficient and optimized weights may be unstable.")
        if not observed:
            warnings.append("Expected returns and covariance are estimates; no historical observations were supplied.")
        d = {"assets": names, "frequency": frequency, "sample_count": len(parsed_dates),
             "dates": parsed_dates, "source": "historical" if observed else "estimates",
             "expected_asset_returns": dict(zip(names, mu.tolist())), "covariance": sigma.tolist(),
             "correlation": [[float(x) if math.isfinite(x) else None for x in row] for row in correlation],
             "asset_volatility": dict(zip(names, std.tolist())), "asset_variance": dict(zip(names, np.diag(sigma).tolist())),
             "current_weights": weights, "risk_free_period_return": rf,
             "cash_period_return": 0.0, "cash_yield_declared": False,
             "covariance_min_eigenvalue": eig_min}
        if observed:
            d["return_series"] = {name: matrix[:, i].tolist() for i, name in enumerate(names)}
        return CalculationResult(Status.VALID, None, "portfolio input", warnings=tuple(warnings),
                                 assumptions={"covariance": "sample n-1" if observed else "entered decimal return squared"}, diagnostics=d)
    except (InputError, UnsupportedInput, TypeError, ValueError, OverflowError) as exc:
        return _failure(exc)


def compare_return_histories(*, names, dates, returns, frequency, risk_free_annual_rate=None):
    """Compare complete portfolio return series on common dates (decimal inputs)."""
    analysis = analyze_optimization_inputs(names=names, dates=dates, returns=returns,
                                           frequency=frequency, risk_free_annual_rate=risk_free_annual_rate)
    if not analysis.ok:
        return analysis
    d = analysis.diagnostics
    matrix = np.asarray(returns, dtype=float)
    rows = []
    for i, name in enumerate(names):
        series = matrix[:, i]
        variance = float(d["covariance"][i][i])
        volatility = math.sqrt(max(variance, 0))
        rows.append({"name": name, "mean": float(np.mean(series)),
                     "cumulative": float(np.prod(1+series)-1), "variance": variance,
                     "volatility": volatility,
                     "sharpe": None if d["risk_free_period_return"] is None or volatility == 0 else
                         float((np.mean(series)-d["risk_free_period_return"])/volatility),
                     "path": (np.cumprod(1+series)-1).tolist()})
    warnings = list(analysis.warnings)
    if d["risk_free_period_return"] is None:
        warnings.append("Sharpe ratio requires an annual effective risk-free rate.")
    return CalculationResult(Status.VALID, None, "portfolio comparison", warnings=tuple(warnings),
                             assumptions={"returns": "simple percentages on common dates",
                                          "covariance": "sample n-1"},
                             diagnostics={**d, "comparison": rows})
