"""Tkinter controls for the two manual portfolio analytics calculators."""
from __future__ import annotations

from datetime import date
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from apps.manual_returns_formulas import individual_steps, investments_portfolio_steps, matrix_steps, number, portfolio_steps
from financial_toolkit.manual_returns import INVESTMENT_OPTIONS, PORTFOLIO_OPTIONS, calculate_manual_returns, investment_weight_total
from financial_toolkit.validation import InputError


def blank(kind):
    names = ["Investment 1", "Investment 2"] if kind == "Investments" else ["Portfolio A", "Portfolio B"]
    year = date.today().year
    return {"started": False, "frequency": "monthly", "names": names,
            "rows": [{"Date": f"{year}-{month:02d}-28", **{name: "" for name in names}} for month in (1, 2, 3)],
            "option": (INVESTMENT_OPTIONS if kind == "Investments" else PORTFOLIO_OPTIONS)[0],
            "risk_free": "", "market": "", "target": "", "benchmark": {}, "result": None,
            "weights": {name: "50" for name in names} if kind == "Investments" else {},
            "cash_weight": "0", "cash_yield": "", "funding_rate": "",
            "result_signature": None, "advanced": {}}


def pct(value):
    if value is None:
        return "Undefined"
    scaled = value * 100
    return f"{scaled:.4e}%" if scaled != 0 and abs(scaled) < 0.00005 else f"{scaled:.4f}%"


