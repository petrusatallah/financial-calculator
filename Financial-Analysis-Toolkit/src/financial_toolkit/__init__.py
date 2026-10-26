"""Shared S1 calculation engine for the legacy calculator interfaces."""

from .core import bond_price, bond_ytm, future_value, irr_roots, npv, periods, present_value, rate_roots, required_payment
from .result import CalculationResult, Status
from .service import calculate_bond, calculate_compounding, calculate_irr, calculate_npv
from .validation import InputError, parse_number, parse_positive_integer

__all__ = [
    "CalculationResult", "Status", "InputError", "parse_number", "parse_positive_integer",
    "future_value", "present_value", "required_payment", "periods", "rate_roots",
    "npv", "irr_roots", "bond_price", "bond_ytm", "calculate_compounding",
    "calculate_npv", "calculate_irr", "calculate_bond",
]
