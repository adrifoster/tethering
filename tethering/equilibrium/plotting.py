"""Plotting functions for equilibrium checking"""

from __future__ import annotations
from pathlib import Path

import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.colors import BoundaryNorm
import numpy as np

from .variable_spec import DriftResult, GriddedSpec

_DELTA_YLIM = {"TOTECOSYSC": 0.2, "TOTSOMC": 0.2, "TOTVEGC": 0.2,
               "TLAI": 0.2, "GPP": 0.2, "TWS": 0.05, "H2OSNO": 5.0}


def plot_scalar_outputs(specs, drift_results, first_year, nyears, pct_landarea):
    
    spec_map = {s.name: s for s in specs}
    scalars = [spec.name for spec in specs if not isinstance(spec, GriddedSpec)]
    gridded = [spec.name for spec in specs if isinstance(spec, GriddedSpec)]
    
    nrows = len(scalars) + len(gridded)
    if nrows == 0:
        return
    
    fig, axes = plt.subplots(nrows, 2, figsize=(8, 2.6*nrows), squeeze=False)
    
    for r, var_name in enumerate(scalars):
        av, ad = axes[r]
        _plot_scalar(av, ad, first_year, nyears, var_name, drift_results[var_name], spec_map[var_name].units)
    
    for k, var_name in enumerate(gridded):
        ax = axes[len(scalars) + k, 0]
        _plot_pct_delta(ax, first_year, nyears, drift_results[var_name], pct_landarea)
    
    for ax in axes.flatten():
        ax.tick_params(axis='both', which='major', labelsize=10, direction='out')
        ax.tick_params(axis='both', which='minor', direction='out')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(alpha=0.3, linestyle='--', linewidth=0.5)
    
    axes[len(scalars) + k, 1].set_visible(False)
    for ax in axes[-1]:
        if ax.get_visible():
            ax.set_xlabel("Spinup Year")
    plt.tight_layout()

def _plot_scalar(av, ad, first_year, nyears, var_name, res, units):
    
    cycle_years = [first_year + i*nyears for i in range(res.ncycles)]
    delta_years = [first_year + i*nyears + nyears//2 for i in range(res.ncycles - 1)]

    av.plot(cycle_years, res.reps, "-o", ms=3, c='k')
    av.set_ylabel(f"{var_name} [{units}]")
    av.set_title(var_name, fontsize=9)
    ad.plot(delta_years, res.deltas, "-o", ms=3, c='k')
    ad.axhline(0, ls="--", lw=1, color="0.4")
    if res.threshold is not None:
        for s in (+1, -1):
            ad.axhline(s*res.threshold, ls=":", lw=0.8, color="r")
        lim = _DELTA_YLIM.get(var_name)
        if lim:
            ad.set_ylim(-lim, lim)
    
    eq = _write_eq_year(res.equil_year)
    ad.set_title(f"{var_name}:  {eq}", fontsize=9)
    ad.set_ylabel(f"\u0394{var_name} [{units}/yr]")
    
def _plot_pct_delta(ax, first_year, nyears, res, pct_landarea):
    
    delta_years = [first_year + i*nyears + nyears//2 for i in range(res.ncycles - 1)]
    
    ax.plot(delta_years, res.deltas, "-o", ms=3, color='k')
    ax.axhline(pct_landarea, ls="--", lw=0.8, color="r")
    ax.set_ylim(0, 80)
    
    eq = _write_eq_year(res.equil_year)
    ax.set_title(f"% land in disequilibrium:  {eq}", fontsize=9)
    ax.set_ylabel("% land area")
    ax.set_xlabel("Spinup Year")


def _write_eq_year(equilibrium_year):
    return f"Equil. Year = {equilibrium_year}" if equilibrium_year else "NOT in equilibrium"

def plot_gridded_outputs(specs, drift_results, first_year, nyears):
    
    gridded = [spec.name for spec in specs if isinstance(spec, GriddedSpec)]
    nrows = len(gridded)
    if nrows == 0:
        return
    
    fig, axes = plt.subplots(nrows, 2, figsize=(14, 5*nrows),
                                 subplot_kw={"projection": ccrs.Robinson()}, squeeze=False)
    
    for r, var_name in enumerate(gridded):
        av, ad = axes[r]
        pcm = _plot_pct_maps([av, ad], nyears, drift_results[var_name], var_name)
    fig.colorbar(pcm, ax=axes, orientation="horizontal", fraction=0.05,
                 pad=0.04, label="gC m$^{-2}$ yr$^{-1}$")

def _plot_pct_maps(axes, nyears, res, var_name):
    
    levels = np.arange(-5, 5.01, 1.0)
    pairs = [(res.reps[-1], res.reps[-2], "last cycle"), (res.reps[-2], res.reps[-3], "prev cycle")]
    for ax, (m1, m0, label) in zip(axes, pairs):
        diff = (m1 - m0) / nyears
        diff = diff.where(abs(diff) > res.cell_threshold)
        ax.add_feature(
            cfeature.NaturalEarthFeature("physical", "ocean", "110m", facecolor="white")
        )
        ax.coastlines()
        pcm = ax.pcolormesh(
            diff.lon,
            diff.lat,
            diff,
            transform=ccrs.PlateCarree(),
            shading="auto",
            cmap='RdBu_r',
            norm=BoundaryNorm(levels, 256, extend="both")
        )
        ax.set_title(f"{var_name} disequil ({label})", fontsize=9)
    return pcm