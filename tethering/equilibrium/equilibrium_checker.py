""""Class for checking equilibrium conditions"""

from __future__ import annotations
from pathlib import Path
import glob
import logging
import subprocess

import numpy as np
import xarray as xr
import matploblib.pyplot as plt

from .equilibrium_config import EquilibriumConfig
from .variable_spec import get_specs, GriddedSpec
from .equilibrium_result import VariableResult, EquilibriumResult

# area in CLM history files is km2; multiply by 1e6 to get m2
_KM2_TO_M2 = 1.0e6

log = logging.getLogger(__name__)

class EquilibriumChecker:
    """Runs equilibrium checks for a CLM case"""
    
    def __init__(self, config: str | Path | dict | None = None, fates: bool = False):
        self.config = EquilibriumConfig.create(config)
        self.specs = get_specs(fates=fates)
        
    def run(self, base_dir: Path, user_name: str, case_name: str,
            output_dir: Path, tape: str = "h0") -> EquilibriumResult:
        
        # file discovery
        hist_dir = base_dir / user_name / "archive" / case_name / "lnd/hist"
        files = _find_history_files(hist_dir, case_name, tape=tape)
        
        # dataset metadata
        first_ds = xr.open_dataset(files[0])
        frequency = _infer_frequency(first_ds)
        spatial_dims = ["lndgrid"] if _is_se_grid(first_ds) else ["lat", "lon"]
        land_area = first_ds["area"] * _KM2_TO_M2 * first_ds["landfrac"]
        land_area_sum = float(land_area.sum(dim=spatial_dims).values)
        
        # variable resolution and file concatenation
        dataset_vars, absent_optional = self.resolve_dataset_variables(first_ds)
        concat_path = output_dir / f"{case_name}_concat.nc"
        _concat_files(files, dataset_vars + ["landfrac", "landmask"], concat_path)
        
        # load and resample
        ds = xr.open_dataset(str(concat_path), decode_timedelta=False)
        ds.load()
        if frequency == "monthly":
            ds = ds.resample(time="YE").mean()
            
        # cycle setup
        nyears = self.config.cycle_years
        ncycles = len(ds.time) // nyears
        if ncycles < 2:
            raise ValueError(
                f"Need at least 2 complete forcing cycles ({nyears} years each) "
                f"to compute drift; found {len(ds.time)} time steps ({ncycles} cycles)."
            )
        first_year = int(ds.time.dt.year.values[0])
        
        # compute
        timeseries = self.build_timeseries(
            ds, land_area, absent_optional, spatial_dims
        )
        var_results = self._evaluate(
            timeseries, land_area, land_area_sum, nyears, ncycles, first_year, spatial_dims
        )
        
        # plot
        plot_path = output_dir / f"{case_name}_equilibrium.png"
        plot_diagnostics(
            timeseries=timeseries, results=var_results, specs=self.specs,
            land_area=land_area, lasum=land_area_sum, nyears=nyears, ncycles=ncycles,
            pct_landarea=self.config.pct_landarea, first_year=first_year,
            output_path=plot_path, spatial_dims=spatial_dims,
        )
        
        overall_passed = all(
            vr.passed for vr in var_results.values()
            if vr.passed is not None and not vr.is_optional
        )
        
        return EquilibriumResult(
            passed=overall_passed,
            variables=var_results,
            plot_path=plot_path,
            case_name=case_name,
        )
        
    def resolve_dataset_variables(
            self,
            first_ds: xr.Dataset,
        ) -> tuple[list[str], set[str]]:
        """
        Resolve the list of actual dataset variable names to load, handling
        TWS fallback and absent optional variables.

        Returns
        -------
        dataset_vars:
            Variable names to request from the dataset.
        absent_optional:
            Names of optional variables not present in the dataset.
        """
        dataset_vars: set[str] = set()
        absent_optional: set[str] = set()

        for spec in self.specs:
            if spec.dataset_var not in first_ds:
                if spec.fallback_components:
                    if all(v in first_ds for v in spec.fallback_components):
                        log.info("%s absent; will reconstruct from components.", spec.name)
                        dataset_vars.update(spec.fallback_components)
                    elif spec.is_optional:
                        log.warning(
                            "%s absent and components unavailable; skipping.", spec.name
                        )
                        absent_optional.add(spec.name)
                    else:
                        raise KeyError(
                            f"Required variable '{spec.dataset_var}' absent and "
                            f"fallback components {spec.fallback_components} unavailable."
                        )
                elif spec.is_optional:
                    log.warning("%s absent from dataset; skipping.", spec.dataset_var)
                    absent_optional.add(spec.name)
                else:
                    raise KeyError(
                        f"Required variable '{spec.dataset_var}' not found in dataset."
                    )
            else:
                dataset_vars.add(spec.dataset_var)
                
        return list(dataset_vars), absent_optional
    
    def build_timeseries(
        self,
        ds: xr.Dataset,
        land_area: xr.DataArray,
        absent_optional: set[str],
        spatial_dims: list[str],
    ) -> dict[str, xr.DataArray | None]:
        """
        Compute scalar (global) or gridded timeseries for each variable spec.
        Returns None for absent optional variables.
        """
        # reconstruct TWS if needed
        if "TWS" not in ds and all(
            v in ds for v in ["H2OCAN", "H2OSNO", "WA", "SOILLIQ", "SOILICE"]
        ):
            tws_reconstructed = _reconstruct_tws(ds)
    
        timeseries = {}
        for spec in self.specs:
            if spec.name in absent_optional:
                timeseries[spec.name] = None
                continue
    
            # resolve raw DataArray
            if spec.name == "TWS" and "TWS" not in ds:
                if tws_reconstructed is None:
                    timeseries[spec.name] = None
                    continue
                raw = tws_reconstructed
            else:
                raw = ds[spec.dataset_var]
                
            timeseries[spec.name] = spec.convert(raw, land_area, spatial_dims)
    
        return timeseries

    def _evaluate(
        self, timeseries, land_area, lasum, nyears, ncycles, first_year, spatial_dims
    ) -> dict[str, VariableResult]:
        var_results = {}
        for spec in self.specs:
            x = timeseries.get(spec.name)
            threshold = self.config.thresholds.get(spec.name)

            if x is None:
                var_results[spec.name] = VariableResult(
                    name=spec.name, drift=float("nan"),
                    threshold=threshold,
                    gridded_cell_threshold=threshold if isinstance(spec, GriddedSpec) else None,
                    passed=None, equil_year=None,
                    is_optional=spec.is_optional,
                    is_gridded=isinstance(spec, GriddedSpec),
                )
                continue

            if isinstance(spec, GriddedSpec):
                cell_threshold = threshold if threshold is not None else 1.0
                drift, passed, equil_year = gridded_drift(
                    x=x, land_area=land_area, lasum=lasum,
                    nyears=nyears, ncycles=ncycles,
                    cell_threshold=cell_threshold,
                    pct_threshold=self.config.pct_landarea,
                    first_year=first_year, spatial_dims=spatial_dims,
                )
                var_results[spec.name] = VariableResult(
                    name=spec.name, drift=drift,
                    threshold=self.config.pct_landarea,
                    gridded_cell_threshold=cell_threshold,
                    passed=passed, equil_year=equil_year,
                    is_optional=spec.is_optional, is_gridded=True,
                )
            else:
                drift, passed, equil_year = scalar_drift(
                    x=x, nyears=nyears, ncycles=ncycles,
                    threshold=threshold, first_year=first_year,
                )
                var_results[spec.name] = VariableResult(
                    name=spec.name, drift=drift,
                    threshold=threshold, gridded_cell_threshold=None,
                    passed=passed, equil_year=equil_year,
                    is_optional=spec.is_optional, is_gridded=False,
                )
        return var_results
    
