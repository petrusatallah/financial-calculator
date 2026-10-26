"""Typed calculation outcomes; failed work never carries a successful value."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNDEFINED = "UNDEFINED"
    UNSUPPORTED = "UNSUPPORTED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class CalculationResult:
    status: Status
    value: float | tuple[float, ...] | None
    unit: str
    message: str = ""
    warnings: tuple[str, ...] = ()
    assumptions: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == Status.VALID
