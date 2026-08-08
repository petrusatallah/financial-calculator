# ==========================================
# TVM FINANCIAL CALCULATOR APP
# ==========================================

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import openpyxl  # noqa: F401
except ImportError:
    openpyxl = None

# ==========================================
# 1. FINANCE FUNCTIONS
# ==========================================


# Present Value
def Present_value(fv, rate, years, pmt):
    pv_fv = fv / (1 + rate) ** years
    pv_pmt = pmt * ((1 - (1 + rate) ** -years) / rate) if rate != 0 else pmt * years
    return pv_fv + pv_pmt


# Future Value
def Future_value(pv, rate, years, pmt):
    return pv * (1 + rate) ** years + pmt * (((1 + rate) ** years - 1) / rate) if rate != 0 else pv + pmt * years


# NPV
def NPV(rate, cashflows):
    return sum(cashflow / (1 + rate) ** year for year, cashflow in enumerate(cashflows))


# Bond Price
def Bond_price(face_value, coupon_rate, ytm, years, frequency):
    coupon = face_value * coupon_rate / frequency
    periods = years * frequency
    periodic_ytm = ytm / frequency
    pv_coupons = coupon * ((1 - (1 + periodic_ytm) ** -periods) / periodic_ytm) if periodic_ytm != 0 else coupon * periods
    pv_face_value = face_value / ((1 + periodic_ytm) ** periods)
    return pv_coupons + pv_face_value


def compute_irr(cashflows, tolerance=1e-6, max_iterations=100):
    if len(cashflows) < 2:
        return None

    def npv(rate):
        return sum(cf / (1 + rate) ** year for year, cf in enumerate(cashflows))

    lower, upper = -0.9999, 0.9999
    lower_value = npv(lower)
    upper_value = npv(upper)

    if lower_value == 0:
        return lower
    if upper_value == 0:
        return upper

    if lower_value * upper_value > 0:
        for factor in [2, 5, 10, 20, 50]:
            upper *= factor
            upper_value = npv(upper)
            if lower_value * upper_value <= 0:
                break
        else:
            return None

    for _ in range(max_iterations):
        mid = (lower + upper) / 2
        value = npv(mid)
        if abs(value) < tolerance:
            return mid
        if lower_value * value < 0:
            upper, upper_value = mid, value
        else:
            lower, lower_value = mid, value

    return mid

# ==========================================
# 2. APP HELPERS
# ==========================================

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def periodic_rate(rate, frequency):
    return rate / frequency if frequency and frequency != 0 else 0.0


def Present_value(fv, rate, years, pmt, frequency=1):
    periodic = periodic_rate(rate, frequency)
    periods = years * frequency
    pv_fv = fv / (1 + periodic) ** periods if periodic != 0 else fv
    pv_pmt = pmt * ((1 - (1 + periodic) ** -periods) / periodic) if periodic != 0 else pmt * periods
    return pv_fv + pv_pmt


def Future_value(pv, rate, years, pmt, frequency=1):
    periodic = periodic_rate(rate, frequency)
    periods = years * frequency
    if periodic != 0:
        return pv * (1 + periodic) ** periods + pmt * (((1 + periodic) ** periods - 1) / periodic)
    return pv + pmt * periods


def solve_present_value(fv, rate, years, pmt, frequency=1):
    return Present_value(fv, rate, years, pmt, frequency)


def solve_future_value(pv, rate, years, pmt, frequency=1):
    return Future_value(pv, rate, years, pmt, frequency)


def solve_payment(pv, fv, rate, years, frequency=1):
    periodic = periodic_rate(rate, frequency)
    periods = years * frequency
    if periodic != 0:
        numerator = fv - pv * (1 + periodic) ** periods
        denominator = ((1 + periodic) ** periods - 1) / periodic
        return numerator / denominator if denominator != 0 else 0.0
    return fv - pv if periods != 0 else 0.0


