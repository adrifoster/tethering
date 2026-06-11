"""Classes for holding results equilibrium checking"""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class VariableResult:
    """Base result for a single variable.

    Attributes
    ----------
    name (str):
        Variable name
    drift (float):
        absolute delta/yr in the variable's units
    threshold (float | None):
        drift threshold
    passed (bool | None):
        None if no threshold configured or variable was absent.
    equil_year (int | None):
        First spinup year at which equilibrium was continuously maintained.
        None if never achieved or no threshold configured
    is_optional (bool):
        If True, failure produces a warning rather than a fatal result
    """

    name: str
    drift: float
    threshold: float | None
    passed: bool | None
    equil_year: int | None
    is_optional: bool = False


@dataclass
class ScalarResult(VariableResult):
    """Result for a globally-aggregated variable."""

    pass


@dataclass
class GriddedResult(VariableResult):
    """Result for a per-cell gridded variable.

    drift: percent of land area with per-cell drift above cell_threshold
    threshold: pct_landarea threshold
    cell_threshold: per-cell drift threshold in gC/m2/yr
    """

    cell_threshold: float = field(kw_only=True)


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
