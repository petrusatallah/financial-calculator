"""Two focused Portfolio screens; Investments remains in its existing module."""
from __future__ import annotations

import calendar
import copy
import json
import math
from datetime import date
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from apps.portfolio_excel import portfolio_excel_bytes
from apps.portfolio_io import parse_portfolio_file
from financial_toolkit.optimization_s4 import efficient_frontier, optimize_portfolio, validate_portfolio_constraints
from financial_toolkit.portfolio_s4 import analyze_optimization_inputs, compare_return_histories
from financial_toolkit.validation import InputError


def _end(start, frequency, offset=0):
    if frequency == "monthly":
        index = start.year*12+start.month-1+offset
        year, month_zero = divmod(index, 12)
        month = month_zero+1
        return date(year, month, calendar.monthrange(year, month)[1])
    return date(start.year+offset, 12, 31)


def _rows(names, frequency, start, count=3):
    return [{"Date": _end(start, frequency, i).isoformat(), **{name: "" for name in names}}
            for i in range(count)]


def _initial(kind):
    names = ["Investment 1", "Investment 2"] if kind == "markowitz" else ["Portfolio A", "Portfolio B"]
    start = date(date.today().year, 1, 1)
    return {"names": names, "frequency": "monthly", "starts": {"monthly": start, "yearly": start},
            "drafts": {}, "rows": _rows(names, "monthly", start), "epoch": 0,
            "input_kind": "history", "source": "Manual entry", "means": {name: "" for name in names},
            "covariance": [["" for _ in names] for _ in names],
            "current_weights": {name: "" for name in names}, "risk_free": "", "target": "",
            "objective": "Minimum Variance", "bounds": {name: ("0", "100") for name in names},
            "sectors": {name: "" for name in names}, "sector_caps": {},
            "groups": [], "group_counter": 0, "allow_short": False,
            "gross": "100", "net_min": "100", "net_max": "100",
            "allow_cash": False, "cash_yield": "", "funding_rate": "",
            "result": None, "signature": None, "export": None, "import": None}


def _state(kind):
    key = "week11_"+kind
    if key not in st.session_state:
        st.session_state[key] = _initial(kind)
    if kind == "markowitz":
        for field in ("groups", "group_counter", "allow_short", "gross", "net_min", "net_max",
                      "allow_cash", "cash_yield", "funding_rate"):
            st.session_state[key].setdefault(field, _initial(kind)[field])
    return st.session_state[key]


def _reset(kind):
    key = "week11_"+kind
    for widget in list(st.session_state):
        if widget.startswith(key+"_"):
            del st.session_state[widget]
    st.session_state[key] = _initial(kind)
    st.rerun()


def _signature(f, mode):
    return json.dumps({"mode": mode, **{key: value for key, value in f.items()
                                      if key not in ("result", "signature", "export", "epoch", "drafts", "starts", "table_base", "table_epoch", "import")}},
                      sort_keys=True, default=str)


def _percent(value, label):
    if isinstance(value, bool):
        raise InputError(f"{label} must be a percentage number.")
    value = str(value).strip().replace(",", "")
    if value.endswith("%"):
        value = value[:-1].strip()
    try:
        number = float(value)/100
    except ValueError as exc:
        raise InputError(f"{label} must be a percentage number; type 10 for 10%.") from exc
    if not math.isfinite(number):
        raise InputError(f"{label} must be finite.")
    return number


def _percent_text(value):
    """Show imported decimal returns as percentages without float display noise."""
    return format((Decimal(str(value)) * 100).normalize(), "f")


def _pct(value):
    if value is None:
        return "Unavailable"
    displayed = f"{value*100:.4f}"
    return ("0.0000" if displayed == "-0.0000" else displayed) + "%"


def _decimal(value):
    if value is None:
        return "Undefined"
    if value == 0:
        return "0.0000000000"
    return f"{value:.4e}" if abs(value) < 5e-11 else f"{value:.10f}"


def _matrix(values, names, *, correlation=False):
    fmt = (lambda value: "Undefined" if pd.isna(value) else f"{value:.4f}") if correlation else _decimal
    return pd.DataFrame(values, index=names, columns=names).map(fmt)


def _ratio(value):
    return "Unavailable" if value is None else f"{value:.4f}"


def _portfolio_style():
    st.markdown("""<style>
    .st-key-week11_markowitz_optimize button, .st-key-week11_compare_calculate button {
        background: #1d6fe8; color: white; border-color: #3384f0;
    }
    .st-key-week11_markowitz_optimize button:hover, .st-key-week11_compare_calculate button:hover {
        background: #2d80f5; color: white;
    }
    .st-key-week11_markowitz_export button:not(:disabled),
    .st-key-week11_compare_export button:not(:disabled) {
        background: #087d42; color: white; border-color: #119753;
    }
    .st-key-week11_markowitz_export button:not(:disabled):hover,
    .st-key-week11_compare_export button:not(:disabled):hover {
        background: #119753; color: white;
    }
    </style>""", unsafe_allow_html=True)


