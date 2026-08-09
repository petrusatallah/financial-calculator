import math
import streamlit as st


st.set_page_config(page_title="Financial Calculator", layout="wide")

_CSS = """
<style>
body {background-color: #0b1220; color: #d1fae5;}
.stApp { background-color: #0b1220; }
.section { background-color: #0f1724; padding: 18px; border-radius: 12px; }
.result-card { background-color: #071019; padding: 18px; border-radius: 12px; border: 1px solid rgba(16,185,129,0.08); }
.round-input { border-radius: 8px; }
div.stButton>button:first-child { background-color: #16a34a; color: white; border-radius: 8px; padding: 8px 18px; }
.small-muted { color: #94a3b8; font-size:12px }
</style>
"""

st.markdown(_CSS, unsafe_allow_html=True)

st.title("Financial Calculator")

tabs = st.tabs(["Compounding", "Bond", "NPV", "IRR"])


def _parse_optional_number(s: str):
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None


def fv_from_inputs(pv, r, n, pmt):
    # r is periodic rate (decimal), n is total periods
    if abs(r) < 1e-12:
        return pv + pmt * n
    return pv * (1 + r) ** n + pmt * (((1 + r) ** n - 1) / r)


def pv_from_inputs(fv, r, n, pmt):
    if abs(r) < 1e-12:
        return fv - pmt * n
    return (fv - pmt * (((1 + r) ** n - 1) / r)) / ((1 + r) ** n)


def periods_from_inputs(pv, fv, r, pmt):
    # returns N (total periods)
    if abs(r) < 1e-12:
        if abs(pmt) < 1e-12:
            raise ValueError("Rate is zero and PMT is zero; cannot solve for periods")
        return (fv - pv) / pmt
    a = pv + pmt / r
    b = fv + pmt / r
    if a <= 0 or b <= 0:
        raise ValueError("Values lead to non-positive log argument; check inputs")
    return math.log(b / a) / math.log(1 + r)


def solve_rate_bisection(pv, fv, n, pmt, tol=1e-12, maxiter=200):
    # solve for periodic rate r using bisection on reasonable interval
    def f(r):
        return fv_from_inputs(pv, r, n, pmt) - fv

    low = -0.999999
    high = 10.0
    f_low = f(low)
    f_high = f(high)
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if f_low * f_high > 0:
        # try expanding high
        for h in [50, 100, 500]:
            f_h = f(h)
            if f_low * f_h <= 0:
                high = h
                f_high = f_h
                break
        else:
            # fallback to secant-like iteration
            r0 = (fv / pv) ** (1 / n) - 1 if pv > 0 else 0.05
            r1 = r0 * 1.1 if r0 != 0 else 0.05
            for _ in range(maxiter):
                try:
                    f0 = f(r0)
                    f1 = f(r1)
                    if abs(f1 - f0) < 1e-16:
                        break
                    r2 = r1 - f1 * (r1 - r0) / (f1 - f0)
                except Exception:
                    break
                r0, r1 = r1, r2
                if abs(f(r1)) < tol:
                    return r1
            raise ValueError("Failed to bracket root for rate; try different inputs")

    for _ in range(maxiter):
        mid = (low + high) / 2
        f_mid = f(mid)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    raise ValueError("Rate solver did not converge")


def bond_price(face, coupon_rate_pct, yield_rate_pct, years, payments_per_year):
    coupon = face * coupon_rate_pct / 100.0 / payments_per_year
    r = yield_rate_pct / 100.0 / payments_per_year
    n = int(years * payments_per_year)
    if n <= 0:
        raise ValueError("Years to maturity must be positive")
    if abs(r) < 1e-12:
        return coupon * n + face
    discount_factors = [(1 + r) ** t for t in range(1, n + 1)]
    pv_coupons = sum(coupon / df for coupon, df in zip([coupon] * n, discount_factors))
    pv_face = face / discount_factors[-1]
    return pv_coupons + pv_face