def _find_history_files(hist_dir: Path, case_name: str, tape: str = "h0") -> list[str]:
    """Return list of full paths to history files given a history directory, case name, and tape

    Args:
        hist_dir (Path): path to history directory,
            normally scratch/user_name/archive/case_name/lnd/hist
        case_name (str): case name
        tape (str): tape: h0a, h0, etc.

    Raises:
        FileNotFoundError: Could not find any files.

    Returns:
        list[str]: list of full paths to history files
    """
    pattern = str(hist_dir / f"{case_name}.clm2.{tape}*.nc")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No history files found matching pattern:\n {pattern}\n"
            "Check case_name, user_name, and tape"
        )
    return files


def _is_se_grid(ds: xr.Dataset) -> bool:
    """Detect unstructured (SE) grid from landfrac variable dimensions."""
    return "lndgrid" in ds["landfrac"].dims


def _infer_frequency(ds: xr.Dataset) -> str:
    """Infer time frequency ('monthly' or 'annual') from time_bounds.
    Handles both 'nbnd' and 'hist_interval' dimension naming conventions.

    Args:
        ds (xr.Dataset): input dataset

    Raises:
        ValueError: Cannot infer frequency

    Returns:
        str: "monthly" or "annual"
    """
    tb = ds.time_bounds
    if "nbnd" in tb.dims:
        dt = tb.isel(time=-1, nbnd=1) - tb.isel(time=-1, nbnd=0)
    elif "hist_interval" in tb.dims:
        dt = tb.isel(time=-1, hist_interval=1) - tb.isel(time=-1, hist_interval=0)
    else:
        raise ValueError(
            f"Cannot infer frequency: unrecognized time_bounds dims {tb.dims}"
        )
    # dt may be a timedelta, numpy timedelta64 (in ns), or numeric (seconds).
    # Normalize to days in all cases.
    val = dt.values
    if hasattr(val, "astype"):
        # numpy timedelta64 — convert to days as float
        days = float(val.astype("timedelta64[D]").astype(float))
    elif hasattr(val, "days"):
        # Python datetime.timedelta
        days = float(val.days)
    else:
        # Already numeric — assume nanoseconds (legacy behavior)
        days = float(val) / (24 * 60 * 60 * 1e9)
    return "monthly" if days < 40 else "annual"