def _rename(f, old, new):
    if not new.strip() or new in f["names"] and new != old:
        raise InputError("Names must be nonblank and unique.")
    at = f["names"].index(old)
    f["names"][at] = new
    for row in f["rows"]:
        row[new] = row.pop(old, "")
    for draft in f["drafts"].values():
        for row in draft:
            row[new] = row.pop(old, "")
    for field in ("means", "current_weights", "bounds", "sectors"):
        f[field][new] = f[field].pop(old)
    for group in f.get("groups", []):
        group["investments"] = [new if name == old else name for name in group["investments"]]
    f["epoch"] += 1
    st.rerun()


def _starting_period(f, key):
    frequency = f["frequency"]
    start = st.date_input("Starting period", value=f["starts"][frequency], key=key+"_start_"+frequency)
    f["starts"][frequency] = start
    if st.button("Apply starting period", key=key+"_apply"):
        generated = _rows(f["names"], frequency, start, len(f["rows"]))
        for fresh, old in zip(generated, f["rows"]):
            for name in f["names"]:
                fresh[name] = old.get(name, "")
        f["rows"] = generated
        f["epoch"] += 1
        st.rerun()


@st.fragment
def _table(f, key):
    frequency = f["frequency"]
    st.caption("Type 10 for 10%. One Enter saves a cell. Dates stay editable; applying a new start changes only dates.")
    if f.get("table_epoch") != f["epoch"]:
        f["table_base"] = copy.deepcopy(f["rows"])
        f["table_epoch"] = f["epoch"]
    table = pd.DataFrame(f["table_base"], columns=["Date", *f["names"]]).fillna("").astype(str)
    config = {"Date": st.column_config.TextColumn("Date"),
              **{name: st.column_config.TextColumn(name+" (%)") for name in f["names"]}}
    edited = st.data_editor(table, hide_index=True, num_rows="fixed", width="stretch",
                            column_config=config, key=f"{key}_table_{f['epoch']}")
    if not st.session_state.get(key+"_calculate", False) and not st.session_state.get(key+"_optimize", False):
        f["rows"] = edited.fillna("").to_dict("records")
    add, remove = st.columns(2)
    if add.button("Add Row", key=key+"_add_row"):
        try:
            last = date.fromisoformat(str(f["rows"][-1]["Date"]))
            next_day = _end(last, frequency, 1).isoformat()
        except (KeyError, TypeError, ValueError):
            st.error("Correct the last YYYY-MM-DD date before adding a row.")
        else:
            f["rows"].append({"Date": next_day, **{name: "" for name in f["names"]}})
            f["epoch"] += 1
            st.rerun()
    if remove.button("Remove last row", key=key+"_remove_row", disabled=len(f["rows"]) <= 2):
        f["rows"].pop()
        f["epoch"] += 1
        st.rerun()


def _frequency(f, key):
    picked = st.radio("Frequency", ["monthly", "yearly"], index=["monthly", "yearly"].index(f["frequency"]),
                      horizontal=True, key=f"{key}_frequency_{f['epoch']}")
    if picked != f["frequency"]:
        previous = f["frequency"]
        f["drafts"][previous] = copy.deepcopy(f["rows"])
        if picked not in f["drafts"]:
            f["starts"][picked] = date(f["starts"][previous].year, 1, 1)
            f["drafts"][picked] = _rows(f["names"], picked, f["starts"][picked], len(f["rows"]))
        f["rows"] = copy.deepcopy(f["drafts"][picked])
        f["frequency"] = picked
        f["epoch"] += 1
        st.rerun()


def _names(f, key, noun):
    old_names = list(f["names"])
    edited = st.data_editor(pd.DataFrame({noun: old_names}), hide_index=True, num_rows="fixed",
                            width="stretch", key=f"{key}_names_{f['epoch']}")
    new_names = [str(value).strip() for value in edited[noun].fillna("")]
    if any(not name for name in new_names) or len(set(new_names)) != len(new_names):
        st.error(noun + " names must be nonblank and unique.")
    elif new_names != old_names:
        mapping = dict(zip(old_names, new_names))
        for rows in [f["rows"], *f["drafts"].values()]:
            for row in rows:
                values = {old: row.pop(old, "") for old in old_names}
                row.update({mapping[old]: values[old] for old in old_names})
        for field in ("means", "current_weights", "bounds", "sectors"):
            f[field] = {mapping[old]: f[field][old] for old in old_names}
        f["names"] = new_names
        f["epoch"] += 1
        st.rerun()
    add, remove = st.columns([1, 2])
    if add.button("Add "+noun, key=key+"_add_name"):
        i = len(f["names"])+1
        name = f"{noun} {i}"
        while name in f["names"]:
            i += 1
            name = f"{noun} {i}"
        f["names"].append(name)
        for row in f["rows"]:
            row[name] = ""
        for draft in f["drafts"].values():
            for row in draft:
                row[name] = ""
        f["means"][name] = f["current_weights"][name] = f["sectors"][name] = ""
        f["bounds"][name] = ("0", "100")
        for row in f["covariance"]:
            row.append("")
        f["covariance"].append([""]*len(f["names"]))
        f["epoch"] += 1
        st.rerun()
    with remove:
        selected = st.selectbox("Remove "+noun.lower(), f["names"], key=key+"_remove_selected")
        if st.button("Remove selected", key=key+"_remove_name", disabled=len(f["names"]) <= 2):
            at = f["names"].index(selected)
            f["names"].pop(at)
            for rows in [f["rows"], *f["drafts"].values()]:
                for row in rows:
                    row.pop(selected, None)
            for field in ("means", "current_weights", "bounds", "sectors"):
                f[field].pop(selected, None)
            f["covariance"].pop(at)
            for row in f["covariance"]:
                row.pop(at)
            f["epoch"] += 1
            st.rerun()