def find_root(function, lower, upper, tolerance=1e-8, max_iterations=100):
    f_lower = function(lower)
    f_upper = function(upper)
    if abs(f_lower) < tolerance:
        return lower
    if abs(f_upper) < tolerance:
        return upper
    for factor in [2, 5, 10]:
        if f_lower * f_upper <= 0:
            break
        upper *= factor
        f_upper = function(upper)
    if f_lower * f_upper > 0:
        return None
    for _ in range(max_iterations):
        mid = (lower + upper) / 2
        f_mid = function(mid)
        if abs(f_mid) < tolerance:
            return mid
        if f_lower * f_mid <= 0:
            upper = mid
            f_upper = f_mid
        else:
            lower = mid
            f_lower = f_mid
    return mid

# ==========================================
# 3. CREATE APP WINDOW
# ==========================================

window = tk.Tk()
window.title("TVM Financial Calculator")
window.geometry("720x640")
window.minsize(700, 620)

style = ttk.Style(window)
style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
style.configure("TLabel", font=("Segoe UI", 10))
style.configure("TButton", font=("Segoe UI", 10))
style.configure("TEntry", font=("Segoe UI", 10))

main_frame = ttk.Frame(window, padding=12)
main_frame.pack(fill="both", expand=True)

header_frame = ttk.Frame(main_frame)
header_frame.pack(fill="x")

title_label = ttk.Label(header_frame, text="TVM Financial Calculator", style="Header.TLabel")
name = title_label.pack(side="left")

selected_calculation = tk.StringVar(value="Compounding")
calculations = ["Compounding", "NPV", "IRR", "Bond Price"]

selection_frame = ttk.Frame(main_frame)
selection_frame.pack(fill="x", pady=(10, 4))

calc_label = ttk.Label(selection_frame, text="Calculation type:")
calc_label.grid(row=0, column=0, sticky="w")

calc_menu = ttk.OptionMenu(selection_frame, selected_calculation, calculations[0], *calculations)
calc_menu.grid(row=0, column=1, sticky="w", padx=(8, 0))

result_label = ttk.Label(main_frame, text="Result will appear here.", style="Header.TLabel", anchor="center", wraplength=680)
result_label.pack(fill="x", pady=(10, 12))

input_frame = ttk.Frame(main_frame)
input_frame.pack(fill="both", expand=True)
input_frame.columnconfigure(0, weight=1)

entries = {}
entries_order = []
cashflow_entries = []
cashflow_canvas = None
cashflow_inner_frame = None
cashflow_scrollbar = None
cashflow_window = None

# ------------------------------------------
# CASHFLOW MANAGEMENT
# ------------------------------------------

def update_cashflow_scrollregion():
    if cashflow_canvas:
        cashflow_canvas.update_idletasks()
        cashflow_canvas.configure(scrollregion=cashflow_canvas.bbox("all"))


def add_cashflow():
    global cashflow_inner_frame
    if cashflow_inner_frame is None:
        return

    index = len(cashflow_entries)
    row = ttk.Frame(cashflow_inner_frame)
    row.pack(fill="x", pady=3)

    label = ttk.Label(row, text=f"Cash Flow {index}:")
    label.pack(side="left")

    entry = ttk.Entry(row, width=24)
    entry.pack(side="left", padx=(10, 0))

    cashflow_entries.append(entry)
    bind_cashflow_entry(entry)
    update_cashflow_scrollregion()


def remove_cashflow():
    if cashflow_entries:
        entry = cashflow_entries.pop()
        parent = entry.master
        parent.destroy()
        update_cashflow_scrollregion()

# ------------------------------------------
# IMPORT / EXPORT
# ------------------------------------------