def solve_ytm(face, coupon_rate_pct, price, years, payments_per_year, tol=1e-12, maxiter=200):
    coupon = face * coupon_rate_pct / 100.0 / payments_per_year
    n = int(years * payments_per_year)
    if n <= 0:
        raise ValueError("Years to maturity must be positive")

    def f(r):
        if abs(r) < 1e-16:
            return coupon * n + face - price
        discount_factors = [(1 + r) ** t for t in range(1, n + 1)]
        pv_coupons = sum(coupon / df for df in discount_factors)
        pv_face = face / discount_factors[-1]
        return pv_coupons + pv_face - price

    low = -0.999999
    high = 1.0
    f_low = f(low)
    f_high = f(high)
    if f_low == 0:
        return low * payments_per_year * 100.0
    if f_high == 0:
        return high * payments_per_year * 100.0
    if f_low * f_high > 0:
        for h in [2.0, 5.0, 10.0, 20.0]:
            f_h = f(h)
            if f_low * f_h <= 0:
                high = h
                f_high = f_h
                break
        else:
            raise ValueError("Cannot bracket YTM; check price and coupon inputs")

    for _ in range(maxiter):
        mid = (low + high) / 2
        f_mid = f(mid)
        if abs(f_mid) < tol:
            return mid * payments_per_year * 100.0
        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    raise ValueError("YTM solver did not converge")


def irr_from_cash_flows(cash_flows, tol=1e-10, maxiter=200):
    if len(cash_flows) < 2:
        raise ValueError("At least two cash flows are required to compute IRR.")

    def npv(rate):
        value = 0.0
        for idx, cf in enumerate(cash_flows):
            value += cf / ((1 + rate) ** idx)
        return value

    # Try to bracket a root
    low = -0.999999
    high = 1.0
    f_low = npv(low)
    f_high = npv(high)
    if f_low == 0:
        return low
    if f_high == 0:
        return high

    if f_low * f_high > 0:
        for h in [2.0, 5.0, 10.0, 20.0, 50.0, 100.0]:
            f_h = npv(h)
            if f_low * f_h <= 0:
                high = h
                f_high = f_h
                break
        else:
            raise ValueError("IRR cannot be found: cash flows may not change sign or are invalid.")

    for _ in range(maxiter):
        mid = (low + high) / 2
        f_mid = npv(mid)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    raise ValueError("IRR solver did not converge")


with tabs[0]:
    st.markdown("""
    <div class="section">
    """, unsafe_allow_html=True)

    left, right = st.columns([2, 1])

    with left:
        st.subheader("Compounding")
        pv_in = st.text_input("Present Value (PV)", key="pv_input")
        fv_in = st.text_input("Future Value (FV)", key="fv_input")
        rate_in = st.text_input("Interest Rate (% per year)", key="rate_input")
        years_in = st.text_input("Years / Periods (years)", key="years_input")
        pmt_in = st.text_input("Payment (PMT) per period", value="0", key="pmt_input")
        freq = st.number_input("Payment Frequency (periods per year)", min_value=1, value=1, step=1, key="freq_input")

        st.markdown("<div class='small-muted'>Leave exactly ONE of PV, FV, Rate, Years empty and press Compute.</div>", unsafe_allow_html=True)

        compute = st.button("Compute", key="compute_btn")

    with right:
        st.markdown("<div class='result-card'>", unsafe_allow_html=True)
        result_area = st.empty()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if compute:
        pv = _parse_optional_number(pv_in)
        fv = _parse_optional_number(fv_in)
        rate = _parse_optional_number(rate_in)
        years = _parse_optional_number(years_in)
        pmt = _parse_optional_number(pmt_in)
        if pmt is None:
            pmt = 0.0

        # Identify how many main vars are empty
        main = {"PV": pv, "FV": fv, "Rate": rate, "Years": years}
        empty = [k for k, v in main.items() if v is None or (isinstance(v, float) and math.isnan(v))]
        if len(empty) != 1:
            result_area.error("Please leave exactly ONE of PV, FV, Rate, Years empty.")
        else:
            missing = empty[0]
            try:
                freq_i = int(freq)
                if freq_i <= 0:
                    raise ValueError
            except Exception:
                result_area.error("Payment Frequency must be a positive integer.")
                freq_i = None

            if freq_i is not None:
                try:
                    if missing == "FV":
                        # compute FV
                        r = (rate or 0.0) / 100.0 / freq_i
                        N = (years or 0.0) * freq_i
                        fv_res = fv_from_inputs(pv or 0.0, r, N, pmt or 0.0)
                        result_area.success(f"Computed FV: {fv_res:,.2f}")
                    elif missing == "PV":
                        r = (rate or 0.0) / 100.0 / freq_i
                        N = (years or 0.0) * freq_i
                        pv_res = pv_from_inputs(fv or 0.0, r, N, pmt or 0.0)
                        result_area.success(f"Computed PV: {pv_res:,.2f}")
                    elif missing == "Years":
                        r = (rate or 0.0) / 100.0 / freq_i
                        # solve for N then convert to years
                        N = periods_from_inputs(pv or 0.0, fv or 0.0, r, pmt or 0.0)
                        years_res = N / freq_i
                        result_area.success(f"Computed Years: {years_res:,.6g}")
                    elif missing == "Rate":
                        N = (years or 0.0) * freq_i
                        # solve for periodic r
                        r_sol = solve_rate_bisection(pv or 0.0, fv or 0.0, N, pmt or 0.0)
                        annual_rate_pct = r_sol * freq_i * 100.0
                        result_area.success(f"Computed Annual Rate: {annual_rate_pct:.6g} %")
                    else:
                        result_area.error("Unknown computation requested")
                except Exception as e:
                    result_area.error(f"Computation error: {e}")