def _investment_editor(f, key):
    old_names = list(f["names"])
    estimated = f["input_kind"] == "estimates"
    columns = {"Investment": old_names}
    if estimated:
        columns["Expected return (%)"] = [f["means"].get(name, "") for name in old_names]
    columns["Current weight (%)"] = [f["current_weights"].get(name, "") for name in old_names]
    edited = st.data_editor(pd.DataFrame(columns).astype(str), hide_index=True, num_rows="fixed",
                            width="stretch", key=f"{key}_investments_{f['epoch']}")
    records = edited.fillna("").to_dict("records")
    new_names = [str(row["Investment"]).strip() for row in records]
    if any(not name for name in new_names) or len(set(new_names)) != len(new_names):
        st.error("Investment names must be nonblank and unique.")
    else:
        if estimated:
            f["means"] = {old: str(row["Expected return (%)"]) for old, row in zip(old_names, records)}
        f["current_weights"] = {old: str(row["Current weight (%)"]) for old, row in zip(old_names, records)}
        if new_names != old_names:
            mapping = dict(zip(old_names, new_names))
            for rows in [f["rows"], *f["drafts"].values()]:
                for row in rows:
                    values = {old: row.pop(old, "") for old in old_names}
                    row.update({mapping[old]: values[old] for old in old_names})
            for field in ("means", "current_weights", "bounds", "sectors"):
                f[field] = {mapping[old]: f[field][old] for old in old_names}
            for group in f["groups"]:
                group["investments"] = [mapping[name] for name in group["investments"]]
            f["names"] = new_names
            f["epoch"] += 1
            st.rerun()
    add, remove = st.columns([1, 2])
    if add.button("Add Investment", key=key+"_add_investment"):
        i = len(f["names"])+1
        while f"Investment {i}" in f["names"]:
            i += 1
        name = f"Investment {i}"
        f["names"].append(name)
        for rows in [f["rows"], *f["drafts"].values()]:
            for row in rows:
                row[name] = ""
        f["means"][name] = f["current_weights"][name] = f["sectors"][name] = ""
        f["bounds"][name] = ("0", "100")
        for row in f["covariance"]:
            row.append("")
        f["covariance"].append([""]*len(f["names"]))
        f["epoch"] += 1
        st.rerun()
    with remove:
        selected = st.selectbox("Remove investment", f["names"], key=key+"_remove_selected")
        if st.button("Remove selected", key=key+"_remove_investment", disabled=len(f["names"]) <= 2):
            at = f["names"].index(selected)
            f["names"].pop(at)
            for rows in [f["rows"], *f["drafts"].values()]:
                for row in rows:
                    row.pop(selected, None)
            for field in ("means", "current_weights", "bounds", "sectors"):
                f[field].pop(selected, None)
            for group in f["groups"]:
                group["investments"] = [name for name in group["investments"] if name != selected]
            f["covariance"].pop(at)
            for row in f["covariance"]:
                row.pop(at)
            f["epoch"] += 1
            st.rerun()


def _import(f, key, purpose):
    file = st.file_uploader("Import Excel / CSV", type=["xlsx", "csv"], key=key+"_file")
    scale = st.radio("Unmarked dated-table values", ["Auto: use % signs or Excel formatting",
                                                   "Percent: 10 means 10%", "Decimal: 0.10 means 10%"],
                     horizontal=True, key=key+"_scale")
    st.caption("Values marked 10% and numeric Excel cells formatted as 10% are always read as 10%. "
               "For plain numbers, choose their scale; the app cannot infer it from their size.")
    if file is None:
        return
    try:
        parsed = parse_portfolio_file(file.getvalue(), file.name,
                                      scale="auto" if scale.startswith("Auto") else
                                            "percent" if scale.startswith("Percent") else "decimal",
                                      purpose=purpose)
    except InputError as exc:
        st.error(str(exc))
        return
    st.info(parsed["note"])
    if parsed["kind"] == "history":
        st.caption("Original values from the file")
        st.dataframe(pd.DataFrame(parsed["original_values"], columns=parsed["names"]).assign(Date=parsed["dates"]),
                     hide_index=True, width="stretch")
        st.caption("Normalized return preview (%)")
        st.dataframe(pd.DataFrame([[value * 100 for value in row] for row in parsed["returns"]],
                                 columns=parsed["names"]).assign(Date=parsed["dates"]),
                     hide_index=True, width="stretch")
        confirmed = st.checkbox("I confirm these columns are " + ("individual investment" if purpose == "investments" else "complete portfolio") + " returns.", key=key+"_confirm")
    else:
        st.dataframe(pd.DataFrame({"Investment": parsed["names"],
                                   "Average return (%)": [parsed["expected_returns"][n]*100 for n in parsed["names"]],
                                   "Current weight (%)": [parsed["current_weights"][n]*100 for n in parsed["names"]]}),
                     hide_index=True, width="stretch")
        st.dataframe(_matrix(parsed["covariance"], parsed["names"]), width="stretch")
        confirmed = True
    if st.button("Accept imported data", key=key+"_accept", disabled=not confirmed):
        f["names"] = parsed["names"]
        f["input_kind"] = parsed["kind"]
        f["source"] = parsed["source"]
        f["import"] = copy.deepcopy(parsed)
        if parsed["frequency"] is not None:
            f["frequency"] = parsed["frequency"]
        if parsed["kind"] == "history":
            f["rows"] = [{"Date": day, **{name: _percent_text(value) for name, value in zip(parsed["names"], values)}}
                         for day, values in zip(parsed["dates"], parsed["returns"])]
            f["drafts"] = {}
            f["means"] = {name: "" for name in f["names"]}
            f["covariance"] = [[""]*len(f["names"]) for _ in f["names"]]
            imported_weights = parsed.get("current_weights") or {}
            f["current_weights"] = {name: _percent_text(imported_weights[name]) if name in imported_weights else ""
                                    for name in f["names"]}
        else:
            f["means"] = {name: _percent_text(parsed["expected_returns"][name]) for name in f["names"]}
            f["covariance"] = [[f"{x:.16g}" for x in row] for row in parsed["covariance"]]
            f["current_weights"] = {name: _percent_text(parsed["current_weights"][name]) for name in f["names"]}
        f["bounds"] = {name: ("0", "100") for name in f["names"]}
        f["sectors"] = {name: "" for name in f["names"]}
        f["groups"] = []
        st.session_state.pop(key+"_basis", None)
        st.session_state.pop(key+"_frequency", None)
        f["epoch"] += 1
        st.rerun()


