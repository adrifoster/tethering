"""Utility functions"""

from __future__ import annotations
import shutil


def find_tool(name: str) -> str:
    """
    Return the full path to an external tool (ncremap, ncrcat,
    ESMF_RegridWeightGen), checking PATH only.

    Raises RuntimeError with a clear message if not found — the tool
    must be on PATH before Python starts (e.g. via module load nco or
    module load esmf on HPC systems).
    """

    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(
        f"External tool '{name}' not found on PATH. "
        f"Ensure the appropriate package is loaded before starting Python "
        f"(e.g. 'module load nco' for ncremap/ncrcat, "
        f"'module load esmf' for ESMF_RegridWeightGen)."
    )
