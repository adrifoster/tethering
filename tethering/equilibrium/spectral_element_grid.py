"""Class for managing spectral element grid information"""

from __future__ import annotations
import logging
import subprocess
import tempfile
from pathlib import Path

import xarray as xr

from .utils import find_tool

log = logging.getLogger(__name__)


class SpectralElementGrid:
    """
    Class for spectral element (unstructured) grid support.

    The weight file is generated automatically using ESMF_RegridWeightGen
    if it does not already exist, mirroring the original spinup_stability NCL script behavior.
    The generated file is named {src_grid}_to_{dst_grid}_{map_method}.nc
    and written to the output_dir

    Parameters
    ----------
    src_grid (str):
        Short name of the source grid (e.g. 'ne16pg3'). Used to derive
        the weight file name.
    src_grid_file (Path):
        Path to the SCRIP description file for the source grid.
    dest_grid (str):
        Short name of the destination grid (e.g. 'f09'). Used to derive
        the weight file name.
    dest_grid_file (Path):
        Path to the SCRIP description file for the destination grid.
    weight_dir (Path):
        Path to where the weight file exists or will be written
    map_method (str):
        Regridding method: 'conserve', 'bilinear', or 'patch'.
        Defaults to 'conserve'.
    """

    def __init__(
        self,
        src_grid: str,
        src_grid_file: Path,
        dest_grid: str,
        dest_grid_file: Path,
        weight_dir: Path,
        map_method: str = "conserve",
    ):

        if not src_grid_file.exists():
            raise FileNotFoundError(
                f"SE src grid SCRIP file not found: {src_grid_file}"
            )
        if not dest_grid_file.exists():
            raise FileNotFoundError(
                f"SE dst grid SCRIP file not found: {dest_grid_file}"
            )
        weight_dir.mkdir(parents=True, exist_ok=True)
        self.weight_dir = weight_dir
            
        self.src_grid_file = Path(src_grid_file)
        self.dest_grid_file = Path(dest_grid_file)
        self.src_grid = src_grid
        self.dest_grid = dest_grid
        self.map_method = map_method
        
        self.weight_file = self.generate_weights()

    @property
    def weight_file_name(self) -> str:
        """Derived weight file name, matching the NCL convention."""
        return f"{self.src_grid}_to_{self.dest_grid}_{self.map_method}.nc"

    # def generate_weights(self):
    #     """Generate an ESMF regridding weight file using ESMF_RegridWeightGen
    #     if it does not already exist, then return its path.

    #     Args:
    #         output_dir (Path): path to output directory where weight file will be written

    #     Raises:
    #         RuntimeError: ESFM_RegridWeightGen failed

    #     Returns:
    #         Path: path to generated weight file
    #     """

    #     weight_file = self.weight_dir / str(self.weight_file_name)

    #     if weight_file.exists():
    #         log.info("Found existing weight file: %s", weight_file)
    #         return weight_file
    #     log.info(
    #         "Generating weight file %s -> %s (%s): %s",
    #         self.src_grid,
    #         self.dest_grid,
    #         self.map_method,
    #         weight_file,
    #     )
    #     cmd = [
    #         find_tool("ESMF_RegridWeightGen"),
    #         "--source",
    #         str(self.src_grid_file),
    #         "--destination",
    #         str(self.dest_grid_file),
    #         "--weight",
    #         str(weight_file),
    #         "--method",
    #         self.map_method,
    #         "--src_type",
    #         "SCRIP",
    #         "--dst_type",
    #         "SCRIP",
    #     ]
    #     result = subprocess.run(cmd, capture_output=True, text=True)
    #     if result.returncode != 0:
    #         raise RuntimeError(
    #             f"ESMF_RegridWeightGen failed (exit {result.returncode}):\n"
    #             f"{result.stderr}"
    #         )
    #     return weight_file

    def regrid_spatial_metadata(self, nc_file: Path) -> xr.Dataset:
        """Run ncremap on a netcdf file to produce a regridded file containing area and 
        landfrac on the destination grid.

        Args:
            nc_file (Path): path to netcdf file

        Raises:
            RuntimeError: ncremap failed

        Returns:
            xr.Dataset: regridded dataset
        """
        with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
            tmp_path = tmp.name
    
        cmd = [
            "ncremap", "-t", "1", "-P", "clm",
            "--sgs_frc=landfrac", "--sgs_msk=landmask",
            "-m", str(self.weight_file),
            str(nc_file), tmp_path,
        ]
        log.info("Running ncremap for spatial metadata: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ncremap failed (exit {result.returncode}):\n{result.stderr}"
            )
        return xr.open_dataset(tmp_path)[["area", "landfrac"]]

    def regrid_data(self,
        input_file: Path,
        output_path: Path,
    ) -> xr.Dataset:
        """Regrid a concatenated CLM history file from SE to FV grid using
        ncremap with a pre-existing weight file.

        Args:
            input_file (Path): Concatenated SE-grid history file (output of concat_files).
            output_path (Path): Destination path for the regridded file. The caller is
            responsible for deleting anything uncessary when done

        Raises:
            FileNotFoundError: can't find the input file
            RuntimeError: ncremap failed

        Returns:
            xr.Dataset: regridded dataset
        """
        if not input_file.exists:
            raise FileNotFoundError(
                f"Concatenated history file not found: {input_file}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            find_tool("ncremap"),
            "-O",
            "-P", "clm",
            "--sgs_frc=landfrac", "--sgs_msk=landmask",
            "-m", str(self.weight_file),
            str(input_file), str(output_path),
        ]
        log.info("Running ncremap for data regridding: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ncremap failed (exit {result.returncode}):\n{result.stderr}"
            )
        ds = xr.open_dataset(str(output_path), decode_timedelta=False)
        ds.load()
        return ds