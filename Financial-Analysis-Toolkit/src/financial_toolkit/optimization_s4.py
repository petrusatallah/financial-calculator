"""S4 constrained portfolio optimization under approved D09/D13 rules.

REQ-OPT-01/02. Solver outputs are independently checked against every constraint.
"""
from __future__ import annotations

import math
import time

import numpy as np
from scipy.optimize import minimize, linprog

from .portfolio_s4 import PER_YEAR, _covariance
from .result import CalculationResult, Status
from .validation import InputError, UnsupportedInput, parse_number


class Incomplete(InputError):
    pass


def _failure(exc):
    status = Status.INCOMPLETE if isinstance(exc, Incomplete) else Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.INVALID
    return CalculationResult(status, None, "portfolio weights", message=str(exc))


def _group_rows(ids, group_constraints):
    rows = {}
    if group_constraints is None:
        return rows
    if not isinstance(group_constraints, (list, tuple)):
        raise InputError("Custom groups must be a list.")
    for group in group_constraints:
        if not isinstance(group, dict):
            raise InputError("Each custom group needs a name, investments and limits.")
        name = str(group.get("name", "")).strip()
        members = group.get("investments")
        if not name or name in rows:
            raise InputError("Custom group names must be nonblank and unique.")
        if not isinstance(members, (list, tuple)) or len(members) < 2 or len(set(members)) != len(members) or not set(members).issubset(ids):
            raise InputError(f"Group {name} needs at least two distinct existing investments.")
        maximum = parse_number(group.get("maximum"), f"Group {name} maximum")
        minimum = None if group.get("minimum") is None else parse_number(group["minimum"], f"Group {name} minimum")
        if minimum is not None and minimum > maximum:
            raise InputError(f"Group {name} minimum exceeds its maximum.")
        vector = np.array([1.0 if identity in members else 0.0 for identity in ids])
        rows[name] = (vector, minimum, maximum)
    return rows


def _linear_feasible(lower, upper, gross, net_lo, net_hi, limit_rows, *,
                     allow_cash=False, funding=None, cash_yield=0.0, target=None, mu=None, check_clock=None):
    """Certify all linear limits together; auxiliary variables model |weight|."""
    n = len(lower)
    base_rows, base_limits = [], []
    for i in range(n):
        positive = np.zeros(2*n); positive[i] = 1; positive[n+i] = -1
        negative = np.zeros(2*n); negative[i] = -1; negative[n+i] = -1
        base_rows.extend((positive, negative)); base_limits.extend((0.0, 0.0))
    base_rows.append(np.r_[np.zeros(n), np.ones(n)]); base_limits.append(gross)
    regions = [(net_lo, min(net_hi, 1.0), cash_yield)]
    if allow_cash and funding is not None:
        regions.append((max(net_lo, 1.0), net_hi, funding))
    feasible = []
    for region_lo, region_hi, rate in regions:
        if region_lo > region_hi+1e-10:
            continue
        rows, limits = list(base_rows), list(base_limits)
        rows.extend((np.r_[np.ones(n), np.zeros(n)], np.r_[-np.ones(n), np.zeros(n)]))
        limits.extend((region_hi, -region_lo))
        for vector, minimum, maximum in limit_rows.values():
            rows.append(np.r_[vector, np.zeros(n)]); limits.append(maximum)
            if minimum is not None:
                rows.append(np.r_[-vector, np.zeros(n)]); limits.append(-minimum)
        if target is not None:
            rows.append(np.r_[rate-mu, np.zeros(n)]); limits.append(rate-target)
        solution = linprog(np.zeros(2*n), A_ub=np.asarray(rows), b_ub=np.asarray(limits),
                           bounds=list(zip(lower, upper))+[(0, None)]*n, method="highs")
        if check_clock is not None:
            check_clock()
        if solution.success:
            feasible.append(solution.x[:n])
    return feasible


