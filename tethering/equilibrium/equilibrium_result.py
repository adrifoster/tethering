"""Classes for holding results equilibrium checking"""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass


@dataclass
class VariableResult:
    name: str
    drift: float
    threshold: float | None
    passed: bool | None
    equil_year: int | None
    is_optional: bool = False
    cell_threshold: float | None = None  # only meaningful when the variable is gridded


@dataclass
class EquilibriumResult:
    """
    Full equilibrium check result. The primary output of check_equilibrium().

    Attributes
    ----------
    passed:
        True if all non-optional thresholded variables are in equilibrium.
    variables:
        Per-variable drift details, keyed by variable name.
    plot_path:
        Path to the diagnostic PNG, or None if plotting was skipped.
    case_name:
        The case this result applies to.
    """

    passed: bool
    variables: dict[str, VariableResult]
    plot_path: Path | None
    case_name: str

    @classmethod
    def from_variables(cls, variables, plot_path, case_name):
        passed = all(
            v.passed
            for v in variables.values()
            if v.passed is not None and not v.is_optional
        )
        return cls(
            passed=passed, variables=variables, plot_path=plot_path, case_name=case_name
        )

    def failed_variables(self) -> list[VariableResult]:
        """Non-optional variables that failed the equilibrium check."""
        return [
            v
            for v in self.variables.values()
            if v.passed is False and not v.is_optional
        ]

    def warned_variables(self) -> list[VariableResult]:
        """Optional variables that failed (warnings, not fatal)."""
        return [
            v for v in self.variables.values() if v.passed is False and v.is_optional
        ]

    def summary(self) -> str:
        lines = [
            f"Equilibrium check: {'PASSED' if self.passed else 'FAILED'}"
            f" ({self.case_name})"
        ]
        for v in self.variables.values():
            if v.passed is None:
                status, detail = "---", "[not evaluated or missing]"
            elif v.passed:
                status = "OK*" if v.is_optional else "OK "
                yr = f", equil_year={v.equil_year}" if v.equil_year is not None else ""
                detail = f"drift={v.drift:.4g}{yr}"
            else:
                status = "WRN" if v.is_optional else "ERR"
                detail = f"drift={v.drift:.4g} >= threshold={v.threshold}"
            lines.append(f"  [{status}] {v.name}: {detail}")
        return "\n".join(lines)
