"""Six-step manual Investments and Portfolio Streamlit screens."""
from __future__ import annotations

import copy
import calendar
from contextlib import nullcontext
from datetime import date, datetime
from html import escape
import json

import pandas as pd
import streamlit as st

from apps.manual_returns_formulas import individual_steps, investments_portfolio_steps, matrix_steps, number, portfolio_steps
from apps.manual_returns_excel import investment_excel_bytes
from financial_toolkit.manual_returns import (
    INVESTMENT_OPTIONS, PORTFOLIO_OPTIONS, calculate_manual_returns, investment_weight_total)
from financial_toolkit.validation import InputError


def _period_end(start, frequency, offset=0):
    if frequency == "monthly":
        month_index = start.year * 12 + start.month - 1 + offset
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        return date(year, month, calendar.monthrange(year, month)[1])
    return date(start.year + offset, 12, 31)


def _period_rows(names, frequency, start, count):
    return [{"Date": _period_end(start, frequency, i).isoformat(),
             **{name: "" for name in names}} for i in range(count)]


def _initial(kind):
    names = ["Investment 1", "Investment 2"] if kind == "Investments" else ["Portfolio A", "Portfolio B"]
    year = date.today().year
    form = {"started": False, "names": names, "frequency": "monthly",
            "rows": [{"Date": f"{year}-01-31", **{name: "" for name in names}},
                     {"Date": f"{year}-02-28", **{name: "" for name in names}},
                     {"Date": f"{year}-03-31", **{name: "" for name in names}}],
            "option": INVESTMENT_OPTIONS[0] if kind == "Investments" else PORTFOLIO_OPTIONS[0],
            "risk_free": "", "market": "", "target": "", "benchmark": {},
            "weights": {name: "50" for name in names} if kind == "Investments" else {},
            "cash_weight": "0", "cash_yield": "", "funding_rate": "", "advanced": {},
            "result": None, "signature": None, "epoch": 0}
    if kind == "Investments":
        form["period_starts"] = {"monthly": date(year, 1, 1), "yearly": date(year, 1, 1)}
        form["return_drafts"] = {}
        form["rows"] = _period_rows(names, "monthly", form["period_starts"]["monthly"], 3)
    return form


@st.fragment
def _investment_returns_table(form, key):
    """Keep cell edits local to this fragment and structural edits explicit."""
    frequency = form["frequency"]
    start = st.date_input("Starting period", value=form["period_starts"][frequency],
                          key=f"{key}_start_{frequency}")
    form["period_starts"][frequency] = start
    st.caption("Apply starting period replaces this draft's dates while keeping return values in their rows."
               " Manual date edits stay in place until you apply a new start.")
    if st.button("Apply starting period", key=key+"_apply_start"):
        generated = _period_rows(form["names"], frequency, start, len(form["rows"]))
        for new, old in zip(generated, form["rows"]):
            for name in form["names"]:
                new[name] = old.get(name, "")
        form["rows"] = generated
        form["epoch"] += 1
        st.rerun()
    if form.get("table_base_epoch") != form["epoch"]:
        form["table_base"] = copy.deepcopy(form["rows"])
        form["table_base_epoch"] = form["epoch"]
    table = pd.DataFrame(form["table_base"], columns=["Date", *form["names"]]).fillna("").astype(str)
    columns = {"Date": st.column_config.TextColumn("Date"),
               **{name: st.column_config.TextColumn(
                   f"{name} (%)", help="Type 5 for a 5% return, or enter 5%.")
                  for name in form["names"]}}
    edited = st.data_editor(table, hide_index=True, num_rows="fixed", width="stretch",
                            column_config=columns,
                            key=f"{key}_table_{form['epoch']}")
    # The Calculate button reruns the whole page. Keep the values saved by the
    # editor's preceding fragment rerun instead of replacing them with a stale
    # editor snapshot during that button rerun.
    if not st.session_state.get(key + "_calculate", False):
        form["rows"] = edited.fillna("").to_dict("records")
    add, remove = st.columns(2)
    if add.button("Add Row", key=key+"_add_row"):
        try:
            last = date.fromisoformat(str(form["rows"][-1]["Date"]))
            next_date = _period_end(last, frequency, 1).isoformat()
        except (KeyError, TypeError, ValueError):
            st.error("Enter a valid YYYY-MM-DD date in the last row before adding a row.")
        else:
            form["rows"].append({"Date": next_date, **{name: "" for name in form["names"]}})
            form["epoch"] += 1
            st.rerun()
    if remove.button("Remove last row", key=key+"_remove_row", disabled=len(form["rows"]) <= 2):
        form["rows"].pop()
        form["epoch"] += 1
        st.rerun()


def _key(kind):
    return "manual_" + kind.lower()


def _reset(kind):
    key = _key(kind)
    for widget_key in list(st.session_state):
        if widget_key.startswith(key + "_"):
            del st.session_state[widget_key]
    st.session_state[key] = _initial(kind)
    st.rerun()


def _rerender(form):
    form["epoch"] += 1
    st.rerun()