def import_excel():
    if pd is None or openpyxl is None:
        messagebox.showerror("Missing Package", "Please install pandas and openpyxl before importing Excel files.")
        return

    file_path = filedialog.askopenfilename(title="Import Excel", filetypes=[("Excel files", "*.xlsx;*.xls")])
    if not file_path:
        return

    try:
        workbook = pd.ExcelFile(file_path)
    except Exception as err:
        messagebox.showerror("Import Failed", f"Could not read Excel file:\n{err}")
        return

    params = None
    cashflows = None

    if "Parameters" in workbook.sheet_names:
        params = pd.read_excel(workbook, sheet_name="Parameters")
    elif workbook.sheet_names:
        params = pd.read_excel(workbook, sheet_name=workbook.sheet_names[0])

    if "CashFlows" in workbook.sheet_names:
        cashflows = pd.read_excel(workbook, sheet_name="CashFlows")
    elif params is not None and {"Year", "CashFlow"}.issubset(params.columns):
        cashflows = params
        params = None

    choice = selected_calculation.get()

    if choice in ["Compounding", "Bond Price"] and params is not None:
        for field in entries:
            column = field.replace(" (%)", "%")
            if column in params.columns:
                entries[field].delete(0, tk.END)
                entries[field].insert(0, str(params[column].iloc[0]))
        messagebox.showinfo("Import Complete", "Excel values were loaded into the current calculation.")
        return

    if choice in ["NPV", "IRR"]:
        if cashflows is None or "CashFlow" not in cashflows.columns:
            messagebox.showerror("Import Failed", "Excel file must include a CashFlows sheet with a CashFlow column.")
            return

        while cashflow_entries:
            remove_cashflow()

        for value in cashflows["CashFlow"].tolist():
            add_cashflow()
            cashflow_entries[-1].delete(0, tk.END)
            cashflow_entries[-1].insert(0, str(value))

        if choice == "NPV" and params is not None and "Required Return (%)" in params.columns:
            entries["Required Return (%)"].delete(0, tk.END)
            entries["Required Return (%)"].insert(0, str(params["Required Return (%)"].iloc[0]))

        messagebox.showinfo("Import Complete", "Cash flows were loaded from Excel.")
        return

    messagebox.showwarning("Import Skipped", "Excel import completed, but no matching values were found for this calculation.")


def export_results():
    if pd is None or openpyxl is None:
        messagebox.showerror("Missing Package", "Please install pandas and openpyxl before exporting Excel files.")
        return

    file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], title="Export Results")
    if not file_path:
        return

    choice = selected_calculation.get()
    params = {field: entry.get() for field, entry in entries.items()}
    cashflows = [entry.get() for entry in cashflow_entries] if choice in ["NPV", "IRR"] else None

    try:
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            pd.DataFrame([params]).to_excel(writer, sheet_name="Parameters", index=False)
            if cashflows is not None:
                pd.DataFrame({"Year": list(range(len(cashflows))), "CashFlow": cashflows}).to_excel(writer, sheet_name="CashFlows", index=False)
        messagebox.showinfo("Export Complete", f"Results were saved to {file_path}")
    except Exception as err:
        messagebox.showerror("Export Failed", f"Could not write Excel file:\n{err}")

# ------------------------------------------
# INPUT BUILDERS
# ------------------------------------------

def clear_input_fields():
    for entry in entries.values():
        entry.delete(0, tk.END)


def clear_all():
    clear_input_fields()
    while cashflow_entries:
        remove_cashflow()
    update_inputs()
    result_label.config(text="Result will appear here.")


def bind_entry_navigation(entry, get_next_widget):
    def on_return(event):
        next_widget = get_next_widget()
        if callable(next_widget) and not isinstance(next_widget, tk.Widget):
            next_widget()
        elif next_widget is not None:
            next_widget.focus_set()
    entry.bind("<Return>", on_return)


def bind_tab_entries():
    for index, entry in enumerate(entries_order):
        def make_next(i):
            return (lambda: entries_order[i + 1]) if i + 1 < len(entries_order) else (lambda: calculate_button)
        bind_entry_navigation(entry, make_next(index))


def bind_cashflow_entry(entry):
    def on_return(event):
        if entry not in cashflow_entries:
            return
        idx = cashflow_entries.index(entry)
        if idx + 1 < len(cashflow_entries):
            cashflow_entries[idx + 1].focus_set()
        else:
            add_cashflow()
            cashflow_entries[-1].focus_set()
    entry.bind("<Return>", on_return)


def create_standard_fields(fields):
    for field in fields:
        row = ttk.Frame(input_frame)
        row.pack(fill="x", pady=4)
        label = ttk.Label(row, text=field)
        label.pack(side="left")
        entry = ttk.Entry(row)
        entry.pack(side="left", padx=(10, 0), fill="x", expand=True)
        entries[field] = entry
        entries_order.append(entry)
        if field == "PMT":
            entry.insert(0, "0")
        if field == "Frequency":
            entry.insert(0, "1")


