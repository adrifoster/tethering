""" "Class for checking equilibrium conditions"""

from __future__ import annotations
from pathlib import Path
import logging

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt

from .equilibrium_config import EquilibriumConfig
from .variable_spec import (
    get_specs,
    VariableSpec,
    GriddedSpec,
    DriftContext,
    DriftResult,
)
from .equilibrium_result import VariableResult, EquilibriumResult
from .case_loader import CaseLoader
from .plotting import plot_outputs

log = logging.getLogger(__name__)


class EquilibriumChecker:
    """Runs equilibrium checks for a CLM case"""

    def __init__(self, config: str | Path | dict | None = None):
        self.config = EquilibriumConfig.create(config)
        self.specs = get_specs(fates=self.config.fates)

    def run(
        self,
        base_dir: Path,
        user_name: str,
        case_name: str,
        output_dir: Path,
        tape: str = "h0a",
    ) -> EquilibriumResult:
        """Run the actual equilibrium test

        Args:
            base_dir (Path): archive root, usually $SCRATCH
            user_name (str): username component of archive path
            case_name (str): CLM case name, e.g. ctsm53026_BNF_AD
            output_dir (Path): directory for the concatenated netcdf and diagnostic PNG
            tape (str, optional): history tape. Defaults to "h0a".

        Returns:
            EquilibriumResult: EquilibriumResult
        """
        hist_dir = base_dir / user_name / "archive" / case_name / "lnd/hist"
        case = CaseLoader(self.config, self.specs).load(
            hist_dir, case_name, output_dir, tape=tape
        )

        # calculate time series and drift for each variable
        time_series = self._build_time_series(
            case.dataset, case.land_area, case.absent_optional, case.spatial_dims
        )
        drift_results = self._calculate_drift(
            time_series,
            case.land_area,
            case.spatial_dims,
            case.first_year,
        )
        var_results = _to_variable_results(drift_results, self.specs)

        # plot the output
        plot_path = output_dir / f"{case_name}_equilibrium.png"
        self._plot_diagnostics(drift_results, case.first_year)
        
        # return EquilibriumResult.from_variables(var_results, plot_path, case_name)

    def _build_time_series(
        self,
        ds: xr.Dataset,
        land_area: xr.DataArray,
        absent_optional: set[str],
        spatial_dims: list[str],
    ) -> dict[str, xr.DataArray | None]:
        """Compute scalar (global) or gridded time series for each variable spec.
        Returns None for absent optional variables.

        Args:
            ds (xr.Dataset): input dataset
            land_area (xr.DataArray): land area data array [m2]
            absent_optional (set[str]): set of absent optional variables
            spatial_dims (list[str]): spatial dimensions, e.g. ['lat', 'lon']

        Raises:
            KeyError: variable spec absent and not reconstructable

        Returns:
            dict[str, xr.DataArray | None]: time series per variable
        """
        time_series = {}
        for spec in self.specs:
            if spec.name in absent_optional:
                time_series[spec.name] = None
                continue

            if spec.dataset_var in ds:
                raw = ds[spec.dataset_var]
            elif spec.reconstruct is not None:
                raw = spec.reconstruct(ds)
            else:
                # resolve_dataset_variables should have routed this to absent_optional
                # or raised already; reaching here means those two fell out of sync.
                raise KeyError(
                    f"{spec.name!r} ({spec.dataset_var}) absent and not reconstructable"
                )
            time_series[spec.name] = spec.convert(raw, land_area, spatial_dims)

        return time_series

    def _calculate_drift(
        self,
        time_series: dict[str, xr.DataArray],
        land_area: xr.DataArray,
        spatial_dims: list[str],
        first_year: int,
    ) -> dict[str, DriftResult]:
        """Calculate drift for each spec

        Args:
            time_series (dict[str, xr.DataArray]): variable: time-series
            land_area (xr.DataArray): land area data array [m2]
            spatial_dims (list[str]): spatial dimensions, e.g. ['lat', 'lon']
            first_year (int): first year of time series

        Raises:
            ValueError: Gridded variable needs a per-cell threshold

        Returns:
            dict[str, DriftResult]: DriftResult per variable
        """
        drift_results = {}
        for spec in self.specs:

            # gridded specs use cell_threshold as the per-gridcell threshold
            # and config.pct_landarea to check overall passing
            if isinstance(spec, GriddedSpec):
                threshold = self.config.pct_landarea
                cell_threshold = self.config.thresholds.get(spec.name)
                if cell_threshold is None:
                    raise ValueError(
                        f"Gridded variable {spec.name!r} requires cell_threshold "
                        f"in config.thresholds, but none was found."
                    )
            else:
                threshold = self.config.thresholds.get(spec.name)
                cell_threshold = None

            data = time_series.get(spec.name)
            if data is None:
                drift_results[spec.name] = DriftResult(
                    threshold=threshold, cell_threshold=cell_threshold
                )
                continue
            drift_results[spec.name] = spec.compute_drift(
                data,
                DriftContext(
                    nyears_cycle=self.config.cycle_years,
                    threshold=threshold,
                    land_area=land_area,
                    cell_threshold=cell_threshold,
                    spatial_dims=spatial_dims,
                    first_year=first_year,
                ),
            )

        return drift_results
    
    def _plot_diagnostics(self, drift_results, first_year):
        
        # plot the scalar outputs
        plot_outputs(self.specs, drift_results, first_year,
                            self.config.cycle_years, self.config.pct_landarea)
        


def _to_variable_results(
    drift_results: dict[str, DriftResult],
    specs: tuple[VariableSpec, ...],
) -> dict[str, VariableResult]:
    results = {}
    for spec in specs:
        dr = drift_results[spec.name]
        results[spec.name] = VariableResult(
            name=spec.name,
            drift=dr.drift,
            passed=dr.passed,
            equil_year=dr.equil_year,
            threshold=dr.threshold,
            cell_threshold=dr.cell_threshold,
            is_optional=spec.is_optional,
        )
    return results
