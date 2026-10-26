"""One-sheet presentation of a completed Investments calculation."""
from __future__ import annotations

from datetime import date
import io
import math

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from financial_toolkit.reporting_s7 import _protect
from financial_toolkit.validation import InputError


NAVY = "103C70"
BLUE = "1456A4"
LIGHT_BLUE = "C9E0F3"
GREEN = "B9DDBC"
ORANGE = "FFD09A"
INK = "172B42"
WHITE = "FFFFFF"
GRID = "C6D6E6"
PANEL = "EAF2FA"
BACKGROUND = "FFFFFF"
PERCENT = '0.0000%;[Red]-0.0000%;0.0000%'
RATIO = '0.0000;[Red]-0.0000;0.0000'
VARIANCE = '0.00000000;[Red]-0.00000000;0.00000000'
TINY = '0.00000000E+00;[Red]-0.00000000E+00;0.00000000E+00'


def _cell(ws, row, col, value, kind="text"):
    cell = ws.cell(row, col)
    if value is None:
        cell.value = None
    elif kind == "text":
        value = str(value)
        if len(value) > 32760:
            raise InputError("An investment name is too long for an Excel cell.")
        cell.value = _protect(value)
        cell.data_type = "s"
    elif kind == "date":
        cell.value = date.fromisoformat(str(value)[:10])
        cell.number_format = "yyyy-mm-dd"
    else:
        numeric = float(value)
        if not math.isfinite(numeric):
            raise InputError("A nonfinite analysis value cannot be exported to Excel.")
        cell.value = numeric
        cell.number_format = (PERCENT if kind == "percent" else RATIO if kind == "ratio"
                              else TINY if numeric != 0 and abs(numeric) < 5e-9 else VARIANCE)
    cell.font = Font(name="Aptos", size=10, color=INK)
    cell.alignment = Alignment(vertical="center")
    cell.border = Border(bottom=Side(style="hair", color=GRID))
    return cell


def _band(ws, row, first, last, label, color):
    for col in range(first, last + 1):
        c = ws.cell(row, col)
        c.fill = PatternFill("solid", fgColor=color)
        c.border = Border(bottom=Side(style="thin", color=GRID))
    ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
    c = _cell(ws, row, first, label)
    c.fill = PatternFill("solid", fgColor=color)
    c.font = Font(name="Aptos", size=11, bold=True, color=INK)
    ws.row_dimensions[row].height = 21


def _headers(ws, row, labels, first=1):
    for col, label in enumerate(labels, first):
        c = _cell(ws, row, col, label)
        c.fill = PatternFill("solid", fgColor=PANEL)
        c.font = Font(name="Aptos", size=9, bold=True, color=INK)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 31


def _metric(ws, row, col, value, kind, unavailable):
    if value is None:
        reason = unavailable.get(kind, "")
        cell = _cell(ws, row, col, "Undefined" if "Undefined" in reason else "Unavailable")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    else:
        _cell(ws, row, col, value, "percent" if kind in ("Average", "Volatility", "CAPM required return")
              else "variance" if kind == "Sample variance" else "ratio")


def _stats_row(ws, row, stat, unavailable):
    _cell(ws, row, 1, stat["name"])
    for col, key, label in ((2, "mean", "Average"), (3, "variance", "Sample variance"),
                            (4, "volatility", "Volatility"), (5, "sharpe", "Sharpe ratio"),
                            (6, "beta", "Beta"), (7, "capm", "CAPM required return")):
        _metric(ws, row, col, stat[key], label, unavailable)