with tabs[1]:
    st.markdown("""
    <div class="section">
    """, unsafe_allow_html=True)

    left, right = st.columns([2, 1])

    with left:
        st.subheader("Bond")
        face_in = st.text_input("Face Value", key="bond_face_input")
        coupon_in = st.text_input("Coupon Rate (%)", key="bond_coupon_input")
        yield_in = st.text_input("Market / Yield Rate (%)", key="bond_yield_input")
        years_in = st.text_input("Years to Maturity", key="bond_years_input")
        payments_in = st.number_input("Payments per Year", min_value=1, value=1, step=1, key="bond_payments_input")
        price_in = st.text_input("Bond Price", key="bond_price_input")

        st.markdown("<div class='small-muted'>Leave Bond Price empty to compute price, or enter it and leave Yield empty to compute YTM.</div>", unsafe_allow_html=True)

        compute_bond = st.button("Compute", key="bond_compute_btn")

    with right:
        st.markdown("<div class='result-card'>", unsafe_allow_html=True)
        bond_result = st.empty()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if compute_bond:
        face = _parse_optional_number(face_in)
        coupon = _parse_optional_number(coupon_in)
        yield_rate = _parse_optional_number(yield_in)
        years = _parse_optional_number(years_in)
        payments = payments_in
        price = _parse_optional_number(price_in)

        if face is None or coupon is None or years is None or payments is None:
            bond_result.error("Please enter Face Value, Coupon Rate, Years, and Payments per Year.")
        else:
            missing = []
            if price is None:
                missing.append("Price")
            if yield_rate is None:
                missing.append("Yield")

            if len(missing) != 1:
                bond_result.error("Leave exactly one of Bond Price or Yield empty.")
            else:
                try:
                    if missing[0] == "Price":
                        price_res = bond_price(face, coupon, yield_rate or 0.0, years, payments)
                        bond_result.success(f"Computed Bond Price: {price_res:,.2f}")
                    else:
                        ytm_res = solve_ytm(face, coupon, price or 0.0, years, payments)
                        bond_result.success(f"Computed YTM: {ytm_res:.6g} %")
                except Exception as e:
                    bond_result.error(f"Computation error: {e}")

if "npv_cash_flows" not in st.session_state:
    st.session_state.npv_cash_flows = ["", "", ""]