def _signature(form, financial_mode):
    return json.dumps({"financial_mode": financial_mode,
                       **{k: v for k, v in form.items() if k not in (
                           "result", "signature", "epoch", "period_starts", "return_drafts",
                           "table_base", "table_base_epoch")}},
                      sort_keys=True, default=str)


def _pct(x):
    if x is None:
        return "Undefined"
    scaled = x * 100
    return f"{scaled:.4e}%" if scaled != 0 and abs(scaled) < 0.00005 else f"{scaled:,.4f}%"


def _ratio(x):
    return f"{x:.4e}" if x != 0 and abs(x) < 0.00005 else f"{x:,.4f}"


def _variance(x):
    return f"{x:.8e}" if x != 0 and abs(x) < 0.000000005 else f"{x:,.8f}"


def _investment_snapshot(form, financial_mode):
    return {"names": copy.deepcopy(form["names"]), "rows": copy.deepcopy(form["rows"]),
            "frequency": form["frequency"], "weights": copy.deepcopy(form["weights"]),
            "risk_free": form["risk_free"], "market": form["market"],
            "benchmark": copy.deepcopy(form["benchmark"]),
            "cash_weight": form["cash_weight"], "cash_yield": form["cash_yield"],
            "funding_rate": form["funding_rate"], "advanced": copy.deepcopy(form["advanced"]),
            "financial_mode": financial_mode,
            "calculated_at": datetime.now().astimezone().isoformat(timespec="seconds")}


def _benchmark_percent(value):
    """Make bare benchmark numbers explicit percentages at the UI boundary."""
    entered = str(value).strip()
    if not entered or entered.endswith("%"):
        return entered
    try:
        float(entered)
    except ValueError:
        return entered  # Preserve invalid input for the existing validation message.
    return entered + "%"


def _matrix(names, values):
    return pd.DataFrame([[float("nan") if x is None else x for x in row]
                         for row in values], index=names, columns=names)


def _matrix_style(names, values, heatmap=False):
    matrix = _matrix(names, values)
    if heatmap:
        return matrix.style.format(lambda x: "Undefined" if pd.isna(x) else number(x)).background_gradient(
            cmap="RdBu", vmin=-1, vmax=1)
    return matrix.map(lambda x: "Undefined" if pd.isna(x) else number(x))


def _calculate_investments_analysis(form, financial_mode, advanced):
    """Combine verified Investments calculations without changing their formulas."""
    inputs = dict(kind="Investments", names=form["names"], rows=copy.deepcopy(form["rows"]),
                  frequency=form["frequency"], financial_mode=financial_mode,
                  weights=form["weights"],
                  cash_weight=form["cash_weight"] if financial_mode == "Advanced" else "0",
                  cash_annual_yield=form["cash_yield"], funding_annual_rate=form["funding_rate"],
                  **advanced)
    result = calculate_manual_returns(option="Average historical return", **inputs)
    unavailable = {}
    risk_free = str(form["risk_free"]).strip()
    market = str(form["market"]).strip()
    dates = [str(row["Date"]) for row in form["rows"]]
    benchmark = {day: _benchmark_percent(form["benchmark"].get(day, "")) for day in dates}
    missing_benchmark = [day for day, value in benchmark.items() if not str(value).strip()]
    has_benchmark = bool(benchmark) and not missing_benchmark

    def merge(other, metric, fields):
        for current, updated in zip(result["stats"], other["stats"]):
            current[metric] = updated[metric]
        result["portfolio"][metric] = other["portfolio"][metric]
        for field in fields:
            result[field] = other[field]
        for warning in other["warnings"]:
            if warning not in result["warnings"]:
                result["warnings"].append(warning)

    sharpe_ready = False
    if not risk_free:
        unavailable["Sharpe ratio"] = "Enter an annual effective risk-free rate."
    else:
        try:
            sharpe = calculate_manual_returns(option="Sharpe ratio", risk_free_annual=risk_free, **inputs)
        except InputError as exc:
            unavailable["Sharpe ratio"] = str(exc)
        else:
            merge(sharpe, "sharpe", ("risk_free_period", "risk_free_annual"))
            sharpe_ready = True
            undefined = [s["name"] for s in result["stats"] if s["sharpe"] is None]
            if result["portfolio"]["sharpe"] is None:
                undefined.append("Whole portfolio")
            if undefined:
                unavailable["Sharpe ratio"] = "Undefined for zero-volatility series: " + ", ".join(undefined) + "."

    beta_ready = False
    if missing_benchmark:
        unavailable["Beta"] = ("Enter a benchmark return for every date; 10 means 10% (missing "
                               + ", ".join(missing_benchmark) + ").")
    elif has_benchmark:
        try:
            beta = calculate_manual_returns(option="Beta", benchmark=benchmark, **inputs)
        except InputError as exc:
            unavailable["Beta"] = str(exc)
        else:
            merge(beta, "beta", ("benchmark_returns", "benchmark_mean", "benchmark_variance",
                                  "benchmark_covariances"))
            beta_ready = True
            if result["portfolio"]["beta"] is None:
                unavailable["Beta"] = "Undefined because the benchmark has zero variance."

    if not market:
        unavailable["CAPM required return"] = "Enter an expected annual market return."
    elif not sharpe_ready:
        unavailable["CAPM required return"] = "A valid annual effective risk-free rate is required."
    elif not beta_ready:
        unavailable["CAPM required return"] = "Complete valid benchmark returns are required."
    else:
        try:
            capm = calculate_manual_returns(option="CAPM required return", risk_free_annual=risk_free,
                                            benchmark=benchmark, expected_market_annual=market, **inputs)
        except InputError as exc:
            unavailable["CAPM required return"] = str(exc)
        else:
            merge(capm, "capm", ("market_period", "market_annual"))
            if result["portfolio"]["capm"] is None:
                unavailable["CAPM required return"] = "Undefined because benchmark variance is zero."
    result["unavailable"] = unavailable
    return result


