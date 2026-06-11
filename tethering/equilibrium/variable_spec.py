"""Data class for managing variables"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import xarray as xr

_SECINYR = 60.0 * 60.0 * 24.0 * 365.0
_G_TO_PGC = 1.0e-15
_KG_TO_G = 1.0e3


@dataclass(frozen=True)
class VariableSpec(ABC):
    """
    Base specification for an equilibrium-check variable.

    Parameters
    ----------
    name (str):
        Configured name used in thresholds dict and results.
        Variables ending in '_gridded' trigger per-cell gridded evaluation.
    dataset_var (str):
        Actual variable name in the CLM history file.
    units (str):
        Units string
    is_optional (bool):
        Whether or not the variable is optional for a post-processing step
    fallback_components (tuplc[str, ...])
        Fallback components for the variable if it can't be found
    """

    name: str
    dataset_var: str
    units: str
    is_optional: bool = False
    fallback_components: tuple[str, ...] = ()

    @abstractmethod
    def convert(
        self, raw_values: xr.DataArray, land_area_m2: xr.DataArray, spatial_dims: list[str]
    ) -> xr.DataArray:
        """Convert to the correct units

        Args:
            raw_values (xr.DataArray): input raw data array
            land_area_m2 (xr.DataArray): land area data array [m2]
            spatial_dims (list[str]): spatial dimensions to aggregate over, 
            e.g. ['lat', 'lon'] for regular grids or ['lndgrid'] for spectral element grids

        Returns:
            xr.DataArray: output converted array
        """


@dataclass(frozen=True)
class SummedSpec(VariableSpec):
    """
    Global weighted sum: cf_base * (land_area_m2 * raw_values).sum()
    Typical use: carbon stocks (PgC), fluxes (PgC/yr).

    Parameters
    ----------
    cf_base (float):
        Base conversion factor for the variable
    """

    cf_base: float = field(kw_only=True)

    def convert(
        self, raw_values: xr.DataArray, land_area_m2: xr.DataArray, spatial_dims: list[str]
    ):
        return self.cf_base * (land_area_m2 * raw_values).sum(dim=spatial_dims)


@dataclass(frozen=True)
class MeanSpec(VariableSpec):
    """
    Area-weighted mean: cf_base * (land_area_m2 * raw_values).sum() / lasum
    Typical use: TLAI (m²/m²), TWS (m), H2OSNO (mm).

    Parameters
    ----------
    cf_base (float):
        Base conversion factor for the variable
    """

    cf_base: float = field(kw_only=True)

    def convert(
        self, raw_values: xr.DataArray, land_area_m2: xr.DataArray, spatial_dims: list[str]
    ):
        la_sum = land_area_m2.sum(dim=spatial_dims)
        return self.cf_base * (land_area_m2 * raw_values).sum(dim=spatial_dims) / la_sum


@dataclass(frozen=True)
class GriddedSpec(VariableSpec):
    """
    Per-cell gridded evaluation — no spatial aggregation.
    Drift is computed on the raw per-cell values directly.
    """

    def convert(
        self, raw_values: xr.DataArray, land_area_m2: xr.DataArray, spatial_dims: str
    ):
        return raw_values  # caller handles drift per-cell


# Standard CLM variable specs, matching NCL script conversions exactly.
# area is km2, converted to m2 via _KM2_TO_M2 when land_area is computed.
_CLM_SPECS: tuple[VariableSpec, ...] = (
    SummedSpec(
        name="TOTECOSYSC",
        dataset_var="TOTECOSYSC",
        units="PgC",
        cf_base=_G_TO_PGC,  # g C/m² * m² -> Pg C
    ),
    SummedSpec(
        name="TOTSOMC",
        dataset_var="TOTSOMC",
        units="PgC",
        cf_base=_G_TO_PGC,
    ),
    SummedSpec(
        name="TOTVEGC",
        dataset_var="TOTVEGC",
        units="PgC",
        cf_base=_G_TO_PGC,
    ),
    MeanSpec(
        name="TLAI",
        dataset_var="TLAI",
        units="m2/m2",
        cf_base=1.0,  # m²/m² * m² / m² -> m²/m² (weighted mean)
    ),
    SummedSpec(
        name="GPP",
        dataset_var="GPP",
        units="PgC/yr",
        cf_base=_G_TO_PGC * _SECINYR,  # g C/m²/s * s/yr * m² -> Pg C/yr
    ),
    MeanSpec(
        name="TWS",
        dataset_var="TWS",
        units="m",
        cf_base=1.0 / 1.0e3,  # mm * m²/m² / 1000 -> m (weighted mean)
        is_optional=True,
        fallback_components=("H2OCAN", "H2OSNO", "WA", "SOILLIQ", "SOILICE"),
    ),
    MeanSpec(
        name="H2OSNO",
        dataset_var="H2OSNO",
        units="mm",
        cf_base=1.0,  # mm * m²/m² -> mm (weighted mean)
    ),
    GriddedSpec(
        name="TOTECOSYSC_gridded",
        dataset_var="TOTECOSYSC",
        units="gC/m2/yr",
    ),
)

# FATES variable specs — only variables that differ from CLM.
# The rest (TOTECOSYSC, TOTSOMC, TWS, H2OSNO, gridded) are identical.
_FATES_OVERRIDES: dict[str, VariableSpec] = {
    "TOTECOSYSC": SummedSpec(
        name="TOTECOSYSC",
        dataset_var="TOTECOSYSC",
        cf_base=_G_TO_PGC,
        units="PgC",
        is_optional=True,
    ),
    "TOTECOSYSC_gridded": GriddedSpec(
        name="TOTECOSYSC_gridded",
        dataset_var="TOTECOSYSC",
        units="gC/m2/yr",
        is_optional=True,
    ),
    "TOTVEGC": SummedSpec(
        name="TOTVEGC",
        dataset_var="FATES_VEGC",
        units="PgC",
        cf_base=_KG_TO_G * _G_TO_PGC,  # kg C/m² -> g -> Pg C
    ),
    "GPP": SummedSpec(
        name="GPP",
        dataset_var="FATES_GPP",
        units="PgC/yr",
        cf_base=_KG_TO_G * _G_TO_PGC * _SECINYR,  # kg C/m²/s -> Pg C/yr
    ),
}


def get_specs(fates: bool = False) -> tuple[VariableSpec, ...]:
    """Return the full variable spec tuple for CLM or FATES."""
    if not fates:
        return _CLM_SPECS
    return tuple(_FATES_OVERRIDES.get(s.name, s) for s in _CLM_SPECS)