def _data(f, key, kind):
    with st.container(border=True):
        st.markdown("### Step 1 · Data input")
        left, right = st.columns(2)
        with left:
            choice = st.radio("Data entry", ["Enter manually", "Import Excel / CSV"], horizontal=True, key=key+"_entry")
            if choice == "Import Excel / CSV":
                _import(f, key, "investments" if kind == "markowitz" else "portfolios")
        with right:
            if kind == "markowitz":
                kind_choice = st.radio("Input basis", ["Historical investment returns", "Expected returns and covariance"],
                                       index=0 if f["input_kind"] == "history" else 1,
                                       key=f"{key}_basis_{f['epoch']}")
                picked = "history" if kind_choice.startswith("Historical") else "estimates"
                if picked != f["input_kind"]:
                    f["input_kind"] = picked
                    f["epoch"] += 1
                    st.rerun()
            else:
                f["input_kind"] = "history"
            _frequency(f, key)
            if f["input_kind"] == "history":
                _starting_period(f, key)


def _markowitz_editors(f, key):
    setup, observations = st.columns([1, 1.55], gap="small")
    with setup:
        st.markdown("**Investments and current allocation**")
        _investment_editor(f, key)
    with observations:
        if f["input_kind"] == "history":
            st.markdown("**Historical investment returns (%)**")
            _table(f, key)
        else:
            st.caption("Expected returns are percentages per selected period: 10 means 10%. Covariance is decimal return squared: enter 0.04 for a 20% volatility.")
            st.markdown("**Covariance matrix input (decimal return squared)**")
            st.caption("Enter matching values on both sides of the diagonal. Asymmetric or invalid matrices are rejected.")
            matrix = pd.DataFrame([{ "Investment": name, **dict(zip(f["names"], row))}
                                   for name, row in zip(f["names"], f["covariance"])]).astype(str)
            edited_matrix = st.data_editor(matrix, hide_index=True, num_rows="fixed", width="stretch",
                                           disabled=["Investment"], key=f"{key}_cov_matrix_{f['epoch']}")
            f["covariance"] = [[str(row[name]) for name in f["names"]]
                               for row in edited_matrix.fillna("").to_dict("records")]


def _inputs(f):
    names = f["names"]
    if f["input_kind"] == "history":
        dates, values = [], []
        for row in f["rows"]:
            try:
                dates.append(date.fromisoformat(str(row["Date"])).isoformat())
            except ValueError as exc:
                raise InputError("Every date must be YYYY-MM-DD.") from exc
            values.append([_percent(row.get(name, ""), f"{name} on {dates[-1]}") for name in names])
        if dates != sorted(set(dates)):
            raise InputError("Return dates must be unique and increasing.")
        return {"kind": "history", "source": f["source"], "names": names[:], "frequency": f["frequency"],
                "dates": dates, "returns": values, "original_import": copy.deepcopy(f["import"])}
    means = {name: _percent(f["means"].get(name, ""), f"Expected return for {name}") for name in names}
    try:
        matrix = [[float(str(x).strip()) for x in row] for row in f["covariance"]]
    except ValueError as exc:
        raise InputError("Complete every covariance cell in decimal return squared units.") from exc
    return {"kind": "estimates", "source": f["source"], "names": names[:], "frequency": f["frequency"],
            "expected_returns": means, "covariance": matrix, "original_import": copy.deepcopy(f["import"])}