def _readable_correlation(names, values):
    """One numeric matrix with heatmap color and readable labels."""
    headings = "".join(f'<th style="padding:10px 14px;min-width:120px;text-align:left">{escape(name)}</th>'
                       for name in names)
    rows = []
    for name, line in zip(names, values):
        cells = []
        for value in line:
            if value is None:
                shown, color = "Undefined", "transparent"
            else:
                shown = _ratio(value)
                color = (f"rgba(59,130,246,{0.12 + 0.40 * abs(value):.3f})" if value >= 0 else
                         f"rgba(239,68,68,{0.12 + 0.40 * abs(value):.3f})")
            cells.append(f'<td style="padding:10px 14px;min-width:120px;background:{color};text-align:right">{shown}</td>')
        rows.append(f'<tr><th style="padding:10px 14px;min-width:120px;text-align:left">{escape(name)}</th>'
                    + "".join(cells) + "</tr>")
    st.markdown('<div style="overflow-x:auto;font-size:16px;line-height:1.5"><table style="border-collapse:collapse">'
                '<thead><tr><th style="padding:10px 14px;text-align:left">Investment</th>' + headings +
                '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>', unsafe_allow_html=True)


def _investments_results(result):
    st.markdown("### Step 5 · Calculated results")
    unavailable = result["unavailable"]

    def metric(value, label, formatter):
        if value is not None:
            return formatter(value)
        return "Unavailable" if label in unavailable and "Undefined" not in unavailable[label] else "Undefined"

    def row(stat, name):
        return {"Name": name, f"Average ({result['frequency']})": _pct(stat["mean"]),
                "Sample variance": _variance(stat["variance"]), "Volatility": _pct(stat["volatility"]),
                "Sharpe ratio": metric(stat["sharpe"], "Sharpe ratio", _ratio),
                "Beta": metric(stat["beta"], "Beta", _ratio),
                "CAPM required return": metric(stat["capm"], "CAPM required return", _pct)}

    st.markdown("**Individual investments**")
    st.dataframe(pd.DataFrame([row(s, s["name"]) for s in result["stats"]]), hide_index=True, width="stretch")
    st.markdown("**Whole portfolio**")
    st.dataframe(pd.DataFrame([row(result["portfolio"], "Whole portfolio")]), hide_index=True, width="stretch")
    st.caption(result["portfolio"]["assumption"])
    if unavailable:
        st.info("Unavailable or undefined metrics: " + " ".join(f"{name}: {reason}" for name, reason in unavailable.items()))
    cov_column, corr_column = st.columns(2, gap="small")
    with cov_column:
        with st.container(border=True):
            st.markdown("**Sample covariance matrix (decimal return squared)**")
            st.dataframe(_matrix(result["names"], result["covariance"]).map(
                lambda x: "Undefined" if pd.isna(x) else _variance(x)), width="stretch")
    with corr_column:
        with st.container(border=True):
            st.markdown("**Correlation matrix**")
            _readable_correlation(result["names"], result["correlation"])
    with st.expander("Details · formulas and numerical working steps"):
        selected_name = st.selectbox("Investment", result["names"], key="formula_name_investments")
        st.code(individual_steps(result, selected_name), language=None, wrap_lines=True, height=300)
        pairs = [(a, b) for i, a in enumerate(result["names"]) for b in result["names"][i:]]
        selected_pair = st.selectbox("Covariance and correlation pair", pairs,
                                     format_func=lambda pair: f"{pair[0]} / {pair[1]}",
                                     key="formula_pair_investments")
        st.code(matrix_steps(result, *selected_pair), language=None, wrap_lines=True, height=300)
        st.code(investments_portfolio_steps(result), language=None, wrap_lines=True, height=300)
    st.info("Historical averages are estimates, not guaranteed future performance.")
    for warning in result["warnings"]:
        st.warning(warning)
    st.markdown("### Step 6 · Visualizations")
    chart = pd.DataFrame(result["returns"], index=result["dates"], columns=result["names"])
    chart["Whole portfolio"] = result["portfolio"]["returns"]
    st.caption("Entered returns over time (%)")
    st.line_chart(chart * 100)
    import altair as alt
    points = pd.DataFrame([{"Name": s["name"], "Volatility (%)": s["volatility"] * 100,
                            "Average return (%)": s["mean"] * 100} for s in result["stats"]])
    p = result["portfolio"]
    points.loc[len(points)] = {"Name": "Whole portfolio", "Volatility (%)": p["volatility"] * 100,
                               "Average return (%)": p["mean"] * 100}
    st.altair_chart(alt.Chart(points).mark_circle(size=120).encode(
        x="Volatility (%):Q", y="Average return (%):Q",
        tooltip=["Name", "Volatility (%)", "Average return (%)"]), width="stretch")