def build_cashflow_section(include_rate=False):
    global cashflow_canvas, cashflow_inner_frame, cashflow_scrollbar

    if include_rate:
        rate_frame = ttk.Frame(input_frame)
        rate_frame.pack(fill="x", pady=4)
        rate_label = ttk.Label(rate_frame, text="Required Return (%):")
        rate_label.pack(side="left")
        rate_entry = ttk.Entry(rate_frame, width=16)
        rate_entry.pack(side="left", padx=(10, 0))
        entries["Required Return (%)"] = rate_entry

    button_frame = ttk.Frame(input_frame)
    button_frame.pack(fill="x", pady=(6, 8))
    add_btn = ttk.Button(button_frame, text="Add Cash Flow", command=add_cashflow)
    remove_btn = ttk.Button(button_frame, text="Remove Cash Flow", command=remove_cashflow)
    add_btn.pack(side="left")
    remove_btn.pack(side="left", padx=6)

    scroll_frame = ttk.Frame(input_frame)
    scroll_frame.pack(fill="both", expand=True)

    cashflow_canvas = tk.Canvas(scroll_frame, borderwidth=0, highlightthickness=0, height=260)
    cashflow_scrollbar = ttk.Scrollbar(scroll_frame, orient="vertical", command=cashflow_canvas.yview)
    cashflow_canvas.configure(yscrollcommand=cashflow_scrollbar.set)
    cashflow_scrollbar.pack(side="right", fill="y")
    cashflow_canvas.pack(side="left", fill="both", expand=True)

    cashflow_inner_frame = ttk.Frame(cashflow_canvas)
    cashflow_window = cashflow_canvas.create_window((0, 0), window=cashflow_inner_frame, anchor="nw")

    def on_frame_configure(event):
        cashflow_canvas.configure(scrollregion=cashflow_canvas.bbox("all"))

    def on_canvas_configure(event):
        cashflow_canvas.itemconfig(cashflow_window, width=event.width)

    cashflow_inner_frame.bind("<Configure>", on_frame_configure)
    cashflow_canvas.bind("<Configure>", on_canvas_configure)

    def on_mousewheel(event):
        cashflow_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def bind_mousewheel(event):
        cashflow_canvas.bind_all("<MouseWheel>", on_mousewheel)

    def unbind_mousewheel(event):
        cashflow_canvas.unbind_all("<MouseWheel>")

    cashflow_canvas.bind("<Enter>", bind_mousewheel)
    cashflow_canvas.bind("<Leave>", unbind_mousewheel)
    scroll_frame.bind("<Enter>", bind_mousewheel)
    scroll_frame.bind("<Leave>", unbind_mousewheel)

    add_cashflow()

# ------------------------------------------
# UPDATE INPUTS
# ------------------------------------------

def update_inputs():
    global cashflow_canvas, cashflow_inner_frame, cashflow_scrollbar
    for widget in input_frame.winfo_children():
        widget.destroy()

    entries.clear()
    entries_order.clear()
    cashflow_entries.clear()
    cashflow_canvas = None
    cashflow_inner_frame = None
    cashflow_scrollbar = None

    choice = selected_calculation.get()

    if choice == "Compounding":
        create_standard_fields(["Present Value", "Future Value", "Interest Rate (%)", "Years", "PMT", "Frequency"])
    elif choice == "NPV":
        build_cashflow_section(include_rate=True)
    elif choice == "IRR":
        build_cashflow_section(include_rate=False)
    elif choice == "Bond Price":
        create_standard_fields(["Face Value", "Coupon Rate (%)", "YTM (%)", "Years", "Frequency"])

    if "PMT" in entries and not entries["PMT"].get():
        entries["PMT"].insert(0, "0")
    if "Frequency" in entries and not entries["Frequency"].get():
        entries["Frequency"].insert(0, "1")
    bind_tab_entries()

selected_calculation.trace_add("write", lambda *args: update_inputs())
update_inputs()

# ==========================================
# 4. CALCULATE
# ==========================================