def _concat_files(files: list[str], dataset_vars: list[str], output_path: Path):
    """Concatenate and variable-subset a list of CLM history files into a
    single temporary NetCDF file using ncrcat.
    
    The caller is responsible for deleting the returned path when done,
    typically via a try/finally block.

    Args:
        files (list[str]): Ordered list of history files to concatenate.
        dataset_vars (list[str]): Variables to extract. time_bounds is always included.
        output_path (Path): Destination path for the concatenated file. The caller is
        responsible for deleting it when done.

    Raises:
        RuntimeError: If ncrcat exits non-zero.
    """
    
    if output_path.exists():
        log.info(
            f"File {output_path} already exists."
        )
        return
    vars_to_extract = list(dict.fromkeys(dataset_vars + ["time_bounds"]))
    var_str = ",".join(vars_to_extract)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ncrcat",
        "-O",
        "-v", var_str,
        *[str(f) for f in files],
        str(output_path),
    ]
    log.info(
        "Running ncrcat over %d files (vars: %s)", len(files), var_str
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ncrcat failed (exit {result.returncode}):\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )
    

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

def scalar_drift(
    x: xr.DataArray,
    nyears: int,
    ncycles: int,
    threshold: float | None,
    first_year: int,
) -> tuple[float, bool | None, int| None]:
    means = cycle_means(x, nyears, ncycles)
    deltas = [(means[i + 1] - means[i]) / nyears for i in range(len(means) - 1)]
    drift = abs(deltas[-1]) if deltas else float("nan")
    if threshold is None:
        return drift, None, None
    return drift, drift < threshold, find_equil_year(deltas, threshold, nyears, first_year)

def find_equil_year(
    cycle_deltas: list[float],
    threshold: float,
    cycle_years: int,
    first_year: int,
) -> int | None:
    """
    Find the first cycle midpoint year from which all subsequent deltas
    remain below threshold. Mirrors NCL backwards-scan logic.
    Returns None if equilibrium was never achieved.
    """
    n = len(cycle_deltas)
    below = [abs(d) < threshold for d in cycle_deltas]
 
    if all(below):
        return first_year + cycle_years // 2
 
    if not below[-1]:
        return None
 
    for i in range(n - 1, -1, -1):
        if not below[i]:
            equil_cycle = i + 1
            return first_year + equil_cycle * cycle_years + cycle_years // 2
 
    return None

