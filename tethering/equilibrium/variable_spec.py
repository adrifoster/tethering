"""Data class for managing variables"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

import xarray as xr

_SECINYR = 60.0 * 60.0 * 24.0 * 365.0
_G_TO_PGC = 1.0e-15
_KG_TO_G = 1.0e3


@dataclass
class DriftContext:
    """Drift context passed to VariableSpec.

    Each VariableSpec subclass uses only the fields relevant to it and ignores
    the rest. This avoids a mixed-concern signature on the abstract interface
    where some arguments are only meaningful to one subclass.

    Attributes
    ----------
    nyears_cycle : int | None
        Number of years in the cycle for the timeseries. Generally corresponds to the
        number of years in the meteorological forcing data.
    threshold : float | None
        Drift threshold
    land_area: xr.DataArray | None
        land area [m2]
    cell_threshold: float | None
        per-gridcell area threshold
    spatial_dims: list[str] | None
        spatial dimensions for land area-based summing
    first_year: int | None
        first year on time series
    """

    nyears_cycle: int | None = None
    threshold: float | None = None
    land_area: xr.DataArray | None = None
    cell_threshold: float | None = None
    spatial_dims: list[str] | None = None
    first_year: int | None = None


@dataclass
class DriftResult:
    """Raw output of compute_drift - needed to build a pass/fail verdict or plot data

    Attributes
    -----------
    threshold : float | None
        drift threshold
    cell_threshold: float | None
        per-gridcell area threshold
    reps (list[float | xr.DataArray]):
        per-cycle reductions (floats for scalars; DataArrays for gridded)
    deltas (list[float]):
        signed deltas between cycles
    drift (float):
        drift for the last delta
    passed (bool | None):
        passed equilibrium check?
    equil_year (bool | None):
        first year we pass the check
    ncycles (int | None):
        number of cycles in the timeseries
    """

    threshold: float | None
    cell_threshold: float | None
    reps: list = field(default_factory=list)
    deltas: list = field(default_factory=list)
    drift: float = float("nan")
    passed: bool | None = None
    equil_year: int | None = None
    ncycles: int | None = None


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
    reconstruct: Callable[[xr.Dataset], xr.DataArray] | None = None

    @abstractmethod
    def convert(
        self,
        raw_values: xr.DataArray,
        land_area_m2: xr.DataArray,
        spatial_dims: list[str],
    ) -> xr.DataArray:
        """Calculate thetimeseries that compute_drift consumes (spatially aggregated for
        scalar specs, per-cell for gridded)

        Args:
            raw_values (xr.DataArray): input raw data array
            land_area_m2 (xr.DataArray): land area data array [m2]
            spatial_dims (list[str]): spatial dimensions to aggregate over,
            e.g. ['lat', 'lon'] for regular grids or ['lndgrid'] for spectral element grids

        Returns:
            xr.DataArray: output converted array
        """

    def _cycle_reduce(self, cycle_slice: xr.DataArray) -> float:
        """Sample first year of the cycle; return a float
        Args:
            cycle_slice (xr.DataArray): input slice
            context (DriftContext): DriftContext instance
        """
        return float(cycle_slice.isel(time=0).values)

    def _transition_metric(
        self, prev: float, curr: float, context: DriftContext
    ) -> float:
        """Non-negative drift between two consecutive cycle representations.

        Args:
            prev (float): previous cycle
            curr (float): current cycle
            context (DriftContext): DriftContext instance

        Raises:
            context not supplied
        Returns:
            float: drift between two consecutive cycles
        """
        if context.nyears_cycle is None:
            raise ValueError("context.nyears_cycle is required to compute drift")
        return (curr - prev) / context.nyears_cycle

    def compute_drift(
        self,
        time_series: xr.DataArray,
        context: DriftContext,
    ) -> DriftResult:
        """Compute drift for this variable

        Args:
            time_series (xr.DataArray): input time series
            nyears (int): number of years per cycle
            first_year (int): first year of the dataset
            threshold (float | None, optional): drift threshold. Defaults to None.

        Raises:
            ValueError: required context not supplied

        Returns:
            DriftResult: result from drift calculation
        """
        if context.nyears_cycle is None:
            raise ValueError("context.nyears_cycle is required to compute drift")
        if context.first_year is None:
            raise ValueError("context.first_year is required to compute drift")
        num_years, first_year = context.nyears_cycle, context.first_year
        ncycles = len(time_series.time) // num_years

        reps = [
            self._cycle_reduce(
                time_series.isel(time=slice(i * num_years, (i + 1) * num_years))
            )
            for i in range(ncycles)
        ]
        deltas = [
            self._transition_metric(reps[i], reps[i + 1], context)
            for i in range(ncycles - 1)
        ]
        drift = abs(deltas[-1]) if deltas else float("nan")

        if context.threshold is None:
            passed, equil_year = None, None
        else:
            passed = drift < context.threshold
            equil_year = _find_equil_year(
                deltas, context.threshold, num_years, first_year
            )

        return DriftResult(
            threshold=context.threshold,
            cell_threshold=context.cell_threshold,
            reps=reps,
            deltas=deltas,
            drift=drift,
            passed=passed,
            equil_year=equil_year,
            ncycles=ncycles,
        )


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
        self,
        raw_values: xr.DataArray,
        land_area_m2: xr.DataArray,
        spatial_dims: list[str],
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
        self,
        raw_values: xr.DataArray,
        land_area_m2: xr.DataArray,
        spatial_dims: list[str],
    ):
        la_sum = land_area_m2.sum(dim=spatial_dims)
        return self.cf_base * (land_area_m2 * raw_values).sum(dim=spatial_dims) / la_sum


@dataclass(frozen=True)
class GriddedSpec(VariableSpec):
    """
    Per-cell gridded evaluation. convert() is identity: the per-cell map
    over time is the series that compute_drift consumes (no spatial aggregation,
    no unit conversion — the per-year rate is applied in compute_drift).
    """

    def convert(
        self,
        raw_values: xr.DataArray,
        land_area_m2: xr.DataArray,
        spatial_dims: list[str],
    ) -> xr.DataArray:
        return raw_values

    def _cycle_reduce(self, cycle_slice: xr.DataArray) -> float:
        """Sample first year of the cycle, keeping spatial array

        Args:
            cycle_slice (xr.DataArray): input slice
            context (DriftContext): DriftContext instance
        """
        return cycle_slice.isel(time=0)

    def _transition_metric(
        self, prev: float, curr: float, context: DriftContext
    ) -> float:
        """Non-negative drift between two consecutive cycle representations.

        Args:
            prev (float): previous cycle
            curr (float): current cycle
            context (DriftContext): DriftContext instance

        Raises:
            ValueError: required context not supplied

        Returns:
            float: drift between two consecutive cycles
        """
        if context.nyears_cycle is None:
            raise ValueError("compute_drift requires context.nyears_cycle")
        if context.cell_threshold is None:
            raise ValueError("GriddedSpec requires context.cell_threshold")
        if context.land_area is None:
            raise ValueError("GriddedSpec requires context.land_area")
        if context.spatial_dims is None:
            raise ValueError("GriddedSpec requires context.spatial_dims")

        land_area_sum = context.land_area.sum(dim=context.spatial_dims)
        exceed = abs(curr - prev) / context.nyears_cycle > context.cell_threshold
        return float(
            (
                100.0
                * (context.land_area * exceed).sum(dim=context.spatial_dims)
                / land_area_sum
            )
        )


def _find_equil_year(
    cycle_deltas: list[float],
    threshold: float,
    cycle_years: int,
    first_year: int,
) -> int | None:
    """
    Find the first cycle year from which all subsequent deltas
    remain below threshold. Returns None if equilibrium was never achieved.
    """
    below = [abs(d) < threshold for d in cycle_deltas]
    if all(below):
        return first_year
    if not below[-1]:
        return None
    for j in range(len(below) - 1, -1, -1):
        if not below[j]:
            return first_year + (j + 2) * cycle_years
    return None


def _reconstruct_tws(ds: xr.Dataset) -> xr.DataArray:
    """Reconstruct TWS from water storage components when TWS is absent

    Args:
        ds (xr.Dataset): input dataset with required variables

    Returns:
        xr.DataArray: TWS dataarray
    """
    return (
        ds["H2OCAN"]
        + ds["H2OSNO"]
        + ds["WA"]
        + ds["SOILLIQ"].sum(dim="levgrnd", keep_attrs=True)
        + ds["SOILICE"].sum(dim="levgrnd", keep_attrs=True)
    )

def _reconstruct_fates_totvegc(ds: xr.Dataset) -> xr.DataArray:
    """Reconstruct TOTECOSYSC from FATES_VEGC and TOTSOCM

    Args:
        ds (xr.Dataset): input dataset with required variables

    Returns:
        xr.DataArray: TOTECOSYSC dataarray
    """
    return (
        ds["FATES_VEGC"] + ds["TOTSOMC"]
    )


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
        is_optional=True,
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
        units="m$^2$ m$^{-2}$",
        cf_base=1.0,  # m²/m² * m² / m² -> m²/m² (weighted mean)
    ),
    SummedSpec(
        name="GPP",
        dataset_var="GPP",
        units="PgC yr$^{-1}$",
        cf_base=_G_TO_PGC * _SECINYR,  # g C/m²/s * s/yr * m² -> Pg C/yr
    ),
    MeanSpec(
        name="TWS",
        dataset_var="TWS",
        units="m",
        cf_base=1.0 / 1.0e3,  # mm * m²/m² / 1000 -> m (weighted mean)
        is_optional=True,
        fallback_components=("H2OCAN", "H2OSNO", "WA", "SOILLIQ", "SOILICE"),
        reconstruct=_reconstruct_tws,
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
        units="gC m$^{-2}$ yr$^{-1}$",
    ),
)

# FATES variable specs — only variables that differ from CLM.
# The rest (TOTECOSYSC, TOTSOMC, TWS, H2OSNO, gridded) are identical.
_FATES_OVERRIDES: dict[str, VariableSpec] = {
    "TOTECOSYSC": SummedSpec(
        name="TOTECOSYSC",
        dataset_var="TOTECOSYSC",
        cf_base=_KG_TO_G * _G_TO_PGC,
        units="PgC",
        fallback_components=("FATES_VEGC", "TOTSOMC"),
        reconstruct=_reconstruct_fates_totvegc,
    ),
    "TOTECOSYSC_gridded": GriddedSpec(
        name="TOTECOSYSC_gridded",
        dataset_var="TOTECOSYSC",
        units="gC m$^{-2}$ yr$^{-1}$",
        fallback_components=("FATES_VEGC", "TOTSOMC"),
        cf_base=_KG_TO_G, 
        reconstruct=_reconstruct_fates_totvegc,
        
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
        units="PgC yr$^{-1}$",
        cf_base=_KG_TO_G * _G_TO_PGC * _SECINYR,  # kg C/m²/s -> Pg C/yr
    ),
}


def get_specs(fates: bool = False) -> tuple[VariableSpec, ...]:
    """Return the full variable spec tuple for CLM or FATES."""
    if not fates:
        return _CLM_SPECS
    return tuple(_FATES_OVERRIDES.get(s.name, s) for s in _CLM_SPECS)