with tabs[2]:
    st.markdown("""
    <div class="section">
    """, unsafe_allow_html=True)

    left, right = st.columns([2, 1])

    with left:
        st.subheader("NPV")
        btn_cols = st.columns([1, 1, 1, 1, 1])
        add_cf = btn_cols[0].button("Add Cash Flow", key="npv_add")
        remove_cf = btn_cols[1].button("Remove Cash Flow", key="npv_remove")
        reset_cf = btn_cols[2].button("Reset Cash Flows", key="npv_reset")
        compute_npv = btn_cols[3].button("Compute NPV", key="npv_compute")
        clear_npv = btn_cols[4].button("Clear", key="npv_clear")

        discount_rate_in = st.text_input("Discount Rate (%)", key="npv_discount_rate")

        st.markdown("<div class='small-muted'>Manage cash flows with Add / Remove / Reset and compute NPV for the entered series.</div>", unsafe_allow_html=True)

        # Manage session state list length and values
        if add_cf:
            st.session_state.npv_cash_flows.append("")
        if remove_cf:
            if len(st.session_state.npv_cash_flows) > 1:
                removed_index = len(st.session_state.npv_cash_flows) - 1
                st.session_state.npv_cash_flows.pop()
                st.session_state.pop(f"npv_cf_{removed_index}", None)
            else:
                st.warning("Cannot remove the final cash flow entry.")
        if reset_cf:
            st.session_state.npv_cash_flows = ["", "", ""]
            for idx in range(10):
                st.session_state.pop(f"npv_cf_{idx}", None)
        if clear_npv:
            st.session_state.npv_cash_flows = ["", "", ""]
            st.session_state.npv_discount_rate = ""
            for idx in range(10):
                st.session_state.pop(f"npv_cf_{idx}", None)

        cash_flows = []
        for idx in range(len(st.session_state.npv_cash_flows)):
            value = st.text_input(f"Cash Flow {idx}", key=f"npv_cf_{idx}")
            cash_flows.append(value)

    with right:
        st.markdown("<div class='result-card'>", unsafe_allow_html=True)
        npv_result = st.empty()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if compute_npv:
        discount_rate = _parse_optional_number(discount_rate_in)
        if discount_rate is None:
            npv_result.error("Enter a valid discount rate.")
        else:
            try:
                r = discount_rate / 100.0
                npv = 0.0
                for idx, cf_value in enumerate(cash_flows):
                    cf = _parse_optional_number(cf_value)
                    if cf is None:
                        cf = 0.0
                    if idx == 0:
                        npv += cf
                    else:
                        npv += cf / ((1 + r) ** idx)
                npv_result.success(f"Computed NPV: {npv:,.2f}")
            except Exception as e:
                npv_result.error(f"Computation error: {e}")

if "irr_cash_flows" not in st.session_state:
    st.session_state.irr_cash_flows = ["", "", ""]

with tabs[3]:
    st.markdown("""
    <div class="section">
    """, unsafe_allow_html=True)

    left, right = st.columns([2, 1])

    with left:
        st.subheader("IRR")
        btn_cols = st.columns([1, 1, 1, 1, 1])
        add_cf = btn_cols[0].button("Add Cash Flow", key="irr_add")
        remove_cf = btn_cols[1].button("Remove Cash Flow", key="irr_remove")
        reset_cf = btn_cols[2].button("Reset Cash Flows", key="irr_reset")
        compute_irr = btn_cols[3].button("Compute IRR", key="irr_compute")
        clear_irr = btn_cols[4].button("Clear", key="irr_clear")

        st.markdown("<div class='small-muted'>Manage cash flows and compute IRR for the entered series.</div>", unsafe_allow_html=True)

        if add_cf:
            st.session_state.irr_cash_flows.append("")
        if remove_cf:
            if len(st.session_state.irr_cash_flows) > 1:
                removed_index = len(st.session_state.irr_cash_flows) - 1
                st.session_state.irr_cash_flows.pop()
                st.session_state.pop(f"irr_cf_{removed_index}", None)
            else:
                st.warning("Cannot remove the final cash flow entry.")
        if reset_cf:
            st.session_state.irr_cash_flows = ["", "", ""]
            for idx in range(20):
                st.session_state.pop(f"irr_cf_{idx}", None)
        if clear_irr:
            st.session_state.irr_cash_flows = ["", "", ""]
            for idx in range(20):
                st.session_state.pop(f"irr_cf_{idx}", None)

        irr_cash_flows = []
        for idx in range(len(st.session_state.irr_cash_flows)):
            value = st.text_input(f"Cash Flow {idx}", key=f"irr_cf_{idx}")
            irr_cash_flows.append(value)

    with right:
        st.markdown("<div class='result-card'>", unsafe_allow_html=True)
        irr_result = st.empty()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if compute_irr:
        try:
            cash_flows = []
            for cf_value in irr_cash_flows:
                cf = _parse_optional_number(cf_value)
                if cf is None:
                    cf = 0.0
                cash_flows.append(cf)
            if len(cash_flows) < 2:
                raise ValueError("At least two cash flows are required.")
            irr_value = irr_from_cash_flows(cash_flows)
            irr_result.success(f"Computed IRR: {irr_value * 100.0:,.6g} %")
        except Exception as e:
            irr_result.error(f"IRR error: {e}")
