""" "Class for checking equilibrium conditions"""

from __future__ import annotations
from pathlib import Path
import logging

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt

from .equilibrium_config import EquilibriumConfig
from .variable_spec import get_specs, GriddedSpec, DriftContext
from .equilibrium_result import VariableResult, CycleDiagnostics, EquilibriumResult
from .case_loader import CaseLoader

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

        time_series = self._build_time_series(
            case.dataset, case.land_area, case.absent_optional, case.spatial_dims
        )
        var_results, diagnostics = self._evaluate(
            time_series,
            case.land_area,
            case.spatial_dims,
            case.first_year,
        )

        plot_path = output_dir / f"{case_name}_equilibrium.png"
        self._plot_diagnostics(
            timeseries=time_series,
            results=var_results,
            land_area=case.land_area,
            nyears=self.config.cycle_years,
            ncycles=case.ncycles,
            pct_landarea=self.config.pct_landarea,
            output_path=plot_path,
            spatial_dims=case.spatial_dims,
        )
        return EquilibriumResult.from_variables(var_results, plot_path, case_name)
    

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

    def _evaluate(
        self,
        time_series: dict[str, xr.DataArray],
        land_area: xr.DataArray,
        spatial_dims: list[str],
        first_year: int
    ) -> tuple[dict[str, VariableResult], dict[str, CycleDiagnostics]]:
        """Evaluate each variable time series to see if it has reached equilibrium

        Args:
            time_series (dict[str, xr.DataArray]): variable: time-series
            land_area (xr.DataArray): land area data array [m2]
            spatial_dims (list[str]): spatial dimensions, e.g. ['lat', 'lon']
            first_year (int): first year of time series

        Raises:
            ValueError: Gridded variable needs a per-cell threshold 

        Returns:
            dict[str, VariableResult]: VariableResult per variable
        """
        diagnostics = {}
        for spec in self.specs:
            is_gridded = isinstance(spec, GriddedSpec)
            if is_gridded:
                threshold = self.config.pct_landarea
                cell_threshold = self.config.thresholds.get(spec.name)
                if cell_threshold is None:
                    raise ValueError(
                        f"Gridded variable {spec.name!r} requires a per-cell threshold (cell_threshold)"
                        f"in config.thresholds, but none was found."
                    )
            else:
                threshold = self.config.thresholds.get(spec.name)
                cell_threshold = None
            
            data = time_series.get(spec.name)
            if data is None:
                diagnostics[spec.name] = CycleDiagnostics(
                    name=spec.name, is_gridded=is_gridded, is_optional=spec.is_optional,
                    threshold=threshold, cell_threshold=cell_threshold,
                    cycle_years=[], cycle_values=[], delta_years=[], deltas=[],
                    drift=float("nan"), passed=None, equil_year=None)
                continue
            diagnostics[spec.name] = spec.compute_drift(data, DriftContext(
                self.config.cycle_years, threshold, land_area,
                cell_threshold, spatial_dims, first_year))
    
        results = {var_name: diagnostic.to_result() for var_name, diagnostic in diagnostics.items()}
        return results, diagnostics
            

    def _plot_diagnostics(
        self,
        time_series: dict[str, xr.DataArray | None],
        var_results: dict[str, VariableResult],
        land_area: xr.DataArray,
        nyears: int,
        ncycles: int,
        pct_landarea: float,
        output_path: Path,
        spatial_dims: list[str],
    ):

        land_area_sum = land_area.sum(dim=spatial_dims)

        spec_map = {spec.name: spec for spec in self.specs}
        plottable = {
            variable: result
            for variable, result in time_series.items()
            if result is not None
        }
        n = len(plottable)
        if n == 0:
            return

        ncols = 3
        nrows = int(np.ceil(n / ncols))
        fig, axes = plt.subplots(nrows, ncols, figsize=(16, 4 * nrows))
        axes = np.array(axes).flatten()

        for j, (var_name, data) in enumerate(plottable.items()):
            ax = axes[j]
            var_result = var_results[var_name]
            unit_str = spec_map[var_name].units
            first_year = int(data.time.dt.year.values[0])

            if var_result.is_gridded:

                cell_thresh = var_result.cell_threshold or 1.0
                pct_series, times = [], []
                for i in range(ncycles - 1):
                    m1 = data.isel(time=slice(i * nyears, (i + 1) * nyears)).mean("time")
                    m2 = data.isel(time=slice((i + 1) * nyears, (i + 2) * nyears)).mean(
                        "time"
                    )
                    pct = float(
                        (
                            100.0
                            * (land_area * (abs(m2 - m1) / nyears > cell_thresh)).sum(
                                dim=spatial_dims
                            )
                            / land_area_sum
                        ).values
                    )
                    pct_series.append(pct)

                    times.append(first_year + (i + 1) * nyears + nyears // 2)
                ax.plot(times, pct_series, marker="o")
                ax.axhline(pct_landarea, color="r", linestyle="--", linewidth=1)
                ax.set_ylim([0, 100])
                ax.set_xlabel("Spinup Year")
                grid_note = " [SE grid]" if spatial_dims == ["lndgrid"] else ""
                ax.set_ylabel(
                    r"abs($\Delta$"
                    + var_name.replace("_gridded", "")
                    + ")"
                    + f">{cell_thresh} {unit_str}/yr\n[% land area{grid_note}]"
                )
                drift_str = f"{var_result.drift:.1f}%"
            else:
                for i in range(ncycles):
                    years = first_year + i * nyears + np.arange(nyears)
                    vals = data.isel(time=slice(i * nyears, (i + 1) * nyears)).values
                    ax.plot(years, vals, label=f"cycle_{i:03d}")
                ax.set_ylabel(f"{var_name} [{unit_str}]")
                if j == ncols - 1:
                    ax.legend(fontsize=6)
                drift_str = f"drift={var_result.drift:.4g} {unit_str}/yr"

            if var_result.threshold is not None:
                drift_str += f" ({'<' if var_result.passed else '>='}{var_result.threshold})"
            else:
                drift_str += " [not evaluated]"
            if var_result.equil_year is not None:
                drift_str += f"\nEquil yr: {var_result.equil_year}"

            title = drift_str
            if var_result.passed is False:
                title = ("WARN: " if var_result.is_optional else "FAILED: ") + title
            ax.set_title(title, fontsize=8)

        for ax in axes[n:]:
            ax.set_visible(False)

        fig.tight_layout()
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path