def _matrix(ws, row, first, title, names, values, correlation=False):
    last = first + len(names)
    _band(ws, row, first, last, title, LIGHT_BLUE)
    _headers(ws, row + 1, ["Investment", *names], first)
    for i, name in enumerate(names):
        _cell(ws, row + 2 + i, first, name)
        for j, value in enumerate(values[i]):
            if value is None:
                _cell(ws, row + 2 + i, first + 1 + j, "Undefined")
            else:
                _cell(ws, row + 2 + i, first + 1 + j, value,
                      "ratio" if correlation else "variance")
    if correlation:
        start = f"{get_column_letter(first+1)}{row+2}"
        stop = f"{get_column_letter(last)}{row+1+len(names)}"
        ws.conditional_formatting.add(f"{start}:{stop}", ColorScaleRule(
            start_type="num", start_value=-1, start_color="E66A6A",
            mid_type="num", mid_value=0, mid_color="FFFFFF",
            end_type="num", end_value=1, end_color="4389E4"))
    return row + len(names) + 2


def _chart(ws, count, column, title, anchor):
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = title
    chart.y_axis.numFmt = "0.0%"
    chart.legend = None
    chart.add_data(Reference(ws, min_col=column, min_row=1, max_row=count + 2),
                   titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=27, min_row=2, max_row=count + 2))
    chart.visible_cells_only = False
    chart.series[0].graphicalProperties.solidFill = BLUE
    chart.series[0].data_points = [DataPoint(idx=count, spPr=GraphicalProperties(solidFill="168B50"))]
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showVal = True
    chart.dataLabels.numFmt = "0.00%"
    chart.width, chart.height = 13.5, 8.2
    ws.add_chart(chart, anchor)


