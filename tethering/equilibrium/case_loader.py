"""Classes to deal with loading data for a case"""

from __future__ import annotations
import logging
import glob
import subprocess
from dataclasses import dataclass
from pathlib import Path

import xarray as xr

from .utils import find_tool
from .equilibrium_config import EquilibriumConfig
from .variable_spec import VariableSpec

# area in CLM history files is km2; multiply by 1e6 to get m2
_KM2_TO_M2 = 1.0e6
_MIN_CYCLES = 3

log = logging.getLogger(__name__)


@dataclass
class LoadedCase:
    """Output of the IO layer: all file access is done, everything below is in memory."""

    dataset: xr.Dataset  # annual-resolution
    land_area: xr.DataArray  # m2
    spatial_dims: list[str]
    absent_optional: set[str]
    ncycles: int
    first_year: int


class CaseLoader:
    """Turns a case's history directory into a clean annual dataset + grid metadata."""

    def __init__(self, config: EquilibriumConfig, specs: tuple[VariableSpec, ...]):
        self.config = config
        self.specs = specs

    def load(
        self, hist_dir: Path, case_name: str, output_dir: Path, tape: str = "h0a"
    ) -> LoadedCase:
        files = _find_history_files(hist_dir, case_name, tape=tape)

        with xr.open_dataset(files[0]) as first_ds:
            frequency = _infer_frequency(first_ds)
            spatial_dims = ["lndgrid"] if _is_se_grid(first_ds) else ["lat", "lon"]
            land_area = (first_ds["area"] * _KM2_TO_M2 * first_ds["landfrac"]).compute()
            dataset_vars, absent_optional = _resolve_dataset_variables(
                first_ds, self.specs
            )
            bounds_var = first_ds["time"].attrs.get("bounds", "time_bounds")
        concat_path = output_dir / f"{case_name}_concat.nc"
        _concat_files(
            files, sorted(dataset_vars) + ["landfrac", "landmask", bounds_var], concat_path
        )

        ds = xr.open_dataset(concat_path, decode_timedelta=False)
        ds.load()
        if frequency == "monthly":
            ds = ds.resample(time="YE").mean()
        
        bnd = "nbnd" if "nbnd" in ds["time_bounds"].dims else "hist_interval"
        first_year = int(ds["time_bounds"].isel(time=0, **{bnd: 0}).dt.year.values) 
        ncycles = self._validate_cycles(ds)
        return LoadedCase(ds, land_area, spatial_dims, absent_optional, ncycles, first_year)

    def _validate_cycles(self, ds: xr.Dataset):
        """Make sure we have enough cycles on the dataset to calculate equilibrium
        conditions

        Args:
            ds (xr.Dataset): input dataset

        Raises:
            ValueError: Not enough cycles
        """
        ncycles = len(ds.time) // self.config.cycle_years
        if ncycles < _MIN_CYCLES:
            raise ValueError(
                f"Need at least 2 complete forcing cycles "
                f"({self.config.cycle_years} years each) to compute drift; "
                f"found {len(ds.time)} annual steps ({ncycles} cycles)."
            )
        return ncycles


def _resolve_dataset_variables(
    first_ds: xr.Dataset, specs: tuple[VariableSpec, ...]
) -> tuple[list[str], set[str]]:
    """Resolve the list of actual dataset variable names to load

    Args:
        first_ds (xr.Dataset): loaded first file
        specs (tuple[VariableSpec, ...]): variable specs

    Raises:
        KeyError:
            Required variable absent and fallback components unavailable

    Returns:
        tuple[list[str], set[str]]: dataset variables, optional absent variables
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


def _find_history_files(hist_dir: Path, case_name: str, tape: str = "h0a") -> list[str]:
    """Return list of full paths to history files given a history directory, case name, and tape

    Args:
        hist_dir (Path): path to history directory,
            normally scratch/user_name/archive/case_name/lnd/hist
        case_name (str): case name
        tape (str): history tape: h0a, h0, etc.

    Raises:
        FileNotFoundError: Could not find any files.

    Returns:
        list[str]: list of full paths to history files
    """
    pattern = str(hist_dir / f"{case_name}.clm2.{tape}.*.nc")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No history files found matching pattern:\n {pattern}\n"
            "Check case_name, user_name, and tape. CTSM's averaged stresm is "
            "typically 'h0a' and the instantaneous stresm 'h0i'; equilibrium "
            "checking needs the averaged stream."
        )
    return files


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


def _is_se_grid(ds: xr.Dataset) -> bool:
    """Detect unstructured (SE) grid from landfrac variable dimensions."""
    return "lndgrid" in ds["landfrac"].dims


def _concat_files(files: list[str], dataset_vars: list[str], output_path: Path,
                  force: bool = False):
    """Concatenate and variable-subset a list of CLM history files into a
    single temporary NetCDF file using ncrcat.

    Args:
        files (list[str]): Ordered list of history files to concatenate.
        dataset_vars (list[str]): Variables to extract. time_bounds is always included.
        output_path (Path): Destination path for the concatenated file. The caller is
        responsible for deleting it when done.
        force (bool, optional): force a re-concatting. Defaults to False.

    Raises:
        RuntimeError: If ncrcat exits non-zero.
    """
    vars_to_extract = list(dict.fromkeys(dataset_vars))
    
    if not force and _concat_is_current(output_path, vars_to_extract):
        log.info("Reusing existing concatenated file: %s", output_path)
        return
    
    var_str = ",".join(vars_to_extract)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        find_tool("ncrcat"),
        "-O",
        "-v", var_str,
        *[str(f) for f in files],
        str(output_path),
    ]
    log.info("Running ncrcat over %d files (vars: %s)", len(files), var_str)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ncrcat failed (exit {result.returncode}):\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )

def _concat_is_current(
    output_path: Path,
    required_vars: list[str],
) -> bool:
    """True if output_path exists and already contains all required vars.

    Args:
        output_path (Path): path to concatted file
        required_vars (list[str]): list of required variables
    """
    if not output_path.exists():
        return False

    with xr.open_dataset(output_path, decode_timedelta=False) as ds:
        missing = [v for v in required_vars if v not in ds.variables]
    if missing:
        log.info("Concat file missing %s; rebuilding.", missing)
        return False

    return True