def calculate():
    choice = selected_calculation.get()

    if choice == "Compounding":
        pv_value = entries["Present Value"].get().strip()
        fv_value = entries["Future Value"].get().strip()
        rate_value = entries["Interest Rate (%)"].get().strip()
        years_value = entries["Years"].get().strip()
        pmt_value = entries["PMT"].get().strip()
        frequency = safe_int(entries["Frequency"].get(), default=1)

        values = {
            "Present Value": pv_value,
            "Future Value": fv_value,
            "Interest Rate (%)": rate_value,
            "Years": years_value,
            "PMT": pmt_value,
        }
        blanks = [name for name, value in values.items() if not value]

        if len(blanks) != 1:
            result_label.config(text="Please leave exactly one field blank and fill the others.")
            return

        known_pv = safe_float(pv_value)
        known_fv = safe_float(fv_value)
        known_rate = safe_float(rate_value) / 100
        known_years = safe_float(years_value)
        known_pmt = safe_float(pmt_value)

        if blanks[0] == "Present Value":
            result = solve_present_value(known_fv, known_rate, known_years, known_pmt, frequency)
            result_label.config(text=f"Present Value = ${result:,.2f}")
        elif blanks[0] == "Future Value":
            result = solve_future_value(known_pv, known_rate, known_years, known_pmt, frequency)
            result_label.config(text=f"Future Value = ${result:,.2f}")
        elif blanks[0] == "Interest Rate (%)":
            def rate_objective(r):
                return solve_future_value(known_pv, r, known_years, known_pmt, frequency) - known_fv

            rate_result = find_root(rate_objective, -0.9999, 1.0)
            if rate_result is None:
                result_label.config(text="Could not calculate Rate. Check the other inputs.")
            else:
                result_label.config(text=f"Interest Rate = {rate_result * 100:.4f}%")
        elif blanks[0] == "Years":
            def years_objective(y):
                return solve_future_value(known_pv, known_rate, y, known_pmt, frequency) - known_fv

            years_result = find_root(years_objective, 0.0, 1000.0)
            if years_result is None:
                result_label.config(text="Could not calculate Years. Check the other inputs.")
            else:
                result_label.config(text=f"Years = {years_result:.4f}")
        else:  # PMT
            result = solve_payment(known_pv, known_fv, known_rate, known_years, frequency)
            result_label.config(text=f"PMT = ${result:,.2f}")
    elif choice == "NPV":
        rate = safe_float(entries["Required Return (%)"].get()) / 100
        cashflows = [safe_float(entry.get()) for entry in cashflow_entries]
        result = NPV(rate, cashflows)
        result_label.config(text=f"NPV = ${result:,.2f}")
    elif choice == "IRR":
        cashflows = [safe_float(entry.get()) for entry in cashflow_entries]
        irr_rate = compute_irr(cashflows)
        if irr_rate is None:
            result_label.config(text="IRR could not be calculated. Check cash flows.")
        else:
            result_label.config(text=f"IRR = {irr_rate * 100:.4f}%")
    elif choice == "Bond Price":
        face_value = safe_float(entries["Face Value"].get())
        coupon_rate = safe_float(entries["Coupon Rate (%)"].get()) / 100
        ytm = safe_float(entries["YTM (%)"].get()) / 100
        years = safe_int(entries["Years"].get())
        frequency = safe_int(entries["Frequency"].get(), default=1)
        result = Bond_price(face_value, coupon_rate, ytm, years, frequency)
        result_label.config(text=f"Bond Price = ${result:,.2f}")

# ==========================================
# 5. BUTTONS
# ==========================================

button_frame = ttk.Frame(main_frame)
button_frame.pack(fill="x", pady=(8, 0))

calculate_button = ttk.Button(button_frame, text="Calculate", command=calculate)
calculate_button.pack(side="left")

export_button = ttk.Button(button_frame, text="Export Results", command=export_results)
export_button.pack(side="left", padx=6)

import_button = ttk.Button(button_frame, text="Import Excel", command=import_excel)
import_button.pack(side="left", padx=6)

reset_button = ttk.Button(button_frame, text="Clear / Reset", command=clear_all)
reset_button.pack(side="left", padx=6)

# ==========================================
# 6. RUN APP
# ==========================================

window.mainloop()