def _analysis(f, mode):
    inputs = _inputs(f)
    weights = None
    if inputs["kind"] == "estimates" or any(str(x).strip() for x in f["current_weights"].values()):
        entered = [str(f["current_weights"].get(name, "")).strip() for name in inputs["names"]]
        if any(entered):
            if not all(entered):
                raise InputError("Enter all current weights or leave all blank.")
            weights = {name: _percent(value, f"Current weight for {name}") for name, value in zip(inputs["names"], entered)}
    rf = None if not str(f["risk_free"]).strip() else _percent(f["risk_free"], "Annual effective risk-free rate")
    if inputs["kind"] == "history":
        analysis = analyze_optimization_inputs(names=inputs["names"], frequency=inputs["frequency"],
            dates=inputs["dates"], returns=inputs["returns"], current_weights=weights,
            risk_free_annual_rate=rf, mode=mode)
    else:
        analysis = analyze_optimization_inputs(names=inputs["names"], frequency=inputs["frequency"],
            expected_returns=inputs["expected_returns"], covariance=inputs["covariance"],
            current_weights=weights, risk_free_annual_rate=rf, mode=mode)
    if not analysis.ok:
        raise InputError(analysis.message)
    return inputs, analysis


def _review(analysis, *, covariance_is_input=False):
    d = analysis.diagnostics
    rows = [{"Investment": name, "Expected return": _pct(d["expected_asset_returns"][name]),
             "Current weight": _pct(d["current_weights"][name]) if d["current_weights"] else "—",
             "Volatility": _pct(d["asset_volatility"][name])}
            for name in d["assets"]]
    left, middle, right = st.columns([1.5, 1, 1])
    with left:
        st.markdown("**Investment summary**")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with middle:
        if not covariance_is_input:
            st.markdown("**Covariance (decimal return squared)**")
            st.dataframe(_matrix(d["covariance"], d["assets"]), width="stretch")
    with right:
        st.markdown("**Correlation**")
        st.dataframe(_matrix(d["correlation"], d["assets"], correlation=True), width="stretch")


def _settings(f, key, mode):
    st.markdown("### Step 3 · Optimization settings")
    options = ["Minimum Variance", "Maximum Sharpe Ratio", "Target Return", "Efficient Frontier"]
    f["objective"] = st.radio("Objective", options, index=options.index(f["objective"]),
                              horizontal=True, key=key+"_objective")
    if f["objective"] == "Target Return":
        f["target"] = st.text_input(f"Target return per {f['frequency'][:-2] if f['frequency']=='yearly' else 'month'} (%)",
                                    value=f["target"], key=key+"_target")
    if f["objective"] == "Maximum Sharpe Ratio":
        f["risk_free"] = st.text_input("Annual effective risk-free rate (%)", value=f["risk_free"], key=key+"_rf")
    else:
        with st.expander("Optional risk-free rate for Sharpe marker"):
            f["risk_free"] = st.text_input("Annual effective risk-free rate (%)", value=f["risk_free"], key=key+"_rf")
    st.markdown("### Step 4 · Portfolio constraints")
    limits, groups_panel, exposure = st.columns([1.15, 1.15, 1])
    with limits:
        with st.container(border=True):
            st.markdown("**A · Individual investment limits**")
            f["allow_short"] = st.checkbox("Allow short selling", value=f["allow_short"], key=key+"_short")
            bounds_table = pd.DataFrame([{"Investment": name,
                                          "Minimum weight (%)": f["bounds"].get(name, ("0", "100"))[0],
                                          "Maximum weight (%)": f["bounds"].get(name, ("0", "100"))[1]}
                                         for name in f["names"]])
            edited_bounds = st.data_editor(bounds_table, hide_index=True, num_rows="fixed", width="stretch",
                                           disabled=["Investment"], key=f"{key}_bounds_{f['epoch']}")
            f["bounds"] = {str(row["Investment"]): (str(row["Minimum weight (%)"]), str(row["Maximum weight (%)"]))
                           for row in edited_bounds.to_dict("records")}
    with groups_panel:
        with st.container(border=True):
            st.markdown("**B · Custom group constraints**")
            for group in list(f["groups"]):
                identifier = group["id"]
                group["name"] = st.text_input("Group name", value=group["name"], key=f"{key}_group_name_{identifier}")
                if st.button("Remove Group", key=f"{key}_group_remove_{identifier}"):
                    f["groups"] = [item for item in f["groups"] if item["id"] != identifier]
                    st.rerun()
                group["investments"] = st.multiselect("Investments in " + (group["name"] or "this group"),
                    options=f["names"], default=[name for name in group["investments"] if name in f["names"]],
                    format_func=lambda name: f"{name} ({f['sectors'][name]})" if f["sectors"].get(name) else name,
                    key=f"{key}_group_members_{identifier}")
                group_left, group_right = st.columns(2)
                group["maximum"] = group_left.text_input("Maximum combined weight (%)", value=group["maximum"],
                                                          key=f"{key}_group_max_{identifier}")
                group["minimum"] = group_right.text_input("Minimum combined weight (%) — optional", value=group["minimum"],
                                                           key=f"{key}_group_min_{identifier}")
            if st.button("Add Group", key=key+"_group_add"):
                f["group_counter"] += 1
                f["groups"].append({"id": f["group_counter"], "name": "", "investments": [],
                                    "minimum": "", "maximum": "100"})
                st.rerun()
    with exposure:
        with st.container(border=True):
            st.markdown("**C · Advanced exposure settings**")
            with st.expander("Gross, net, cash and funding"):
                f["gross"] = st.text_input("Gross exposure cap (%)", value=f["gross"], key=key+"_gross")
                f["net_min"] = st.text_input("Minimum net risky exposure (%)", value=f["net_min"], key=key+"_netmin")
                f["net_max"] = st.text_input("Maximum net risky exposure (%)", value=f["net_max"], key=key+"_netmax")
                f["allow_cash"] = st.checkbox("Allow cash or funding", value=f["allow_cash"], key=key+"_cash")
                if f["allow_cash"]:
                    f["cash_yield"] = st.text_input("Annual effective cash yield (%)", value=f["cash_yield"], key=key+"_yield")
                    f["funding_rate"] = st.text_input("Annual effective funding rate (%) — required for borrowing",
                                                       value=f["funding_rate"], key=key+"_funding")
            compare_baseline = st.checkbox("Compare with long-only, fully invested baseline", key=key+"_baseline")
            st.caption("Net portfolio allocation is 100%. Cash or funding covers the remainder when enabled.")
    try:
        lower = {name: _percent(f["bounds"][name][0], f"{name} minimum") for name in f["names"]}
        upper = {name: _percent(f["bounds"][name][1], f"{name} maximum") for name in f["names"]}
        groups = [{"name": group["name"], "investments": group["investments"],
                   "minimum": None if not group["minimum"].strip() else _percent(group["minimum"], group["name"]+" minimum"),
                   "maximum": _percent(group["maximum"], group["name"]+" maximum")}
                  for group in f["groups"]]
        gross = _percent(f["gross"], "Gross exposure cap")
        net_min = _percent(f["net_min"], "Minimum net risky exposure")
        net_max = _percent(f["net_max"], "Maximum net risky exposure")
        cash_yield = _percent(f["cash_yield"], "Cash yield") if f["allow_cash"] else None
        funding_rate = _percent(f["funding_rate"], "Funding rate") if f["funding_rate"].strip() and f["allow_cash"] else None
        status = validate_portfolio_constraints(f["names"], lower_bounds=lower, upper_bounds=upper,
            group_constraints=groups, allow_short=f["allow_short"], gross_cap=gross,
            net_min=net_min, net_max=net_max, allow_cash=f["allow_cash"],
            funding_annual_rate=funding_rate)
        if not status.ok:
            raise InputError(status.message)
    except (InputError, ValueError, KeyError) as exc:
        st.error("Invalid constraints: " + str(exc))
        return None, compare_baseline
    st.success("Valid constraints · allocation and all custom groups are jointly feasible.")
    return {"mode": "Advanced", "execution_profile": mode,
            "lower_bounds": lower, "upper_bounds": upper, "group_constraints": groups,
            "allow_short": f["allow_short"], "gross_cap": gross, "net_min": net_min, "net_max": net_max,
            "allow_cash": f["allow_cash"], "cash_annual_yield": cash_yield,
            "funding_annual_rate": funding_rate}, compare_baseline


