"""Equilibrium config for starting up an equilibrium test"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .spectral_element_grid import SpectralElementGrid

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "TOTECOSYSC": 0.02,
    "TOTSOMC": 0.02,
    "TOTVEGC": 0.02,
    "TLAI": 0.02,
    "GPP": 0.02,
    "TWS": 0.001,
    "H2OSNO": 1.0,
    "TOTECOSYSC_gridded": 1.0,
}

_DEFAULT_CYCLE_YEARS = 20
_DEFAULT_PCT_LAND = 3.0


@dataclass
class EquilibriumConfig:
    """
    User-configurable parameters for equilibrium checking.

    Variable definitions (which variables to check, their dataset names,
    units, and conversion factors) are hard-coded in _CLM_SPECS and
    _FATES_OVERRIDES. Only thresholds and run parameters belong here.

    Parameters
    ----------
    cycle_years:
        Number of years per cycle, generally per met-forcing cycle
    thresholds:
        Dict mapping variable name -> drift threshold.
        For standard variables: maximum acceptable |delta/yr| in the
        variable's units (e.g. PgC/yr, m2/m2/yr).
        For TOTECOSYSC_gridded: per-cell drift threshold in gC/m2/yr;
        pass/fail is then determined by pct_landarea.
    fates:
        If True, use FATES output variables for TOTVEGC, TLAI, and GPP.
    pct_landarea:
        For TOTECOSYSC_gridded: max acceptable % of land area with
        per-cell drift above the gridded threshold. Defaults to 3.0.
    se_grid:
        If provided, treat history files as spectral element (unstructured) grid.
        If None, assume regular gridded lat/lon.
    """

    cycle_years: int = _DEFAULT_CYCLE_YEARS
    thresholds: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_THRESHOLDS)
    )
    fates: bool = False
    pct_landarea: float = _DEFAULT_PCT_LAND
    se_grid: SpectralElementGrid | None = None

    def __post_init__(self):
        if self.cycle_years < 1:
            raise ValueError(f"cycle_years must be >= 1, got {self.cycle_years}.")
        if not self.thresholds:
            raise ValueError("thresholds must not be empty.")

    @classmethod
    def create(cls, config: str | Path | dict | None = None) -> EquilibriumConfig:

        cfg = _load_config(config if config else {})

        se_grid = None
        if "se_grid" in cfg:
            se_grid = SpectralElementGrid.from_dict(cfg["se_grid"])

        return cls(
            cycle_years=cfg.get("cycle_years", _DEFAULT_CYCLE_YEARS),
            thresholds={**_DEFAULT_THRESHOLDS, **cfg.get("thresholds", {})},
            fates=cfg.get("fates", False),
            pct_landarea=cfg.get("pct_landarea", _DEFAULT_PCT_LAND),
            se_grid=se_grid,
        )


def _load_config(config: Path | str | dict) -> dict:
    """Normalise *config* to a plain dict.

    Args:
        config: a dict, or a path to a YAML file.

    Returns:
        A plain dict with the config contents.

    Raises:
        TypeError: if *config* is not a dict, str, or Path.
    """
    if isinstance(config, dict):
        return config
    if isinstance(config, (str, Path)):
        with open(config, encoding="utf-8") as f:
            return yaml.safe_load(f)
    raise TypeError(
        f"config must be a dict, str, or Path, got {type(config).__name__!r}."
    )