def cycle_means(da: xr.DataArray, nyears: int, ncycles: int) -> list[float]:
    return [
        float(da.isel(time=slice(i * nyears, (i + 1) * nyears)).mean("time").values)
        for i in range(ncycles)
    ]
    
def gridded_drift(
    x: xr.DataArray,
    land_area: xr.DataArray,
    lasum: float,
    nyears: int,
    ncycles: int,
    cell_threshold: float,
    pct_threshold: float,
    first_year: int,
    spatial_dims: list[str],
) -> tuple[float, bool | None, int | None]:
    cycle_maps = [
        x.isel(time=slice(i * nyears, (i + 1) * nyears)).mean("time")
        for i in range(ncycles)
    ]
    pct_deltas = [
        float(
            (100.0 * (land_area * (abs(cycle_maps[i + 1] - cycle_maps[i]) / nyears > cell_threshold))
             .sum(dim=spatial_dims) / lasum).values
        )
        for i in range(len(cycle_maps) - 1)
    ]
    drift_pct = pct_deltas[-1] if pct_deltas else float("nan")
    return (
        drift_pct,
        drift_pct < pct_threshold,
        find_equil_year(pct_deltas, pct_threshold, nyears, first_year),
    )

def plot_diagnostics(
    timeseries,
    results,
    specs,
    land_area,
    lasum,
    nyears,
    ncycles,
    pct_landarea,
    first_year,
    output_path,
    spatial_dims,
):

 
    spec_map = {s.name: s for s in specs}
    plotable = {k: v for k, v in timeseries.items() if v is not None}
    n = len(plotable)
    if n == 0:
        return
 
    ncols = 3
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(16, 4 * nrows))
    axes = np.array(axes).flatten()
 
    for j, (var_name, x) in enumerate(plotable.items()):
        ax = axes[j]
        vr = results[var_name]
        unit_str = spec_map[var_name].units
 
        if vr.is_gridded:
            cell_thresh = vr.gridded_cell_threshold or 1.0
            pct_series, times = [], []
            for i in range(ncycles - 1):
                m1 = x.isel(time=slice(i * nyears, (i + 1) * nyears)).mean("time")
                m2 = x.isel(time=slice((i + 1) * nyears, (i + 2) * nyears)).mean("time")
                pct = float(
                    (100.0 * (land_area * (abs(m2 - m1) / nyears > cell_thresh))
                     .sum(dim=spatial_dims) / lasum).values
                )
                pct_series.append(pct)
                times.append(first_year + (i + 1) * nyears + nyears // 2)
            ax.plot(times, pct_series, marker="o")
            ax.axhline(pct_landarea, color="r", linestyle="--", linewidth=1)
            ax.set_ylim([0, 100])
            ax.set_xlabel("Spinup Year")
            grid_note = " [SE grid]" if spatial_dims == ["lndgrid"] else ""
            ax.set_ylabel(
                r"abs($\Delta$" + var_name.replace("_gridded", "") + ")"
                + f">{cell_thresh} {unit_str}/yr\n[% land area{grid_note}]"
            )
            drift_str = f"{vr.drift:.1f}%"
        else:
            for i in range(ncycles):
                years = first_year + i * nyears + np.arange(nyears)
                vals = x.isel(time=slice(i * nyears, (i + 1) * nyears)).values
                ax.plot(years, vals, label=f"cycle_{i:03d}")
            ax.set_ylabel(f"{var_name} [{unit_str}]")
            if j == ncols - 1:
                ax.legend(fontsize=6)
            drift_str = f"drift={vr.drift:.4g} {unit_str}/yr"
 
        if vr.threshold is not None:
            drift_str += f" ({'<' if vr.passed else '>='}{vr.threshold})"
        else:
            drift_str += " [not evaluated]"
        if vr.equil_year is not None:
            drift_str += f"\nEquil yr: {vr.equil_year}"
 
        title = drift_str
        if vr.passed is False:
            title = ("WARN: " if vr.is_optional else "FAILED: ") + title
        ax.set_title(title, fontsize=8)
 
    for ax in axes[n:]:
        ax.set_visible(False)