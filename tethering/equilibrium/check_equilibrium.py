"""Functions for checking equilibrium status of a run"""

from __future__ import annotations
from pathlib import Path
import glob
import subprocess 
import logging
from typing import Optional

import xarray as xr

from .spectral_element_grid import SpectralElementGrid
from .variable_spec import get_specs, VariableSpec, GriddedSpec

log = logging.getLogger(__name__)

# area in CLM history files is km2; multiply by 1e6 to get m2
_KM2_TO_M2 = 1.0e6

def find_history_files(hist_dir: Path, case_name: str, tape: str) -> list[str]:
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


def get_land_area(
    file: Path, se_grid: SpectralElementGrid | None = None
) -> xr.DataArray:
    """Calculate land area from an input file

    Args:
        file (Path): one file from the dataset
        se_grid (SpectralElementGrid | None, optional): SpectralElementGrid class, can be None if
        the file does not need to be re-gridded. Defaults to None.

    Raises:
        ValueError: We have a spectral element grid but no SpectralElementGrid class was
        supplied

    Returns:
        xr.DataArray: land area data array [m2]
    """

    # open one file
    first_ds = xr.open_dataset(file)

    # regrid if necessary
    if _is_se_grid(first_ds):
        if se_grid is None:
            raise ValueError(
                "Spectral element grid detected but no SpectralElementGrid provided. "
                "Add an SpectralElementGrid section to your YAML config."
            )
        spatial_ds = se_grid.regrid_spatial_metadata(file)
        land_area = spatial_ds["area"] * _KM2_TO_M2 * spatial_ds["landfrac"]
    else:

        # otherwise just return area * landfrac
        land_area = first_ds["area"] * _KM2_TO_M2 * first_ds["landfrac"]

    return land_area


def resolve_dataset_variables(
    specs: tuple[VariableSpec, ...],
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

    for spec in specs:
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

def subset_files(files: list[str], cycle_years: int, frequency: str) -> list[str]:
    """Subset list of files to only the set we need to calculate equilibrium conditions

    Args:
        files (list[str]): Ordered full list of files
        cycle_years (int): number of years to use as a cycle
        frequency (str): history output frequency: "monthly" or "annual"

    Returns:
        list[str]: input list of subset files
    """
    
    files_per_cycle = cycle_years if frequency == "annual" else cycle_years * 12
    n_files_needed = 3 * files_per_cycle
    if len(files) > n_files_needed:
        log.info(
            "Subsetting to last %d files (%d of %d total) for last 3 cycles.",
            n_files_needed, n_files_needed, len(files),
        )
        files = files[-n_files_needed:]
    else:
        log.info(
            "Using all %d files (%d complete cycles).",
            len(files), len(files) // files_per_cycle,
        )
    return files

def concat_files(files: list[str], dataset_vars: list[str], output_path: Path):
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
    
def reconstruct_tws(ds: xr.Dataset) -> xr.DataArray:
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


def build_timeseries(
    ds: xr.Dataset,
    specs: tuple[VariableSpec, ...],
    land_area: xr.DataArray,
    absent_optional: set[str],
) -> dict[str, Optional[xr.DataArray]]:
    """
    Compute scalar (global) or gridded timeseries for each variable spec.
    Returns None for absent optional variables.
    """
    # reconstruct TWS if needed
    tws_reconstructed: Optional[xr.DataArray] = None
    if "TWS" not in ds and all(
        v in ds for v in ["H2OCAN", "H2OSNO", "WA", "SOILLIQ", "SOILICE"]
    ):
        tws_reconstructed = reconstruct_tws(ds)
 
    timeseries: dict[str, Optional[xr.DataArray]] = {}
 
    for spec in specs:
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
            
        timeseries[spec.name] = spec.convert(raw, land_area)
 
    return timeseries