def _interpretation(result):
    option = result["option"]
    explanations = {
        "Average historical return": "The arithmetic average describes the typical observed period. It is not a forecast.",
        "Risk Analysis": "Individual investment risk and the weighted whole-portfolio risk use the same aligned periods.",
        "Variance": "Higher sample variance means returns moved farther from their historical average.",
        "Volatility (standard deviation)": "Volatility is the sample standard deviation of period returns; it describes dispersion, not loss probability.",
        "Covariance matrix": "Positive covariance means two return series tended to move together; negative covariance means opposite movement.",
        "Correlation matrix": "Correlation scales co-movement from −1 to +1. It is undefined for a constant return series.",
        "Sharpe ratio": "Sharpe compares historical excess return with volatility over the same period.",
        "Beta": "Beta estimates sensitivity to the entered benchmark over aligned dates.",
        "CAPM required return": "CAPM is a model-implied required return using the manually entered expected market return.",
        "Portfolio statistics": "These statistics describe each entered complete portfolio independently.",
        "Covariance and correlation matrix": "The matrices show how the entered portfolio return series moved together.",
        "Compare portfolios": "Compare historical averages and risk over the same aligned dates.",
        "Efficient frontier": "Each plotted point is an estimated minimum-risk allocation meeting a return floor.",
    }
    if option.startswith("Markowitz"):
        return "The allocation is estimated from historical means and sample covariance; it is not guaranteed future performance."
    return explanations.get(option, "")