class ManualScreen:
    def __init__(self, parent, kind, form, mode):
        self.parent, self.kind, self.form, self.mode = parent, kind, form, mode
        self.fields = {}
        self.name_fields = []
        self.weight_fields = []
        self.weight_vars = []
        self.field_vars = {}
        self.total_weight_label = None
        self.row_fields = []
        self.benchmark_fields = []
        self.advanced_fields = {}
        self.allow_short = None
        self.option_widget = None
        self.frequency_widget = None
        self.output = None
        self.render()

    def save(self):
        if not self.form["started"] or not self.name_fields:
            return
        old = self.form["names"]
        names = [entry.get().strip() for entry in self.name_fields]
        weights = {name: entry.get() for name, entry in zip(names, self.weight_fields)} if self.kind == "Investments" else {}
        rows = []
        for row in self.row_fields:
            values = [entry.get() for entry in row]
            rows.append({"Date": values[0], **{name: values[i+1] for i, name in enumerate(names)}})
        benchmark = {row[0].get(): row[1].get() for row in self.benchmark_fields}
        self.form.update(names=names, weights=weights, rows=rows, benchmark=benchmark,
                         frequency=self.frequency_widget.get(), option=self.option_widget.get())
        for key, entry in self.fields.items():
            self.form[key] = entry.get()
        self.form["advanced"] = {key: entry.get() for key, entry in self.advanced_fields.items()}
        if self.allow_short is not None:
            self.form["advanced"]["allow_short"] = bool(self.allow_short.get())

    def signature(self):
        f = self.form
        return repr((f["names"], f["weights"], f["cash_weight"], f["cash_yield"], f["funding_rate"],
                     f["rows"], f["frequency"], f["option"], f["risk_free"],
                     f["market"], f["target"], f["benchmark"], f["advanced"], self.mode))

    def refresh(self):
        self.save()
        self.render()

    def render(self):
        for child in self.parent.winfo_children():
            child.destroy()
        self.fields = {}; self.field_vars = {}; self.name_fields = []; self.weight_fields = []; self.weight_vars = []; self.row_fields = []; self.benchmark_fields = []; self.advanced_fields = {}; self.allow_short = None; self.total_weight_label = None
        outer = ttk.Frame(self.parent)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        body = ttk.Frame(canvas, padding=14)
        handle = canvas.create_window(0, 0, window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(handle, width=e.width))
        f = self.form
        ttk.Label(body, text=self.kind, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        if not f["started"]:
            ttk.Label(body, text="Step 1 · Open " + self.kind).pack(anchor="w", pady=8)
            ttk.Label(body, text="Enter manual historical returns and calculate risk and return." if self.kind == "Investments"
                      else "Compare portfolio returns and estimate allocations between portfolios.").pack(anchor="w")
            ttk.Button(body, text="Start Analysis", command=self.start).pack(anchor="w", pady=10)
            return
        ttk.Label(body, text="Step 2 · " + ("Enter investments" if self.kind == "Investments" else "Create portfolios"),
                  font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(12, 4))
        freq = ttk.Frame(body); freq.pack(fill="x")
        ttk.Label(freq, text="Return frequency").pack(side="left")
        self.frequency_widget = ttk.Combobox(freq, values=("monthly", "yearly"), state="readonly", width=12)
        self.frequency_widget.set(f["frequency"]); self.frequency_widget.pack(side="left", padx=10)
        for i, name in enumerate(f["names"]):
            line = ttk.Frame(body); line.pack(fill="x", pady=3)
            entry = ttk.Entry(line); entry.insert(0, name); entry.pack(side="left", fill="x", expand=True)
            self.name_fields.append(entry)
            if self.kind == "Investments":
                ttk.Label(line, text="Weight (%)").pack(side="left", padx=(8, 2))
                weight_value = tk.StringVar(value=f["weights"].get(name, ""))
                weight = ttk.Entry(line, width=12, textvariable=weight_value); weight.pack(side="left")
                weight_value.trace_add("write", lambda *_: self.update_total_weight())
                self.weight_vars.append(weight_value)
                self.weight_fields.append(weight)
            ttk.Button(line, text="Remove", command=lambda i=i: self.remove_name(i),
                       state="disabled" if len(f["names"]) <= 1 else "normal").pack(side="left", padx=5)
        ttk.Button(body, text="Add " + ("investment" if self.kind == "Investments" else "portfolio"),
                   command=self.add_name).pack(anchor="w", pady=5)
        if self.kind == "Investments":
            if self.mode == "Advanced":
                self.entry(body, "Cash holding Weight (%)", "cash_weight")
                self.entry(body, "Annual effective cash yield (%) — required for positive cash", "cash_yield")
                self.entry(body, "Annual effective funding rate (%) — required for negative cash", "funding_rate")
            self.total_weight_label = ttk.Label(body)
            self.total_weight_label.pack(anchor="w", pady=4)
            self.update_total_weight()
            ttk.Label(body, text=("Investment weights must total 100%." if self.mode == "Standard" else
                      "Investment weights plus cash must total 100%. Enter cash explicitly, including 0%.") +
                      " Whole-portfolio returns use constant weights rebalanced each period.", wraplength=1000).pack(anchor="w", pady=4)
        ttk.Label(body, text="Step 3 · Enter historical returns (%)", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(12, 4))
        ttk.Label(body, text="Each row is one aligned date. Blank returns are missing, not zero.").pack(anchor="w")
        grid = ttk.Frame(body); grid.pack(fill="x", pady=6)
        for j, name in enumerate(["Date", *f["names"]]):
            ttk.Label(grid, text=name, width=19).grid(row=0, column=j, sticky="w")
        for i, data in enumerate(f["rows"]):
            entries = []
            for j, name in enumerate(["Date", *f["names"]]):
                entry = ttk.Entry(grid, width=18)
                entry.insert(0, str(data.get(name, "")))
                entry.grid(row=i+1, column=j, padx=2, pady=2, sticky="ew")
                entries.append(entry)
            self.row_fields.append(entries)
        bar = ttk.Frame(body); bar.pack(anchor="w")
        ttk.Button(bar, text="Add period", command=self.add_row).pack(side="left")
        ttk.Button(bar, text="Remove last period", command=self.remove_row,
                   state="normal" if len(f["rows"]) > 2 else "disabled").pack(side="left", padx=6)
        ttk.Label(body, text="Step 4 · Choose calculation", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(12, 4))
        opts = INVESTMENT_OPTIONS if self.kind == "Investments" else PORTFOLIO_OPTIONS
        self.option_widget = ttk.Combobox(body, values=opts, state="readonly", width=55)
        self.option_widget.set(f["option"]); self.option_widget.pack(anchor="w")
        self.option_widget.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        option = f["option"]
        need_rf = option in ("Sharpe ratio", "CAPM required return", "Markowitz optimization — Maximum Sharpe ratio")
        if need_rf or self.kind == "Portfolio" and option == "Portfolio statistics":
            self.entry(body, "Annual effective risk-free rate (%)", "risk_free")
        if option in ("Beta", "CAPM required return"):
            ttk.Label(body, text="Matching benchmark returns (%)").pack(anchor="w", pady=(6, 2))
            for row in f["rows"]:
                line = ttk.Frame(body); line.pack(anchor="w")
                d = ttk.Entry(line, width=16); d.insert(0, row["Date"]); d.pack(side="left")
                value = ttk.Entry(line, width=18); value.insert(0, f["benchmark"].get(row["Date"], "")); value.pack(side="left")
                self.benchmark_fields.append((d, value))
        if option == "CAPM required return":
            self.entry(body, "Expected annual market return (%)", "market")
        if option == "Markowitz optimization — Target return":
            self.entry(body, "Target return (% per selected period)", "target")
        if self.kind == "Investments" and self.mode == "Advanced":
            ttk.Label(body, text="Advanced investment allocation constraints (%)").pack(anchor="w", pady=5)
            for name in f["names"]:
                self.advanced_entry(body, name + " lower", "lo:" + name, "0")
                self.advanced_entry(body, name + " upper", "hi:" + name, "100")
            for label, key, default in (("Gross exposure cap", "gross", "100"),
                                        ("Minimum net exposure", "net_min", "100"),
                                        ("Maximum net exposure", "net_max", "100")):
                self.advanced_entry(body, label, key, default)
            self.allow_short = tk.BooleanVar(value=bool(f["advanced"].get("allow_short", False)))
            ttk.Checkbutton(body, text="Allow short positions", variable=self.allow_short).pack(anchor="w")
        if self.kind == "Portfolio" and (option.startswith("Markowitz") or option == "Efficient frontier"):
            ttk.Label(body, text="Standard allocation: long only, fully invested; weights total 100%.").pack(anchor="w", pady=5)
            if self.mode == "Advanced":
                ttk.Label(body, text="Advanced allocation constraints (%)").pack(anchor="w")
                for name in f["names"]:
                    self.advanced_entry(body, name + " lower", "lo:" + name, "0")
                    self.advanced_entry(body, name + " upper", "hi:" + name, "100")
                for label, key, default in (("Gross exposure cap", "gross", "100"),
                                            ("Minimum net exposure", "net_min", "100"),
                                            ("Maximum net exposure", "net_max", "100")):
                    self.advanced_entry(body, label, key, default)
                self.allow_short = tk.BooleanVar(value=bool(f["advanced"].get("allow_short", False)))
                ttk.Checkbutton(body, text="Allow short positions", variable=self.allow_short).pack(anchor="w")
        controls = ttk.Frame(body); controls.pack(anchor="w", pady=10)
        ttk.Button(controls, text="Calculate", command=self.calculate).pack(side="left")
        ttk.Button(controls, text="Reset", command=self.reset).pack(side="left", padx=7)
        self.output = ttk.Frame(body); self.output.pack(fill="both", expand=True)
        if f["result"]:
            self.show(f["result"])

    def entry(self, body, label, key):
        ttk.Label(body, text=label).pack(anchor="w", pady=(5, 2))
        if key == "cash_weight" and self.kind == "Investments":
            value = tk.StringVar(value=self.form[key])
            field = ttk.Entry(body, width=24, textvariable=value)
            value.trace_add("write", lambda *_: self.update_total_weight())
            self.field_vars[key] = value
        else:
            field = ttk.Entry(body, width=24)
            field.insert(0, self.form[key])
        field.pack(anchor="w")
        self.fields[key] = field

    def update_total_weight(self):
        if self.total_weight_label is None:
            return
        cash = self.fields["cash_weight"].get() if self.mode == "Advanced" else None
        total = investment_weight_total({str(i): field.get() for i, field in enumerate(self.weight_fields)}, cash)
        self.total_weight_label.configure(text="Total Weight (%): " + ("Incomplete" if total is None else f"{total:g}%"))

    def advanced_entry(self, body, label, key, default):
        ttk.Label(body, text=label + " (%)").pack(anchor="w", pady=(4, 1))
        field = ttk.Entry(body, width=18)
        field.insert(0, self.form["advanced"].get(key, default))
        field.pack(anchor="w")
        self.advanced_fields[key] = field

    def start(self):
        self.form["started"] = True
        self.render()

    def add_name(self):
        self.save()
        n = len(self.form["names"]) + 1
        name = (f"Investment {n}" if self.kind == "Investments" else f"Portfolio {chr(64+n)}")
        while name in self.form["names"]:
            n += 1; name = f"Portfolio {n}" if self.kind == "Portfolio" else f"Investment {n}"
        self.form["names"].append(name)
        if self.kind == "Investments": self.form["weights"][name] = ""
        for row in self.form["rows"]: row[name] = ""
        self.render()

    def remove_name(self, index):
        self.save()
        if len(self.form["names"]) <= 1: return
        name = self.form["names"].pop(index)
        if self.kind == "Investments": self.form["weights"].pop(name, None)
        for row in self.form["rows"]: row.pop(name, None)
        self.render()

    def add_row(self):
        self.save()
        self.form["rows"].append({"Date": "", **{name: "" for name in self.form["names"]}})
        self.render()

    def remove_row(self):
        self.save()
        if len(self.form["rows"]) > 2: self.form["rows"].pop()
        self.render()

    def calculate(self):
        self.save()
        for child in self.output.winfo_children(): child.destroy()
        try:
            f = self.form
            advanced = {}
            if self.kind == "Investments" and self.mode == "Advanced":
                values = f["advanced"]
                try:
                    advanced = {"lower_bounds": {name: values["lo:" + name] for name in f["names"]},
                                "upper_bounds": {name: values["hi:" + name] for name in f["names"]},
                                "gross_cap": values["gross"], "net_min": values["net_min"],
                                "net_max": values["net_max"],
                                "allow_short": bool(values.get("allow_short", False))}
                except KeyError as exc:
                    raise InputError("Enter Advanced bounds and exposure limits for every investment.") from exc
            if self.mode == "Advanced" and (f["option"].startswith("Markowitz") or f["option"] == "Efficient frontier"):
                values = f["advanced"]
                try:
                    advanced = {"lower_bounds": {name: float(values["lo:" + name])/100 for name in f["names"]},
                                "upper_bounds": {name: float(values["hi:" + name])/100 for name in f["names"]},
                                "gross_cap": float(values["gross"])/100,
                                "net_min": float(values["net_min"])/100,
                                "net_max": float(values["net_max"])/100,
                                "allow_short": bool(values.get("allow_short", False))}
                except (KeyError, ValueError) as exc:
                    raise InputError("Enter numeric Advanced bounds and exposure limits.") from exc
            result = calculate_manual_returns(kind=self.kind, names=f["names"], rows=f["rows"],
                frequency=f["frequency"], option=f["option"], risk_free_annual=f["risk_free"],
                benchmark=f["benchmark"], expected_market_annual=f["market"], target_return=f["target"],
                financial_mode=self.mode,
                **({"weights": f["weights"], "cash_weight": f["cash_weight"] if self.mode == "Advanced" else "0",
                    "cash_annual_yield": f["cash_yield"], "funding_annual_rate": f["funding_rate"]}
                   if self.kind == "Investments" else {}), **advanced)
            f["result"] = result
            f["result_signature"] = self.signature()
            self.show(result)
        except (InputError, ValueError) as exc:
            self.form["result"] = None
            ttk.Label(self.output, text="INVALID: " + str(exc), wraplength=950).pack(anchor="w")

    def reset(self):
        self.form.clear(); self.form.update(blank(self.kind)); self.render()

    def formula_panel(self, title, choices, content):
        """Keep long numerical expansions visible through a scrolling detail pane."""
        panel = ttk.LabelFrame(self.output, text=title)
        panel.pack(fill="x", pady=5)
        chooser = ttk.Combobox(panel, values=choices, state="readonly", width=48)
        chooser.current(0); chooser.pack(anchor="w", padx=5, pady=4)
        detail = ScrolledText(panel, height=10, wrap="word", width=115)
        detail.pack(fill="x", padx=5, pady=(0, 5))

        def update(_=None):
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", content(chooser.current()))
            detail.configure(state="disabled")

        chooser.bind("<<ComboboxSelected>>", update)
        update()
        return detail

    def show(self, result):
        if self.form["result_signature"] != self.signature():
            ttk.Label(self.output, text="Inputs changed since calculation. Press Calculate to update results.").pack(anchor="w")
        ttk.Label(self.output, text="Step 5 · Calculated results", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=5)
        selected = {"Average historical return": ("mean", pct), "Variance": ("variance", number),
                    "Volatility (standard deviation)": ("volatility", pct),
                    "Sharpe ratio": ("sharpe", lambda x: "Undefined" if x is None else number(x)),
                    "Beta": ("beta", lambda x: "Undefined" if x is None else number(x)),
                    "CAPM required return": ("capm", pct)}
        if result["option"] in selected:
            field, formatter = selected[result["option"]]
            for stat in result["stats"]:
                ttk.Label(self.output, text=f"{stat['name']}: {formatter(stat[field])}",
                          font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=3)
        for stat in result["stats"]:
            ttk.Label(self.output, text=(f"{stat['name']}: average {pct(stat['mean'])}; sample variance {number(stat['variance'])}; "
                f"volatility {pct(stat['volatility'])}; Sharpe {number(stat['sharpe']) if stat['sharpe'] is not None else 'undefined'}; "
                f"beta {number(stat['beta']) if stat['beta'] is not None else 'undefined'}; CAPM {pct(stat['capm'])}"),
                wraplength=1100).pack(anchor="w", pady=2)
        if result["portfolio"] is not None:
            p = result["portfolio"]
            ttk.Label(self.output, text="Whole portfolio", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(7, 2))
            ttk.Label(self.output, text=(f"Weighted average {pct(p['mean'])}; sample variance {number(p['variance'])}; "
                f"volatility {pct(p['volatility'])}; Sharpe {number(p['sharpe']) if p['sharpe'] is not None else 'undefined'}; "
                f"beta {number(p['beta']) if p['beta'] is not None else 'undefined'}; CAPM {pct(p['capm'])}"),
                wraplength=1100).pack(anchor="w")
            ttk.Label(self.output, text=p["assumption"], wraplength=1100).pack(anchor="w")
        self.formula_panel("Entered values and numerical steps", result["names"],
                           lambda index: individual_steps(result, result["names"][index]))
        if result["kind"] == "Investments" or result["option"] in ("Covariance matrix", "Correlation matrix", "Covariance and correlation matrix", "Portfolio statistics", "Compare portfolios"):
            for title, matrix in (("Covariance", result["covariance"]), ("Correlation", result["correlation"])):
                ttk.Label(self.output, text=title + " matrix", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
                for name, row in zip(result["names"], matrix):
                    ttk.Label(self.output, text=name + ": " + " | ".join("undefined" if x is None else number(x) for x in row)).pack(anchor="w")
            pairs = [(a, b) for i, a in enumerate(result["names"]) for b in result["names"][i:]]
            self.formula_panel("Paired return substitutions", [f"{a} / {b}" for a, b in pairs],
                               lambda index: matrix_steps(result, *pairs[index]))
        if result["portfolio"] is not None:
            self.formula_panel("Actual weights, returns and covariance in whole-portfolio formulas", ["Whole portfolio"],
                               lambda _: investments_portfolio_steps(result))
        if result["optimization"]:
            d = result["optimization"]
            ttk.Label(self.output, text="Optimal weights: " + ", ".join(f"{name} {pct(weight)}" for name, weight in d["weights"].items())).pack(anchor="w")
            ttk.Label(self.output, text=f"Estimated return {pct(d['expected_return'])}; volatility {pct(d['volatility'])}; wᵀΣw = {number(d['variance'])}").pack(anchor="w")
            ttk.Label(self.output, text="wᵀμ = " + " + ".join(f"{d['weights'][s['name']]:.6f} × {s['mean']:.6f}" for s in result["stats"]) + f" = {d['expected_return']:.6f} per period.").pack(anchor="w")
            self.formula_panel("Actual weights, means and covariance in portfolio formulas", ["Optimized allocation"],
                               lambda _: portfolio_steps(result, d))
        if result["frontier"]:
            ttk.Label(self.output, text=f"Efficient frontier: {len(result['frontier'])} feasible points.").pack(anchor="w")
            points = result["frontier"]
            self.formula_panel("Efficient-frontier point formulas",
                               [f"Point {i+1}: target {pct(point['target'])}" for i, point in enumerate(points)],
                               lambda index: portfolio_steps(result, points[index]))
        meaning = {
            "Average historical return": "The arithmetic average describes the observed period, not a future forecast.",
            "Risk Analysis": "Individual investment risk and weighted whole-portfolio risk use aligned periods.",
            "Variance": "Higher variance means returns moved farther from their historical average.",
            "Volatility (standard deviation)": "Volatility describes historical return dispersion.",
            "Covariance matrix": "Positive covariance indicates movement together; negative covariance indicates opposite movement.",
            "Correlation matrix": "Correlation scales co-movement from -1 to +1.",
            "Sharpe ratio": "Sharpe compares historical excess return with matching-period volatility.",
            "Beta": "Beta measures sensitivity to the entered benchmark.",
            "CAPM required return": "CAPM is a model-implied required return using the entered market expectation.",
            "Portfolio statistics": "These statistics describe each complete portfolio independently.",
            "Covariance and correlation matrix": "The matrices describe co-movement between complete portfolios.",
            "Compare portfolios": "Compare returns and risk over the same aligned dates.",
            "Efficient frontier": "Frontier points are estimated minimum-risk allocations for return floors.",
        }
        explanation = meaning.get(result["option"], "The optimized allocation is estimated from historical returns and is not guaranteed.")
        ttk.Label(self.output, text=explanation, wraplength=1100).pack(anchor="w", pady=4)
        for warning in result["warnings"]:
            ttk.Label(self.output, text="Warning: " + warning, wraplength=1100).pack(anchor="w")
        ttk.Label(self.output, text="Historical estimates are not guaranteed future performance.").pack(anchor="w", pady=4)
        ttk.Label(self.output, text="Step 6 · Visualizations", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(8, 2))
        self.chart(result)

    def chart(self, result):
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            fig = Figure(figsize=(9, 3), dpi=100)
            ax = fig.add_subplot(111)
            for i, name in enumerate(result["names"]):
                ax.plot(result["dates"], [row[i]*100 for row in result["returns"]], marker="o", label=name)
            if result["portfolio"] is not None:
                ax.plot(result["dates"], [x*100 for x in result["portfolio"]["returns"]],
                        marker="o", linewidth=2.5, label="Whole portfolio")
            ax.set_ylabel("Return (%)"); ax.tick_params(axis="x", rotation=35); ax.legend(loc="best")
            fig.tight_layout()
            widget = FigureCanvasTkAgg(fig, master=self.output)
            widget.draw(); widget.get_tk_widget().pack(fill="x")
            if result["kind"] == "Investments" or result["option"] in ("Correlation matrix", "Covariance matrix", "Covariance and correlation matrix", "Compare portfolios", "Portfolio statistics", "Efficient frontier"):
                fig_h = Figure(figsize=(5, 3), dpi=100); hx = fig_h.add_subplot(111)
                values = [[float("nan") if x is None else x for x in row] for row in result["correlation"]]
                heat = hx.imshow(values, vmin=-1, vmax=1, cmap="RdBu")
                hx.set_xticks(range(len(result["names"])), result["names"], rotation=30)
                hx.set_yticks(range(len(result["names"])), result["names"])
                fig_h.colorbar(heat, ax=hx); fig_h.tight_layout()
                view_h = FigureCanvasTkAgg(fig_h, master=self.output)
                view_h.draw(); view_h.get_tk_widget().pack(fill="x")
            if result["option"] in ("Volatility (standard deviation)", "Risk Analysis", "Sharpe ratio", "Compare portfolios", "Portfolio statistics", "Efficient frontier"):
                fig_r = Figure(figsize=(6, 3), dpi=100); rx = fig_r.add_subplot(111)
                for stat in result["stats"]:
                    x, y = stat["volatility"]*100, stat["mean"]*100
                    rx.scatter([x], [y]); rx.annotate(stat["name"], (x, y))
                if result["portfolio"] is not None:
                    p = result["portfolio"]
                    x, y = p["volatility"]*100, p["mean"]*100
                    rx.scatter([x], [y], marker="D"); rx.annotate("Whole portfolio", (x, y))
                rx.set_xlabel("Volatility (%)"); rx.set_ylabel("Average return (%)")
                fig_r.tight_layout(); view_r = FigureCanvasTkAgg(fig_r, master=self.output)
                view_r.draw(); view_r.get_tk_widget().pack(fill="x")
            if result["frontier"]:
                fig2 = Figure(figsize=(7, 3), dpi=100); bx = fig2.add_subplot(111)
                bx.plot([x["volatility"]*100 for x in result["frontier"]],
                        [x["return"]*100 for x in result["frontier"]], marker="o")
                bx.set_xlabel("Volatility (%)"); bx.set_ylabel("Estimated return (%)")
                fig2.tight_layout(); view = FigureCanvasTkAgg(fig2, master=self.output)
                view.draw(); view.get_tk_widget().pack(fill="x")
        except ImportError:
            ttk.Label(self.output, text="Install the web/chart optional dependencies to display charts.").pack(anchor="w")


class ManualPortfolioTabs:
    def __init__(self, parent, forms, mode, kinds=("Investments", "Portfolio")):
        self.notebook = ttk.Notebook(parent); self.notebook.pack(fill="both", expand=True)
        self.screens = []
        self.tabs = {}
        for kind in kinds:
            tab = ttk.Frame(self.notebook); self.notebook.add(tab, text=kind)
            self.tabs[kind] = tab
            self.screens.append(ManualScreen(tab, kind, forms[kind], mode))

    def save(self):
        for screen in self.screens:
            screen.save()