def investment_excel_bytes(inputs, result):
    """Export only the Summary worksheet from the exact calculated snapshot."""
    if result.get("kind") != "Investments" or result.get("portfolio") is None:
        raise InputError("A completed Investments analysis is required for Excel export.")
    names, days, frequency = result["names"], result["dates"], result["frequency"]
    if (names != inputs["names"] or days != [str(row["Date"]) for row in inputs["rows"]]
            or frequency != inputs["frequency"]):
        raise InputError("The export input snapshot does not match the calculated result.")

    book = Workbook()
    ws = book.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 80
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.freeze_panes = "A4"
    for col, width in {"A": 27, "B": 20, "C": 17, "D": 18, "E": 15,
                       "F": 22, "G": 18, "H": 19, "I": 18, "J": 18}.items():
        ws.column_dimensions[col].width = width
    ws.merge_cells("A1:J2")
    title = _cell(ws, 1, 1, "Investment Analysis")
    title.fill = PatternFill("solid", fgColor=NAVY)
    title.font = Font(name="Aptos Display", size=21, bold=True, color=WHITE)
    title.alignment = Alignment(vertical="center", indent=1)
    for row in (1, 2):
        for col in range(1, 11):
            ws.cell(row, col).fill = PatternFill("solid", fgColor=NAVY)
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 16

    for row, label, value, kind in (
            (4, "Analysis date", inputs["calculated_at"], "date"),
            (5, "Return frequency", frequency.title(), "text"),
            (6, "Annual risk-free rate", result["risk_free_annual"], "percent"),
            (7, "Expected market return", result["market_annual"], "percent"),
            (8, "Number of periods", str(len(days)), "text")):
        _cell(ws, row, 1, label)
        _cell(ws, row, 2, value, kind)
    _band(ws, 4, 6, 8, "Portfolio weights", LIGHT_BLUE)
    for row, name in enumerate(names, 5):
        ws.merge_cells(start_row=row, start_column=6, end_row=row, end_column=7)
        _cell(ws, row, 6, name)
        _cell(ws, row, 8, result["weights"][name], "percent")
    total_row = 5 + len(names)
    ws.merge_cells(start_row=total_row, start_column=6, end_row=total_row, end_column=7)
    _cell(ws, total_row, 6, "Total (including cash)")
    _cell(ws, total_row, 8, sum(result["weights"].values()) + result["cash_weight"], "percent")
    for col in (6, 7, 8):
        ws.cell(total_row, col).fill = PatternFill("solid", fgColor=LIGHT_BLUE)
    ws.cell(total_row, 6).font = Font(name="Aptos", size=10, bold=True, color=INK)
    ws.cell(total_row, 8).font = Font(name="Aptos", size=10, bold=True, color=INK)
    if result["cash_weight"] != 0:
        cash_row = total_row + 1
        ws.merge_cells(start_row=cash_row, start_column=6, end_row=cash_row, end_column=7)
        _cell(ws, cash_row, 6, "Cash / funding")
        _cell(ws, cash_row, 8, result["cash_weight"], "percent")

    stats_title = max(12, total_row + 3)
    _band(ws, stats_title, 1, 7, "Individual investments", GREEN)
    labels = ["Investment", f"Average ({frequency})", "Variance", "Volatility",
              "Sharpe ratio", "Beta", "CAPM required return"]
    _headers(ws, stats_title + 1, labels)
    for row, item in enumerate(result["stats"], stats_title + 2):
        _stats_row(ws, row, item, result["unavailable"])
    portfolio_title = stats_title + len(names) + 4
    _band(ws, portfolio_title, 1, 7, "Whole portfolio", ORANGE)
    _headers(ws, portfolio_title + 1, labels)
    _stats_row(ws, portfolio_title + 2, result["portfolio"], result["unavailable"])
    for col, color in enumerate(("DBEAF8", "DDF0DF", "E5DDF7", "FFF0CA", "E1E9FA", "F7E2E7"), 2):
        cell = ws.cell(portfolio_title + 2, col)
        cell.fill = PatternFill("solid", fgColor=color)
        cell.font = Font(name="Aptos", size=10, bold=True, color=INK)
    matrix_row = portfolio_title + 5
    cov_end = _matrix(ws, matrix_row, 1, "Covariance matrix (decimal return squared)",
                      names, result["covariance"])
    if len(names) <= 4:
        cor_end = _matrix(ws, matrix_row, 6, "Correlation matrix", names,
                          result["correlation"], True)
    else:
        cor_end = _matrix(ws, cov_end + 2, 1, "Correlation matrix", names,
                          result["correlation"], True)
    chart_row = max(cov_end, cor_end) + 3
    ws["AA1"] = "Investment"
    ws["AB1"] = "Average return"
    ws["AC1"] = "Volatility"
    for row, item in enumerate([*result["stats"], result["portfolio"]], 2):
        _cell(ws, row, 27, item["name"])
        _cell(ws, row, 28, item["mean"], "percent")
        _cell(ws, row, 29, item["volatility"], "percent")
    for col in ("AA", "AB", "AC"):
        ws.column_dimensions[col].hidden = True
    _chart(ws, len(names), 28, f"Average historical return ({frequency})", f"A{chart_row}")
    _chart(ws, len(names), 29, f"Volatility ({frequency})", f"F{chart_row}")
    ws.print_area = f"A1:J{chart_row+17}"
    background = PatternFill("solid", fgColor=BACKGROUND)
    for row in ws.iter_rows(min_row=3, max_row=chart_row+17, min_col=1, max_col=10):
        for cell in row:
            if cell.fill.patternType is None:
                cell.fill = background
    ws.sheet_properties.tabColor = BLUE

    history = book.create_sheet("Returns Input")
    history.sheet_view.showGridLines = False
    history.freeze_panes = "B2"
    history.sheet_properties.tabColor = GREEN
    history.column_dimensions["A"].width = 18
    for col in range(2, len(names) + 2):
        history.column_dimensions[get_column_letter(col)].width = 22
    _headers(history, 1, ["Date", *names])
    for row_number, (day, values) in enumerate(zip(days, result["returns"]), 2):
        _cell(history, row_number, 1, day, "date")
        for col, value in enumerate(values, 2):
            _cell(history, row_number, col, value, "percent")
    history.print_area = f"A1:{get_column_letter(len(names)+1)}{len(days)+1}"

    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()
