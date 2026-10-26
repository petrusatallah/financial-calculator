"""REQ-PORT-02 comparable portfolio allocations on one validated observation set."""
from __future__ import annotations

from .portfolio_s4 import analyze_portfolio
from .result import CalculationResult, Status
from .validation import InputError


def compare_portfolios(*, assets, allocations, currency, frequency, mode="Standard",
                       cash_annual_yield=None, funding_annual_rate=None, risk_free_annual_rate=None, execution_profile=None):
    try:
        if not isinstance(allocations,(list,tuple)) or len(allocations)<2:
            raise InputError("Enter at least two named allocations.")
        names=[]
        results=[]
        for item in allocations:
            if not isinstance(item,dict) or not isinstance(item.get("name"),str) or not item["name"].strip():
                raise InputError("Each allocation needs a name and mapped weights.")
            name=item["name"].strip()
            if name in names:
                raise InputError("Allocation names must be unique.")
            names.append(name)
            result=analyze_portfolio(assets=assets,weights=item.get("weights"),currency=currency,frequency=frequency,
                mode=mode,cash_weight=item.get("cash_weight",0),cash_annual_yield=cash_annual_yield,funding_annual_rate=funding_annual_rate,
                risk_free_annual_rate=risk_free_annual_rate,execution_profile=execution_profile)
            if not result.ok:
                return result
            results.append(result)
        dates=results[0].diagnostics["dates"]
        if any(result.diagnostics["dates"]!=dates for result in results):
            raise InputError("Portfolio comparisons require identical aligned dates.")
        rows=[]
        for name,result in zip(names,results):
            d=result.diagnostics
            rows.append({"name":name,"weights":d["weights"],"cash_weight":d["cash_weight"],
                "expected_return":d["expected_portfolio_return"],"volatility":d["volatility"],
                "annualized_geometric_return":d["annualized_geometric_return"],
                "cumulative_return":d["cumulative_return"],"historical_returns":d["portfolio_returns"],
                "cumulative_path":d["cumulative_path"]})
        return CalculationResult(Status.VALID,None,"portfolio comparison",warnings=tuple(dict.fromkeys(w for r in results for w in r.warnings)),
            assumptions=results[0].assumptions,diagnostics={"dates":dates,"portfolios":rows})
    except (InputError,TypeError,ValueError) as exc:
        return CalculationResult(Status.INVALID,None,"portfolio comparison",message=str(exc))