def _markowitz_results(f):
    saved = f["result"]
    analysis, solution, frontier, baseline, inputs = (saved[key] for key in ("analysis", "solution", "frontier", "baseline", "inputs"))
    d, opt = analysis.diagnostics, solution.diagnostics
    st.markdown("### Step 6 · Results")
    names = d["assets"]
    weights = [{"Investment": name, "Current (%)": _pct(d["current_weights"][name]) if d["current_weights"] else "—",
                "Optimized (%)": _pct(opt["weights"][name]),
                "Change (pp)": f"{(opt['weights'][name]-d['current_weights'][name])*100:+.4f}"
                               if d["current_weights"] else "—",
                "Baseline (%)": _pct(baseline.diagnostics["weights"][name]) if baseline else "—"} for name in names]
    st.dataframe(pd.DataFrame(weights), hide_index=True, width="stretch")
    first, second, third, fourth = st.columns(4)
    first.metric("Expected return", _pct(opt["expected_return"]))
    second.metric("Volatility", _pct(opt["volatility"]))
    third.metric("Estimated Sharpe", _ratio(opt["estimated_sharpe"]))
    fourth.metric("Variance", _decimal(opt['variance']))
    st.caption("Estimates are per selected return period. Future outcomes can differ.")
    if frontier is not None and frontier.ok:
        if len(frontier.diagnostics["points"]) == 1:
            st.caption("The efficient set has one distinct portfolio under these inputs and constraints.")
        rows = [{"Volatility (%)": point["volatility"]*100, "Return (%)": point["return"]*100,
                 "Type": "Efficient frontier"} for point in frontier.diagnostics["points"]]
        points = pd.DataFrame(rows)
        line = alt.Chart(points).mark_line(point=True).encode(x="Volatility (%):Q", y="Return (%):Q", tooltip=["Volatility (%)", "Return (%)"])
        markers = [{"Volatility (%)": frontier.diagnostics["minimum_variance"]["volatility"]*100,
                    "Return (%)": frontier.diagnostics["minimum_variance"]["expected_return"]*100,
                    "Portfolio": "Minimum variance"}]
        if saved["sharpe_marker"] is not None:
                markers.append({"Volatility (%)": saved["sharpe_marker"]["volatility"]*100,
                                "Return (%)": saved["sharpe_marker"]["expected_return"]*100,
                                "Portfolio": "Maximum Sharpe"})
        if d["current_weights"]:
            current = [d["current_weights"][name] for name in names]
            current_return = sum(weight*d["expected_asset_returns"][name] for weight, name in zip(current, names))
            current_variance = sum(current[i]*d["covariance"][i][j]*current[j]
                                   for i in range(len(names)) for j in range(len(names)))
            if current_variance >= -1e-12:
                markers.append({"Volatility (%)": math.sqrt(max(current_variance, 0))*100,
                                "Return (%)": current_return*100, "Portfolio": "Current portfolio"})
        dots = alt.Chart(pd.DataFrame(markers)).mark_point(size=140, filled=True).encode(
            x="Volatility (%):Q", y="Return (%):Q", color="Portfolio:N", tooltip=["Portfolio", "Volatility (%)", "Return (%)"])
        st.altair_chart(line+dots, width="stretch")
    if saved.get("sharpe_marker_error"):
        st.warning("Maximum Sharpe marker unavailable: " + saved["sharpe_marker_error"])
    with st.expander("Constraint, baseline and solver diagnostics"):
        settings = saved["settings"]
        st.caption("Net risky allocation: " + ("within the entered exposure range; cash or funding is the remainder."
                   if settings.get("allow_cash") else "100% fully invested in the listed investments."))
        for group in settings.get("group_constraints", []):
            floor = "" if group["minimum"] is None else f"; minimum {_pct(group['minimum'])}"
            st.caption(f"{group['name']}: {', '.join(group['investments'])}; maximum {_pct(group['maximum'])}{floor}.")
        st.write(f"Solver: {opt['solver']} — {opt['solver_message']}; certified feasible: {opt['feasible']}.")
        st.dataframe(pd.DataFrame([{"Constraint": name, "Residual (decimal)": value}
                                  for name, value in opt["constraint_residuals"].items()]), hide_index=True)
        if baseline:
            st.caption("Baseline: Standard long-only, fully invested, no Advanced bounds or sector caps.")
    for warning in dict.fromkeys((*analysis.warnings, *solution.warnings)):
        st.warning("Estimation uncertainty: " + warning)
    with st.expander("Formula and numerical details"):
        w = [opt["weights"][name] for name in names]
        st.code("Expected return = wᵀμ; variance = wᵀΣw; volatility = √variance; Sharpe = (return − matching-period risk-free rate) / volatility.\n"
                f"w = {w}\nμ = {[d['expected_asset_returns'][name] for name in names]}\nΣ = {d['covariance']}\n"
                f"wᵀΣw = {opt['variance']:.16g}\nRisk-free per period = {d['risk_free_period_return']}")
    st.download_button("Export to Excel", data=f["export"], file_name="Portfolio_Markowitz_Analysis.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="week11_markowitz_export")


def render_markowitz(mode="Standard"):
    key = "week11_markowitz"
    f = _state("markowitz")
    _portfolio_style()
    st.subheader("Markowitz Optimization")
    st.caption("Optimize weights between individual investments using historical returns or period-matched estimates.")
    try:
        _data(f, key, "markowitz")
        with st.container(border=True):
            st.markdown("### Step 2 · Review data")
            _markowitz_editors(f, key)
            analysis = None
            try:
                _, analysis = _analysis(f, mode)
            except InputError as exc:
                st.info(str(exc))
            if analysis is not None:
                _review(analysis, covariance_is_input=f["input_kind"] == "estimates")
                if f["result"] is None or f["signature"] != _signature(f, mode):
                    for warning in analysis.warnings:
                        st.warning("Estimation uncertainty: " + warning)
        with st.container(border=True):
            settings, compare_baseline = _settings(f, key, mode)
        with st.container(border=True):
            st.markdown("### Step 5 · Optimize")
            left, right = st.columns([2, 1])
            optimize_clicked = left.button("Optimize Portfolio", type="primary",
                                           key=key+"_optimize", disabled=settings is None)
            if right.button("Reset", key=key+"_reset"):
                _reset("markowitz")
        if optimize_clicked:
            inputs, analysis = _analysis(f, mode)
            objective = {"Minimum Variance": "minimum_variance", "Maximum Sharpe Ratio": "maximum_estimated_sharpe",
                         "Target Return": "target_return_minimum_variance", "Efficient Frontier": "minimum_variance"}[f["objective"]]
            opts = dict(settings)
            if f["objective"] == "Target Return":
                opts["target_return"] = _percent(f["target"], "Target return")
            solution = optimize_portfolio(analysis, objective=objective, **opts)
            if not solution.ok:
                raise InputError(solution.message)
            frontier_settings = dict(settings)
            frontier = efficient_frontier(analysis, points=10, **frontier_settings)
            if not frontier.ok:
                raise InputError(frontier.message)
            baseline = None
            if compare_baseline:
                base_opts = {"mode": "Standard"}
                if f["objective"] == "Target Return":
                    base_opts["target_return"] = opts["target_return"]
                baseline = optimize_portfolio(analysis, objective=objective, **base_opts)
                if not baseline.ok:
                    raise InputError("Baseline optimization failed: "+baseline.message)
            sharpe_marker = None
            sharpe_marker_error = None
            if analysis.diagnostics["risk_free_period_return"] is not None:
                marker_result = solution if objective == "maximum_estimated_sharpe" else optimize_portfolio(
                    analysis, objective="maximum_estimated_sharpe", **frontier_settings)
                if marker_result.ok:
                    sharpe_marker = marker_result.diagnostics
                else:
                    sharpe_marker_error = marker_result.message
            f["result"] = {"analysis": analysis, "solution": solution, "frontier": frontier,
                           "baseline": baseline, "inputs": inputs, "settings": frontier_settings,
                           "sharpe_marker": sharpe_marker, "sharpe_marker_error": sharpe_marker_error}
            inputs["objective"] = f["objective"]
            inputs["constraints"] = opts
            f["export"] = portfolio_excel_bytes("Markowitz Optimization", inputs, analysis, solution, frontier, baseline)
            f["signature"] = _signature(f, mode)
        if f["result"] is not None:
            if f["signature"] == _signature(f, mode):
                with st.container(border=True):
                    _markowitz_results(f)
            else:
                st.info("Inputs changed. Optimize again to refresh results and Excel export.")
    except (InputError, ValueError, KeyError) as exc:
        st.error(str(exc))
        if st.button("Reset", key=key+"_reset_after_error"):
            _reset("markowitz")


def render_compare(mode="Standard"):
    key = "week11_compare"
    f = _state("compare")
    st.subheader("Compare Portfolios")
    st.caption("Compare two or more complete portfolio return histories on the same dated periods.")
    try:
        _data(f, key, "compare")
        with st.container(border=True):
            st.markdown("### Step 2 · Create portfolios")
            _names(f, key, "Portfolio")
        with st.container(border=True):
            st.markdown("### Step 3 · Enter dated returns")
            _table(f, key)
        with st.container(border=True):
            st.markdown("### Step 4 · Calculate")
            risk_rate, calculate, reset = st.columns([2, 1, 1])
            f["risk_free"] = risk_rate.text_input("Annual effective risk-free rate (%) — optional for Sharpe",
                                                 value=f["risk_free"], key=key+"_rf")
            calculate_clicked = calculate.button("Calculate Analysis", type="primary", key=key+"_calculate")
            if reset.button("Reset", key=key+"_reset"):
                _reset("compare")
        if calculate_clicked:
            inputs = _inputs(f)
            rf = None if not f["risk_free"].strip() else _percent(f["risk_free"], "Risk-free rate")
            comparison = compare_return_histories(names=inputs["names"], dates=inputs["dates"],
                returns=inputs["returns"], frequency=inputs["frequency"], risk_free_annual_rate=rf)
            if not comparison.ok:
                raise InputError(comparison.message)
            f["result"] = {"inputs": inputs, "analysis": comparison}
            f["export"] = portfolio_excel_bytes("Compare Portfolios", inputs, comparison)
            f["signature"] = _signature(f, mode)
        if f["result"] is not None:
            if f["signature"] != _signature(f, mode):
                st.info("Inputs changed. Calculate again to refresh results and Excel export.")
                return
            saved = f["result"]
            d = saved["analysis"].diagnostics
            st.markdown("### Step 5 · Results")
            st.dataframe(pd.DataFrame([{"Portfolio": item["name"], "Average return": _pct(item["mean"]),
                "Cumulative return": _pct(item["cumulative"]), "Sample variance": _decimal(item['variance']),
                "Volatility": _pct(item["volatility"]), "Sharpe": _ratio(item["sharpe"])}
                for item in d["comparison"]]), hide_index=True, width="stretch")
            covariance_panel, correlation_panel = st.columns(2)
            with covariance_panel:
                st.markdown("**Covariance (decimal return squared)**")
                st.dataframe(_matrix(d["covariance"], d["assets"]), width="stretch")
            with correlation_panel:
                st.markdown("**Correlation**")
                st.dataframe(_matrix(d["correlation"], d["assets"], correlation=True), width="stretch")
            chart = pd.DataFrame({item["name"]: item["path"] for item in d["comparison"]}, index=d["dates"])
            st.markdown("**Historical cumulative return**")
            st.line_chart(chart, width="stretch")
            st.caption("The chart shows compounded cumulative returns. A higher historical return does not establish a universally best portfolio.")
            for warning in saved["analysis"].warnings:
                st.warning(warning)
            with st.expander("Formula and calculation details"):
                st.code("Average = sum(period returns) / n\nCumulative = product(1 + period return) − 1\n"
                        "Sample variance and covariance divide by n − 1.\n"
                        "Volatility = √variance; Sharpe = (average − period-matched risk-free rate) / volatility.\n"
                        f"Validated dates = {d['dates']}\nCovariance = {d['covariance']}")
            st.download_button("Export to Excel", data=f["export"], file_name="Portfolio_Comparison.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=key+"_export")
    except (InputError, ValueError, KeyError) as exc:
        st.error(str(exc))