def _results(result):
    if result["kind"] == "Investments":
        _investments_results(result)
        return
    st.markdown("### Step 5 · Calculated results")
    option = result["option"]
    primary = {"Average historical return": ("mean", _pct), "Variance": ("variance", number),
               "Volatility (standard deviation)": ("volatility", _pct),
               "Sharpe ratio": ("sharpe", lambda x: "Undefined" if x is None else number(x)),
               "Beta": ("beta", lambda x: "Undefined" if x is None else number(x)),
               "CAPM required return": ("capm", _pct)}
    if option in primary:
        field, formatter = primary[option]
        cols = st.columns(min(len(result["stats"]), 4))
        for i, stat in enumerate(result["stats"]):
            cols[i % len(cols)].metric(stat["name"], formatter(stat[field]))
    rows = []
    for s in result["stats"]:
        rows.append({"Name": s["name"], f"Average ({result['frequency']})": _pct(s["mean"]),
                     "Sample variance": number(s["variance"]), "Volatility": _pct(s["volatility"]),
                     "Sharpe": "Undefined" if s["sharpe"] is None else number(s["sharpe"]),
                     "Beta": "Undefined" if s["beta"] is None else number(s["beta"]),
                     "CAPM required return": _pct(s["capm"])})
    if result["kind"] == "Investments":
        st.markdown("**Individual investments**")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if result["portfolio"] is not None:
        p = result["portfolio"]
        st.markdown("**Whole portfolio**")
        st.dataframe(pd.DataFrame([{"Average (" + result["frequency"] + ")": _pct(p["mean"]),
            "Sample variance": number(p["variance"]), "Volatility": _pct(p["volatility"]),
            "Sharpe": "Undefined" if p["sharpe"] is None else number(p["sharpe"]),
            "Beta": "Undefined" if p["beta"] is None else number(p["beta"]),
            "CAPM required return": _pct(p["capm"])}]), hide_index=True, width="stretch")
        st.caption(p["assumption"])
    st.write(_interpretation(result))
    if result["kind"] == "Investments" or option in ("Covariance matrix", "Covariance and correlation matrix", "Compare portfolios", "Portfolio statistics"):
        st.markdown("**Sample covariance (decimal return squared)**")
        st.dataframe(_matrix_style(result["names"], result["covariance"]), width="stretch")
    if result["kind"] == "Investments" or option in ("Correlation matrix", "Covariance and correlation matrix", "Compare portfolios", "Portfolio statistics"):
        st.markdown("**Correlation**")
        st.dataframe(_matrix_style(result["names"], result["correlation"]), width="stretch")
    selected_name = st.selectbox("Inspect numerical formula for", result["names"],
                                 key="formula_name_" + result["kind"].lower())
    with st.expander("Entered values and numerical steps — " + selected_name,
                     expanded=len(result["dates"]) <= 10):
        st.code(individual_steps(result, selected_name), language=None, wrap_lines=True, height=300)
    if result["kind"] == "Investments" or option in ("Covariance matrix", "Correlation matrix", "Covariance and correlation matrix",
                  "Compare portfolios", "Portfolio statistics"):
        pairs = [(a, b) for i, a in enumerate(result["names"]) for b in result["names"][i:]]
        selected_pair = st.selectbox("Inspect covariance and correlation for", pairs,
                                     format_func=lambda pair: f"{pair[0]} / {pair[1]}",
                                     key="formula_pair_" + result["kind"].lower())
        with st.expander("Paired return substitutions — " + " / ".join(selected_pair)):
            st.code(matrix_steps(result, *selected_pair), language=None, wrap_lines=True, height=300)
    if result["portfolio"] is not None:
        with st.expander("Actual weights, returns and covariance in whole-portfolio formulas", expanded=True):
            st.code(investments_portfolio_steps(result), language=None, wrap_lines=True, height=300)
    if result["optimization"]:
        d = result["optimization"]
        st.markdown("**Estimated allocation between entered portfolios**")
        st.dataframe(pd.DataFrame([{"Portfolio": k, "Weight": _pct(v)} for k, v in d["weights"].items()]),
                     hide_index=True, width="stretch")
        st.write(f"Estimated return: {_pct(d['expected_return'])} per period · Volatility: {_pct(d['volatility'])} per period")
        st.caption(f"wᵀμ = {number(d['expected_return'])}; wᵀΣw = {number(d['variance'])}; Σw = {number(sum(d['weights'].values()))}. {d['solver_message']}")
        st.caption("wᵀμ = " + " + ".join(f"{d['weights'][s['name']]:.6f} × {s['mean']:.6f}" for s in result["stats"]) + f" = {d['expected_return']:.6f} per period.")
        with st.expander("Actual weights, means and covariance in portfolio formulas"):
            st.code(portfolio_steps(result, d), language=None, wrap_lines=True, height=300)
    if result["frontier"]:
        st.dataframe(pd.DataFrame(result["frontier"]), hide_index=True, width="stretch")
        point_number = st.selectbox("Inspect efficient-frontier point", range(len(result["frontier"])),
                                    format_func=lambda i: f"Point {i+1}: target {_pct(result['frontier'][i]['target'])}",
                                    key="formula_frontier_" + result["kind"].lower())
        with st.expander("Actual weights, means and covariance for selected point"):
            st.code(portfolio_steps(result, result["frontier"][point_number]),
                    language=None, wrap_lines=True, height=300)
    st.info("Historical averages and optimized allocations are estimates, not guaranteed future performance.")
    for warning in result["warnings"]:
        st.warning(warning)
    st.markdown("### Step 6 · Visualizations")
    chart = pd.DataFrame(result["returns"], index=result["dates"], columns=result["names"])
    if result["portfolio"] is not None:
        chart["Whole portfolio"] = result["portfolio"]["returns"]
    st.caption("Entered returns over time (%)")
    st.line_chart(chart * 100)
    if len(result["names"]) > 1 and (result["kind"] == "Investments" or option in ("Correlation matrix", "Covariance matrix", "Covariance and correlation matrix", "Compare portfolios", "Portfolio statistics", "Efficient frontier")):
        st.caption("Correlation heatmap; blank cells indicate undefined correlation")
        st.dataframe(_matrix_style(result["names"], result["correlation"], heatmap=True), width="stretch")
    if option in ("Volatility (standard deviation)", "Risk Analysis", "Sharpe ratio", "Compare portfolios", "Portfolio statistics", "Efficient frontier"):
        import altair as alt
        points = pd.DataFrame([{"Name": s["name"], "Volatility (%)": s["volatility"]*100,
                               "Average return (%)": s["mean"]*100} for s in result["stats"]])
        if result["portfolio"] is not None:
            p = result["portfolio"]
            points.loc[len(points)] = {"Name": "Whole portfolio", "Volatility (%)": p["volatility"]*100,
                                       "Average return (%)": p["mean"]*100}
        st.altair_chart(alt.Chart(points).mark_circle(size=120).encode(x="Volatility (%):Q", y="Average return (%):Q", tooltip=["Name", "Volatility (%)", "Average return (%)"]), width="stretch")
        if result["frontier"]:
            frontier = pd.DataFrame([{"Volatility (%)": p["volatility"]*100, "Return (%)": p["return"]*100} for p in result["frontier"]])
            st.altair_chart(alt.Chart(frontier).mark_line(point=True).encode(x="Volatility (%):Q", y="Return (%):Q"), width="stretch")