def validate_portfolio_constraints(names, *, lower_bounds, upper_bounds, group_constraints=None,
                                   allow_short=False, gross_cap=1.0, net_min=1.0, net_max=1.0,
                                   allow_cash=False, funding_annual_rate=None):
    """Preflight the same bounds, group and exposure polytope used by the optimizer."""
    try:
        ids = list(names)
        if len(ids) < 2 or len(set(ids)) != len(ids):
            raise InputError("Enter at least two distinct investments.")
        if set(lower_bounds) != set(ids) or set(upper_bounds) != set(ids):
            raise InputError("Bounds must cover every investment.")
        lower = np.array([parse_number(lower_bounds[name], f"Minimum {name}") for name in ids])
        upper = np.array([parse_number(upper_bounds[name], f"Maximum {name}") for name in ids])
        if np.any(lower > upper):
            raise InputError("Each investment minimum must be at or below its maximum.")
        if not allow_short and np.any(lower < 0):
            raise InputError("Negative minimum weights require short selling.")
        gross = parse_number(gross_cap, "Gross exposure cap")
        net_lo = parse_number(net_min, "Minimum net risky exposure")
        net_hi = parse_number(net_max, "Maximum net risky exposure")
        if gross < 0 or net_lo > net_hi:
            raise InputError("Gross and net exposure limits are inconsistent.")
        if not allow_cash and (abs(net_lo-1) > 1e-10 or abs(net_hi-1) > 1e-10):
            raise InputError("Without cash or funding, net risky weights must total 100%.")
        if allow_cash and net_hi > 1+1e-10 and funding_annual_rate is None:
            raise InputError("Borrowing above 100% risky exposure requires a funding rate.")
        if sum(lower) > net_hi+1e-9:
            raise UnsupportedInput("Investment minimum weights exceed the allowed allocation.")
        if sum(upper) < net_lo-1e-9:
            raise UnsupportedInput("Investment maximum weights cannot reach the required allocation.")
        groups = _group_rows(ids, group_constraints)
        funding = 0.0 if funding_annual_rate is not None else None
        if not _linear_feasible(lower, upper, gross, net_lo, net_hi, groups,
                                allow_cash=allow_cash, funding=funding):
            names_text = ", ".join(groups) if groups else "investment bounds and exposure limits"
            raise UnsupportedInput(f"These limits are jointly infeasible: {names_text}. Check overlapping groups, bounds and exposure caps.")
        return CalculationResult(Status.VALID, True, "constraint feasibility",
                                 diagnostics={"net_allocation": 1.0 if not allow_cash else None,
                                              "groups": tuple(groups)})
    except (InputError, TypeError, ValueError) as exc:
        return _failure(exc)


def optimize_portfolio(analysis, *, objective, mode="Standard", target_return=None,
                       allow_cash=False, lower_bounds=None, upper_bounds=None,
                       allow_short=False, gross_cap=None, net_min=None, net_max=None,
                       cash_annual_yield=None, funding_annual_rate=None,
                       risk_free_annual_rate=None, sector_assignments=None, sector_caps=None,
                       group_constraints=None,
                       cancel=None, execution_profile=None):
    """Optimize one validated S4 analysis with expected simple returns per period."""
    started = time.monotonic()
    try:
        if not isinstance(analysis, CalculationResult) or not analysis.ok:
            raise InputError("A valid portfolio analysis is required before optimization.")
        if objective not in {"minimum_variance", "maximum_estimated_sharpe", "target_return_minimum_variance", "maximum_expected_return"}:
            raise InputError("Select an approved optimization objective.")
        if mode not in {"Standard", "Advanced"}:
            raise InputError("Mode must be Standard or Advanced.")
        resource_mode = execution_profile or mode
        if resource_mode not in {"Standard", "Advanced"}:
            raise InputError("Invalid execution profile.")
        d = analysis.diagnostics
        ids = d["assets"]
        n = len(ids)
        asset_cap, row_cap, seconds, iterations, memory = (50, 5000, 10, 2000, 256) if resource_mode == "Standard" else (200, 20000, 30, 10000, 512)
        if n > asset_cap or d["sample_count"] > row_cap:
            raise UnsupportedInput("Analysis exceeds the optimizer profile limit.")
        if d["sample_count"]*n*32+n*n*64 > memory*1024*1024:
            raise Incomplete("Estimated optimizer working memory exceeds the approved limit.")
        mu = np.array([d["expected_asset_returns"][identity] for identity in ids], dtype=float)
        sigma = np.array(d["covariance"], dtype=float)
        if sigma.shape != (n, n) or not np.all(np.isfinite(sigma)):
            raise InputError("Analysis covariance is invalid.")
        scale = max(float(np.max(np.abs(sigma))), 1e-15)
        eig_min, eig_max = float(np.linalg.eigvalsh(sigma)[0]), float(np.linalg.eigvalsh(sigma)[-1])
        if np.max(np.abs(sigma-sigma.T)) > 1e-10*scale or eig_min < -1e-10*scale:
            raise InputError("Analysis covariance is invalid.")
        if "return_series" in d:
            recomputed, _, _, _ = _covariance(np.array([d["return_series"][identity] for identity in ids]).T)
            if np.max(np.abs(sigma-recomputed)) > 1e-8+1e-8*scale:
                raise InputError("Analysis covariance does not match its return observations.")
        elif d.get("source") != "estimates":
            raise InputError("Optimization requires validated historical observations or validated estimate inputs.")
        q = PER_YEAR[d["frequency"]]
        yield_annual = d["cash_period_return"] if cash_annual_yield is None else parse_number(cash_annual_yield, "Annual cash yield")
        if cash_annual_yield is None:
            cash_yield = d["cash_period_return"]
        else:
            if yield_annual <= -1:
                raise InputError("Annual cash yield must exceed -100%.")
            cash_yield = (1+yield_annual)**(1/q)-1
        funding = None
        if funding_annual_rate is not None:
            rate = parse_number(funding_annual_rate, "Annual funding rate")
            if rate <= -1:
                raise InputError("Annual funding rate must exceed -100%.")
            funding = (1+rate)**(1/q)-1
        if risk_free_annual_rate is None:
            rf = d["risk_free_period_return"]
        else:
            annual_rf = parse_number(risk_free_annual_rate, "Risk-free annual rate")
            if annual_rf <= -1:
                raise InputError("Risk-free annual effective rate must exceed -100%.")
            rf = (1+annual_rf)**(1/q)-1
        if rf is not None and not math.isfinite(rf):
            raise InputError("Risk-free rate is invalid.")
        if objective == "maximum_estimated_sharpe" and rf is None:
            raise InputError("Maximum estimated Sharpe requires an explicit risk-free rate.")
        target = None if target_return is None else parse_number(target_return, "Target return per period")
        if objective == "target_return_minimum_variance" and target is None:
            raise InputError("Target-return optimization requires a target floor.")
        if allow_cash and cash_annual_yield is None and not d.get('cash_yield_declared', False):
            raise InputError('Allowing cash requires an explicit annual effective cash yield.')
        if mode == "Standard":
            if any(value is not None for value in (lower_bounds, upper_bounds, gross_cap, net_min, net_max, funding_annual_rate)) or allow_short:
                raise UnsupportedInput("Advanced bounds, shorts and financing require Advanced mode.")
            lower = np.zeros(n)
            upper = np.ones(n)
            net_lo, net_hi, gross = (0.0 if allow_cash else 1.0), 1.0, 1.0
        else:
            if lower_bounds is None or upper_bounds is None or gross_cap is None or net_min is None or net_max is None:
                raise InputError("Advanced optimization requires bounds, gross cap and net exposure range.")
            if set(lower_bounds) != set(ids) or set(upper_bounds) != set(ids):
                raise InputError("Bounds must map exactly to asset identities.")
            lower = np.array([parse_number(lower_bounds[identity], f"Lower {identity}") for identity in ids])
            upper = np.array([parse_number(upper_bounds[identity], f"Upper {identity}") for identity in ids])
            if np.any(lower > upper):
                raise InputError("Asset lower bounds exceed upper bounds.")
            if not allow_short and np.any(lower < 0):
                raise InputError("Negative lower bounds require short selling to be enabled.")
            net_lo = parse_number(net_min, "Minimum net risky exposure")
            net_hi = parse_number(net_max, "Maximum net risky exposure")
            gross = parse_number(gross_cap, "Gross risky exposure cap")
            if net_lo > net_hi or gross < 0 or gross + 1e-7 < max(abs(net_lo),abs(net_hi)) and net_lo == net_hi:
                raise InputError("Exposure limits are inconsistent.")
            if allow_cash and net_hi > 1+1e-7 and funding is None:
                raise InputError("Potential negative cash requires an explicit funding rate.")
            if not allow_cash:
                if abs(net_lo-1.0) > 1e-10 or abs(net_hi-1.0) > 1e-10:
                    raise InputError("Without cash or funding, net risky weights must total 100%.")
                net_lo = net_hi = 1.0
            elif funding is None:
                net_hi = min(net_hi, 1.0)
        if np.sum(lower) > net_hi+1e-7 or np.sum(upper) < net_lo-1e-7:
            raise UnsupportedInput("Weight bounds cannot satisfy the net exposure limits.")
        sector_rows = {}
        if sector_assignments is not None or sector_caps is not None:
            if not isinstance(sector_assignments, dict) or set(sector_assignments) != set(ids):
                raise InputError("Every investment needs exactly one sector assignment.")
            if not isinstance(sector_caps, dict) or not sector_caps:
                raise InputError("Enter at least one sector limit.")
            sectors = {identity: str(sector_assignments[identity]).strip() for identity in ids}
            if any(not sector for sector in sectors.values()) or not set(sector_caps).issubset(set(sectors.values())):
                raise InputError("Sector limits must refer to assigned sectors.")
            for sector, raw_cap in sector_caps.items():
                cap = parse_number(raw_cap, f"Sector cap {sector}")
                if cap < 0:
                    raise InputError("Sector caps must be nonnegative.")
                sector_rows[sector] = (np.array([1.0 if sectors[identity] == sector else 0.0 for identity in ids]), cap)
        group_rows = _group_rows(ids, group_constraints)
        limit_rows = {f"sector:{name}": (vector, None, cap) for name, (vector, cap) in sector_rows.items()}
        limit_rows.update({f"group:{name}": row for name, row in group_rows.items()})
        if target is not None and objective != "target_return_minimum_variance":
            raise InputError("A target applies only to target-return minimum variance.")
        def check_clock():
            if callable(cancel) and cancel():
                raise Incomplete("Optimization was cancelled.")
            if time.monotonic()-started > seconds:
                raise Incomplete(f"{mode} optimization exceeded {seconds} seconds.")
        def expected(w):
            cash = 1-float(sum(w))
            if abs(cash) <= 1e-10:
                cash = 0.0
            return float(mu @ w + cash*(cash_yield if cash >= 0 or funding is None else funding))
        def variance(w):
            return max(float(w @ sigma @ w),0.0)
        sharpe_floor = 1e-12 * max(1.0, float(np.max(np.abs(mu))), abs(rf) if rf is not None else 0.0)
        def sharpe(w):
            risk = math.sqrt(variance(w))
            return (expected(w)-rf)/risk if risk > sharpe_floor else -math.inf
        constraints = [
            {"type":"ineq", "fun":lambda w: float(sum(w))-net_lo},
            {"type":"ineq", "fun":lambda w: net_hi-float(sum(w))},
            {"type":"ineq", "fun":lambda w: gross-float(sum(abs(w)))},
        ]
        for vector, minimum, maximum in limit_rows.values():
            constraints.append({"type":"ineq", "fun":lambda w, vector=vector, cap=maximum: cap-float(vector@w)})
            if minimum is not None:
                constraints.append({"type":"ineq", "fun":lambda w, vector=vector, floor=minimum: float(vector@w)-floor})
        if target is not None:
            constraints.append({"type":"ineq", "fun":lambda w: expected(w)-target})
        feasible = _linear_feasible(lower, upper, gross, net_lo, net_hi, limit_rows,
                                    allow_cash=allow_cash, funding=funding, cash_yield=cash_yield,
                                    target=target, mu=mu, check_clock=check_clock)
        if not feasible:
            raise UnsupportedInput("The declared bounds, exposures and return target are infeasible.")
        seeds = feasible + [np.clip(np.ones(n)/n,lower,upper), lower, upper]
        candidates = []
        def callback(_):
            check_clock()
        def goal(w):
            check_clock()
            if objective == "maximum_estimated_sharpe":
                score = sharpe(w)
                return -score if math.isfinite(score) else 1e12
            if objective == "maximum_expected_return":
                return -expected(w)
            return variance(w)
        def residuals_for(w):
            values = {"net_min":float(sum(w))-net_lo, "net_max":net_hi-float(sum(w)),
                      "gross":gross-float(sum(abs(w))), "bounds_lower":float(np.min(w-lower)),
                      "bounds_upper":float(np.min(upper-w)), "target":None if target is None else expected(w)-target}
            for name, (vector, minimum, maximum) in limit_rows.items():
                values[name+":max"] = maximum-float(vector@w)
                if minimum is not None:
                    values[name+":min"] = float(vector@w)-minimum
            return values
        for seed in seeds:
            check_clock()
            result = minimize(goal, seed, method="SLSQP", bounds=list(zip(lower,upper)), constraints=constraints,
                              callback=callback, options={"maxiter":iterations,"ftol":1e-12})
            if result.success:
                w = np.asarray(result.x)
                residuals = residuals_for(w)
                if min(v for v in residuals.values() if v is not None) >= -1e-7:
                    if objective != "maximum_estimated_sharpe" or math.sqrt(variance(w)) > sharpe_floor:
                        candidates.append((goal(w),w,result,residuals))
        if not candidates:
            if objective == "maximum_estimated_sharpe" and eig_min <= 1e-10*scale:
                raise Incomplete("Maximum Sharpe is unavailable for this singular or nearly singular covariance: no finite positive-risk optimum could be certified. Review the return and covariance estimates.")
            raise Incomplete("Solver did not produce a certified feasible optimum.")
        candidates.sort(key=lambda item:item[0])
        score,w,result,residuals = candidates[0]
        tied_minimum = False
        solver_label = "SLSQP multi-start"
        if objective == "minimum_variance" and eig_min <= 1e-10*scale:
            # On a PSD minimum-risk face, the positive-eigenvalue projection
            # is fixed; movement in the nullspace leaves variance unchanged.
            # Select the highest-return feasible member of that face.
            eigenvalues, eigenvectors = np.linalg.eigh(sigma)
            projection = eigenvectors[:, eigenvalues > 1e-10*scale].T
            projection_target = projection @ w
            rows, limits = [], []
            for i in range(n):
                positive = np.zeros(2*n); positive[i] = 1; positive[n+i] = -1
                negative = np.zeros(2*n); negative[i] = -1; negative[n+i] = -1
                rows.extend((positive, negative)); limits.extend((0.0, 0.0))
            rows.append(np.r_[np.zeros(n), np.ones(n)]); limits.append(gross)
            for vector, minimum, maximum in limit_rows.values():
                rows.append(np.r_[vector, np.zeros(n)]); limits.append(maximum)
                if minimum is not None:
                    rows.append(np.r_[-vector, np.zeros(n)]); limits.append(-minimum)
            equality = np.asarray([np.r_[vector, np.zeros(n)] for vector in projection]) if len(projection) else None
            regions = [(net_lo, min(net_hi, 1.0), cash_yield)]
            if allow_cash and funding is not None:
                regions.append((max(net_lo, 1.0), net_hi, funding))
            variance_tolerance = 1e-14*float(np.max(np.abs(sigma)))
            for region_lo, region_hi, rate in regions:
                if region_lo > region_hi+1e-10:
                    continue
                regional_rows = rows + [np.r_[np.ones(n), np.zeros(n)], np.r_[-np.ones(n), np.zeros(n)]]
                regional_limits = limits + [region_hi, -region_lo]
                tied = linprog(np.r_[rate-mu, np.zeros(n)], A_ub=np.asarray(regional_rows),
                               b_ub=np.asarray(regional_limits), A_eq=equality,
                               b_eq=projection_target if len(projection) else None,
                               bounds=list(zip(lower,upper))+[(0,None)]*n, method="highs")
                check_clock()
                if tied.success:
                    candidate = np.asarray(tied.x[:n])
                    candidate_residuals = residuals_for(candidate)
                    if (min(value for value in candidate_residuals.values() if value is not None) >= -1e-7
                            and np.max(np.abs(projection @ candidate-projection_target), initial=0.0) <= 1e-7
                            and variance(candidate) <= variance(w)+variance_tolerance
                            and expected(candidate) > expected(w)+1e-10):
                        w, result, residuals = candidate, tied, candidate_residuals
                        score = variance(w)
                        solver_label = "SLSQP minimum variance; HiGHS return tie-break"
                        tied_minimum = True
        risk = math.sqrt(variance(w))
        cash = 1-float(sum(w))
        if abs(cash) <= 1e-10:
            cash = 0.0
        warnings = ["Optimized returns and risk are estimates, not guaranteed future results."]
        if eig_min <= 1e-10*scale:
            warnings.append("Covariance is singular or nearly singular; weights may be nonunique or unstable.")
        if tied_minimum:
            warnings.append("Among equal minimum-variance allocations, the highest estimated return was selected.")
        if len(candidates)>1 and any(np.linalg.norm(w-other[1])>1e-5 and abs(score-other[0])<=1e-8 for other in candidates[1:]):
            warnings.append("Multiple distinct weights have numerically equal objective values; solution may be nonunique.")
        check_clock()
        return CalculationResult(Status.VALID, tuple(float(x) for x in w), "portfolio weights",
            warnings=tuple(warnings), assumptions={"objective":objective,"mode":mode,"target_is_floor":target is not None,
            "cash_yield_per_period":cash_yield,"funding_cost_per_period":funding,
            "sector_caps": {sector: cap for sector, (_, cap) in sector_rows.items()},
            "custom_groups": {name: {"minimum": floor, "maximum": cap,
                                     "investments": tuple(identity for identity, included in zip(ids, vector) if included)}
                              for name, (vector, floor, cap) in group_rows.items()}},
            diagnostics={"assets":ids,"weights":dict(zip(ids,w.tolist())),"cash_weight":cash,
            "expected_return":expected(w),"variance":variance(w),"volatility":risk,
            "estimated_sharpe":None if rf is None or risk<=sharpe_floor else sharpe(w),"objective_value":-score if objective=="maximum_estimated_sharpe" else score,
            "gross_risky_exposure":float(sum(abs(w))),"net_risky_exposure":float(sum(w)),
            "constraint_residuals":residuals,"solver":solver_label,"solver_success":bool(result.success),
            "solver_message":str(result.message),"solver_iterations":int(result.nit),"feasible":True})
    except (InputError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        return _failure(exc)


def efficient_frontier(analysis, *, points=15, **settings):
    """Build the efficient branch from achieved minimum risk to feasible maximum return."""
    if not isinstance(points, int) or not 2 <= points <= 60:
        return _failure(InputError("Choose 2 to 60 frontier points."))
    minimum = optimize_portfolio(analysis, objective="minimum_variance", **settings)
    if not minimum.ok:
        return minimum
    maximum = optimize_portfolio(analysis, objective="maximum_expected_return", **settings)
    if not maximum.ok:
        return maximum
    low = minimum.diagnostics["expected_return"]
    high = maximum.diagnostics["expected_return"]
    if high < low-1e-8:
        return _failure(Incomplete("Maximum-return solution is below the minimum-variance return."))
    frontier = [{"return": low, "volatility": minimum.diagnostics["volatility"],
                 "variance": minimum.diagnostics["variance"],
                 "weights": minimum.diagnostics["weights"], "target": low}]
    if high > low+1e-10:
        for target in np.linspace(low, high, points)[1:]:
            solution = optimize_portfolio(analysis, objective="target_return_minimum_variance",
                                          target_return=float(target), **settings)
            if not solution.ok:
                return CalculationResult(Status.INCOMPLETE, None, "efficient frontier",
                                         message=f"A frontier point could not be certified: {solution.message}")
            d = solution.diagnostics
            if d["expected_return"] < target-1e-7:
                return _failure(Incomplete("A frontier point missed its return floor."))
            if d["expected_return"] <= frontier[-1]["return"]+1e-10:
                continue
            frontier.append({"return": d["expected_return"], "volatility": d["volatility"],
                             "variance": d["variance"], "weights": d["weights"],
                             "target": float(target)})
    return CalculationResult(Status.VALID, None, "efficient frontier",
                             warnings=tuple(dict.fromkeys((*minimum.warnings, *maximum.warnings))),
                             assumptions={"branch": "achieved minimum-variance return to feasible maximum return",
                                          "constraints": minimum.assumptions},
                             diagnostics={"points": frontier, "minimum_variance": minimum.diagnostics,
                                          "maximum_return": maximum.diagnostics})