def render(kind, financial_mode="Standard"):
    key = _key(kind)
    if key not in st.session_state:
        st.session_state[key] = _initial(kind)
    f = st.session_state[key]
    if kind == "Investments":
        # Existing browser sessions predate the weight fields; never invent an allocation.
        f.setdefault("weights", {name: "" for name in f["names"]})
        for name in f["names"]:
            f["weights"].setdefault(name, "")
        for field, default in (("cash_weight", "0"), ("cash_yield", ""),
                               ("funding_rate", ""), ("advanced", {})):
            f.setdefault(field, default)
        f.setdefault("period_starts", {"monthly": date.today().replace(month=1, day=1),
                                       "yearly": date.today().replace(month=1, day=1)})
        f.setdefault("return_drafts", {})
    st.subheader(kind)
    if not f["started"]:
        st.markdown("### Step 1 · Open " + kind)
        st.write("Enter manual historical returns, calculate risk and return, and inspect the results."
                 if kind == "Investments" else "Compare complete portfolios and estimate allocations between them using manual historical returns.")
        if st.button("Start Analysis", key=key+"_start"):
            f["started"] = True
            st.rerun()
        return
    if kind == "Investments":
        st.markdown("""<style>
        .st-key-manual_investments_calculate button { background: #1d6fe8; color: white; border-color: #3384f0; }
        .st-key-manual_investments_export button:not(:disabled) { background: #087d42; color: white; border-color: #119753; }
        .st-key-manual_investments_calculate button:hover { background: #2d80f5; color: white; }
        .st-key-manual_investments_export button:not(:disabled):hover { background: #119753; color: white; }
        </style>""", unsafe_allow_html=True)
    dashboard = st.columns([1, 1.55], gap="small") if kind == "Investments" else None
    if dashboard:
        with dashboard[1]:
            returns_card = st.container(border=True)
            with returns_card:
                st.markdown("#### Step 3 · Historical returns")
                frequency = st.radio("Return frequency", ["monthly", "yearly"],
                                     index=["monthly", "yearly"].index(f["frequency"]),
                                     horizontal=True, key=key+"_frequency")
    with (dashboard[0] if dashboard else nullcontext()):
        with (st.container(border=True) if dashboard else nullcontext()):
            st.markdown("#### Step 2 · Portfolio setup" if kind == "Investments" else
                        "### Step 2 · Create portfolios")
            if not dashboard:
                frequency = st.radio("Return frequency", ["monthly", "yearly"],
                                     index=["monthly", "yearly"].index(f["frequency"]),
                                     horizontal=True, key=key+"_frequency")
            if kind == "Investments" and frequency != f["frequency"]:
                previous = f["frequency"]
                f["return_drafts"][previous] = copy.deepcopy(f["rows"])
                if frequency not in f["return_drafts"]:
                    f["period_starts"][frequency] = date(f["period_starts"][previous].year, 1, 1)
                    f["return_drafts"][frequency] = _period_rows(
                        f["names"], frequency, f["period_starts"][frequency], len(f["rows"]))
                f["rows"] = copy.deepcopy(f["return_drafts"][frequency])
                f["frequency"] = frequency
                _rerender(f)
            else:
                f["frequency"] = frequency
            if kind == "Investments":
                name_head, weight_head, _ = st.columns([3, 1.4, .8], gap="small")
                name_head.caption("Investment")
                weight_head.caption("Weight (%)")
            for i, old in enumerate(list(f["names"])):
                columns = st.columns([3, 1.4, .8], gap="small") if kind == "Investments" else st.columns([5, 1])
                a, b = columns[0], columns[-1]
                singular = "Investment" if kind == "Investments" else "Portfolio"
                new = a.text_input(f"{singular} {i+1} name", value=old,
                                   label_visibility="collapsed" if kind == "Investments" else "visible",
                                   key=f"{key}_name_{i}_{f['epoch']}")
                if new != old:
                    f["names"][i] = new
                    for row in f["rows"]:
                        row[new] = row.pop(old, "")
                    if kind == "Investments":
                        f["weights"][new] = f["weights"].pop(old, "")
                        for draft in f["return_drafts"].values():
                            for row in draft:
                                row[new] = row.pop(old, "")
                        for bound in ("lower_bounds", "upper_bounds"):
                            if bound in f["advanced"]:
                                f["advanced"][bound][new] = f["advanced"][bound].pop(old, "")
                    _rerender(f)
                if kind == "Investments":
                    f["weights"][old] = columns[1].text_input(f"Weight (%) for {old}",
                        value=f["weights"].get(old, ""), label_visibility="collapsed",
                        key=f"{key}_weight_{i}_{f['epoch']}")
                if b.button("🗑" if kind == "Investments" else "Remove",
                            help=f"Remove {old}" if kind == "Investments" else None,
                            key=f"{key}_remove_{i}", disabled=len(f["names"]) <= 1):
                    f["names"].pop(i)
                    for row in f["rows"]:
                        row.pop(old, None)
                    if kind == "Investments":
                        f["weights"].pop(old, None)
                        for draft in f["return_drafts"].values():
                            for row in draft:
                                row.pop(old, None)
                    _rerender(f)
            if st.button("Add " + ("investment" if kind == "Investments" else "portfolio"), key=key+"_add"):
                prefix = "Investment " if kind == "Investments" else "Portfolio "
                n = len(f["names"]) + 1
                name = prefix + (str(n) if kind == "Investments" else chr(64+n))
                while name in f["names"]:
                    n += 1
                    name = prefix + str(n)
                f["names"].append(name)
                for row in f["rows"]:
                    row[name] = ""
                if kind == "Investments":
                    f["weights"][name] = ""
                    for draft in f["return_drafts"].values():
                        for row in draft:
                            row[name] = ""
                _rerender(f)
            if kind == "Investments":
                if financial_mode == "Advanced":
                    f["cash_weight"] = st.text_input("Cash holding Weight (%)", value=f["cash_weight"], key=key+"_cash_weight")
                    f["cash_yield"] = st.text_input("Annual effective cash yield (%) — required for positive cash", value=f["cash_yield"], key=key+"_cash_yield")
                    f["funding_rate"] = st.text_input("Annual effective funding rate (%) — required for negative cash", value=f["funding_rate"], key=key+"_funding_rate")
                total = investment_weight_total(f["weights"], f["cash_weight"] if financial_mode == "Advanced" else None)
                st.metric("Total Weight (%)", "Incomplete" if total is None else f"{total:g}%")
                st.caption("Investment weights must total 100%." if financial_mode == "Standard" else
                           "Investment weights plus cash must total 100%. Enter cash explicitly, including 0%.")
                st.caption("Whole-portfolio returns assume constant weights rebalanced each period.")
    with (returns_card if dashboard else nullcontext()):
        if not dashboard:
            st.markdown("### Step 3 · Enter historical returns")
        st.caption("Each investment column is in percent: enter 10 for a 10% return (or type 10%). "
                   "Press Enter once to save a cell. "
                   "Each row is one aligned observation period; blanks are not treated as zero.")
        if kind == "Investments":
            _investment_returns_table(f, key)
        else:
            edited = st.data_editor(pd.DataFrame(f["rows"], columns=["Date", *f["names"]]),
                                    hide_index=True, num_rows="dynamic", width="stretch",
                                    key=f"{key}_table_{f['epoch']}")
            f["rows"] = edited.fillna("").to_dict("records")
    if kind == "Investments":
        st.markdown("### Step 4 · Optional market inputs")
        st.markdown("""<style>
        .st-key-investments_step4 [data-testid="stTextInputRootElement"] {
            background-color: #334155 !important;
            border: 1px solid #94a3b8 !important;
            border-radius: 0.5rem;
        }
        .st-key-investments_step4 [data-testid="stTextInputRootElement"]:focus-within {
            border-color: #38bdf8 !important;
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.28);
        }
        .st-key-investments_step4 [data-testid="stTextInputRootElement"] input {
            color: #f8fafc !important;
        }
        </style>""", unsafe_allow_html=True)
        with st.container(border=True, key="investments_step4"):
            with st.expander("Risk-free rate, benchmark and expected market return"):
                market_left, market_right = st.columns([1, 1.2])
                with market_left:
                    f["risk_free"] = st.text_input("Annual effective risk-free rate (%)", value=f["risk_free"], key=key+"_rf")
                    f["market"] = st.text_input("Expected annual market return (%) — manually entered", value=f["market"], key=key+"_market")
                    st.caption("Type 10 for 10%. Optional inputs add Sharpe, beta and CAPM when complete.")
                with market_right:
                    st.caption("Benchmark returns (%) for the same dates as investment returns")
                    benchmark_rows = [{"Date": row["Date"], "Benchmark (%)": f["benchmark"].get(str(row["Date"]), "")}
                                      for row in f["rows"]]
                    bench = st.data_editor(pd.DataFrame(benchmark_rows), hide_index=True, disabled=["Date"],
                                           column_config={"Benchmark (%)": st.column_config.TextColumn(
                                               "Benchmark (%)", help="Type 10 for 10%, or enter 10%.")},
                                           width="stretch", key=f"{key}_bench_{f['epoch']}")
                    f["benchmark"] = {str(row["Date"]): row["Benchmark (%)"]
                                      for row in bench.fillna("").to_dict("records")}
    else:
        st.markdown("### Step 4 · Choose calculation")
        options = PORTFOLIO_OPTIONS
        f["option"] = st.selectbox("Calculation", options, index=options.index(f["option"]), key=key+"_option")
        needs_rf = f["option"] in ("Sharpe ratio", "CAPM required return", "Markowitz optimization — Maximum Sharpe ratio")
        needs_benchmark = f["option"] in ("Beta", "CAPM required return")
        if needs_rf or f["option"] == "Portfolio statistics":
            f["risk_free"] = st.text_input("Annual effective risk-free rate (%)" + ("" if needs_rf else " — optional for Sharpe"),
                                           value=f["risk_free"], key=key+"_rf")
        if needs_benchmark:
            st.caption("Enter a benchmark return (%) for each date shown above.")
            benchmark_rows = [{"Date": row["Date"], "Benchmark (%)": f["benchmark"].get(str(row["Date"]), "")} for row in f["rows"]]
            bench = st.data_editor(pd.DataFrame(benchmark_rows), hide_index=True, disabled=["Date"], width="stretch", key=f"{key}_bench_{f['epoch']}")
            f["benchmark"] = {str(row["Date"]): row["Benchmark (%)"] for row in bench.fillna("").to_dict("records")}
        if f["option"] == "CAPM required return":
            f["market"] = st.text_input("Expected annual market return (%) — manually entered", value=f["market"], key=key+"_market")
        if f["option"] == "Markowitz optimization — Target return":
            f["target"] = st.text_input(f"Target return (% per {f['frequency'][:-2] if f['frequency']=='yearly' else 'month'})", value=f["target"], key=key+"_target")
    advanced = {}
    if kind == "Investments" and financial_mode == "Advanced":
        st.caption("Advanced investment bounds and gross/net exposure limits (%). Cash is 100% minus risky net exposure.")
        for name in f["names"]:
            for label, field, default in (("lower", "lower_bounds", "0"), ("upper", "upper_bounds", "100")):
                current = f["advanced"].get(field, {}).get(name, default)
                entered = st.text_input(f"{name} {label} weight (%)", value=current,
                    key=f"{key}_{field}_{name}_{f['epoch']}")
                advanced.setdefault(field, {})[name] = entered
        for label, field, default in (("Gross exposure cap (%)", "gross_cap", "100"),
                                      ("Minimum net exposure (%)", "net_min", "100"),
                                      ("Maximum net exposure (%)", "net_max", "100")):
            advanced[field] = st.text_input(label, value=f["advanced"].get(field, default), key=key+"_"+field)
        advanced["allow_short"] = st.checkbox("Allow short positions", value=f["advanced"].get("allow_short", False), key=key+"_short_investments")
        f["advanced"] = advanced
    if kind == "Portfolio" and (f["option"].startswith("Markowitz") or f["option"] == "Efficient frontier"):
        if financial_mode == "Advanced":
            st.caption("Advanced allocation constraints apply between the entered portfolios.")
            for name in f["names"]:
                lo = st.number_input(name+" lower weight (%)", value=0.0, key=key+"_lo_"+name)
                hi = st.number_input(name+" upper weight (%)", value=100.0, key=key+"_hi_"+name)
                advanced.setdefault("lower_bounds", {})[name] = lo/100
                advanced.setdefault("upper_bounds", {})[name] = hi/100
            advanced["gross_cap"] = st.number_input("Gross exposure cap (%)", value=100.0, key=key+"_gross")/100
            advanced["net_min"] = st.number_input("Minimum net exposure (%)", value=100.0, key=key+"_netmin")/100
            advanced["net_max"] = st.number_input("Maximum net exposure (%)", value=100.0, key=key+"_netmax")/100
            advanced["allow_short"] = st.checkbox("Allow short positions", key=key+"_short")
        else:
            st.caption("Standard allocation: long only, fully invested; weights sum to 100%.")
    if kind == "Investments":
        action_column, export_column = st.columns([1.55, 1], gap="small")
        with action_column:
            with st.container(border=True):
                st.markdown("#### Calculate")
                left, right = st.columns([2, 1])
        with export_column:
            with st.container(border=True):
                st.markdown("#### Export results")
                export = st.container()
    else:
        left, right = st.columns(2)
    if left.button("Calculate Analysis" if kind == "Investments" else "Calculate",
                   type="primary" if kind == "Investments" else "secondary", key=key+"_calculate"):
        try:
            if kind == "Investments":
                st.session_state.pop(key + "_excel", None)
                st.session_state.pop(key + "_snapshot", None)
                f["result"] = _calculate_investments_analysis(f, financial_mode, advanced)
            else:
                f["result"] = calculate_manual_returns(kind=kind, names=f["names"], rows=copy.deepcopy(f["rows"]),
                    frequency=f["frequency"], option=f["option"], risk_free_annual=f["risk_free"],
                    benchmark=f["benchmark"], expected_market_annual=f["market"],
                    target_return=f["target"], financial_mode=financial_mode, **advanced)
            f["signature"] = _signature(f, financial_mode)
            if kind == "Investments":
                snapshot = _investment_snapshot(f, financial_mode)
                st.session_state[key + "_excel"] = investment_excel_bytes(snapshot, copy.deepcopy(f["result"]))
                st.session_state[key + "_snapshot"] = snapshot
        except (InputError, ValueError) as exc:
            f["result"] = None
            st.error(str(exc))
    if right.button("Reset", key=key+"_reset"):
        _reset(kind)
    if kind == "Investments":
        current = bool(f["result"] and f["signature"] == _signature(f, financial_mode))
        snapshot = st.session_state.get(key + "_snapshot")
        export.download_button("Export to Excel", data=st.session_state.get(key + "_excel", b""),
                               file_name="Investment_Analysis_" +
                               (snapshot["calculated_at"][:10] if snapshot else date.today().isoformat()) + ".xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               type="primary",
                               disabled=not (current and snapshot and st.session_state.get(key + "_excel")),
                               key=key+"_export")
    if f["result"]:
        if f["signature"] != _signature(f, financial_mode):
            st.warning("Inputs changed since calculation. Press Calculate Analysis to update these results."
                       if kind == "Investments" else
                       "Inputs changed since calculation. Press Calculate to update these results.")
        _results(f["result"])
