"""Plotting functions for equilibrium checking"""

from __future__ import annotations
from pathlib import Path

import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.colors import BoundaryNorm
import numpy as np

from .variable_spec import DriftResult, GriddedSpec

_DELTA_YLIM = {
    "TOTECOSYSC": 0.2,
    "TOTSOMC": 0.2,
    "TOTVEGC": 0.2,
    "TLAI": 0.2,
    "GPP": 0.2,
    "TWS": 0.05,
    "H2OSNO": 5.0,
}


def plot_outputs(specs, drift_results, first_year, nyears, pct_landarea):

    spec_map = {s.name: s for s in specs}
    scalars = [spec.name for spec in specs if not isinstance(spec, GriddedSpec)]
    gridded = [spec.name for spec in specs if isinstance(spec, GriddedSpec)]

    nrows = len(scalars) + len(gridded)
    ncols = 2
    if nrows == 0:
        return

    # have to build the subplots manually because we are mixing ccrs with regular
    # transforms
    fig = plt.figure(figsize=(8, 2.6 * nrows))
    axes = []
    for i in range(nrows*ncols):
        pos = i + 1
        if pos // 2 <= len(scalars):
            ax = fig.add_subplot(nrows, ncols, pos)
            ax.tick_params(axis="both", which="major", labelsize=10, direction="out")
            ax.tick_params(axis="both", which="minor", direction="out")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
        else:
            ax = fig.add_subplot(nrows, ncols, pos, projection=ccrs.Robinson())
        axes.append(ax)
    axes = np.array(axes).reshape(nrows, ncols)

    for r, var_name in enumerate(scalars):
        av, ad = axes[r]
        _plot_scalar(
            av,
            ad,
            first_year,
            nyears,
            var_name,
            drift_results[var_name],
            spec_map[var_name].units,
        )

    for k, var_name in enumerate(gridded):
        av, ad = axes[len(scalars) + k]
        _plot_gridded(av, ad, first_year, nyears, drift_results[var_name], var_name,
                      spec_map[var_name].units, pct_landarea)

    for ax in axes[-1]:
        ax.set_xlabel("Spinup Year")
    plt.tight_layout()
    return fig
    

def _plot_scalar(av, ad, first_year, nyears, var_name, res, units):

    cycle_years = [first_year + i * nyears for i in range(res.ncycles)]
    delta_years = [
        first_year + i * nyears + nyears // 2 for i in range(res.ncycles - 1)
    ]

    av.plot(cycle_years, res.reps, "-o", ms=3, c="k")
    av.set_ylabel(f"{var_name} [{units}]")
    av.set_title(var_name, fontsize=9)
    ad.plot(delta_years, res.deltas, "-o", ms=3, c="k")
    ad.axhline(0, ls="--", lw=1, color="0.4")
    if res.threshold is not None:
        for s in (+1, -1):
            ad.axhline(s * res.threshold, ls=":", lw=0.8, color="r")
        lim = _DELTA_YLIM.get(var_name)
        if lim:
            ad.set_ylim(-lim, lim)

    eq = _write_eq_year(res.equil_year)
    ad.set_title(f"{var_name}:  {eq}", fontsize=9)
    ad.set_ylabel(f"\u0394{var_name} [{units}/yr]")


def _plot_gridded(av, ad, first_year, nyears, res, var_name, units, pct_landarea):

    delta_years = [
        first_year + i * nyears + nyears // 2 for i in range(res.ncycles - 1)
    ]

    av.plot(delta_years, res.deltas, "-o", ms=3, color="k")
    av.axhline(pct_landarea, ls="--", lw=0.8, color="r")
    av.set_ylim(0, 80)

    eq = _write_eq_year(res.equil_year)
    av.set_title(f"% land in disequilibrium:  {eq}", fontsize=9)
    av.set_ylabel("% land area")
    av.set_xlabel("Spinup Year")
    
    levels = np.arange(-5, 5.01, 1.0)
    diff = (res.reps[-1] - res.reps[-2])/nyears
    diff = diff.where(abs(diff) > res.cell_threshold)
    ad.add_feature(
        cfeature.NaturalEarthFeature("physical", "ocean", "110m", facecolor="white")
    )
    ad.coastlines()
    pcm = ad.pcolormesh(
        diff.lon,
        diff.lat,
        diff,
        transform=ccrs.PlateCarree(),
        shading="auto",
        cmap="RdBu_r",
        norm=BoundaryNorm(levels, 256, extend="both"),
    )
    ad.set_title(f"{var_name} disequilibrium", fontsize=9)
    plt.colorbar(
        pcm,
        ax=ad,
        orientation="horizontal",
        fraction=0.05,
        pad=0.04,
        label=units,
    )
    

def _write_eq_year(equilibrium_year):
    return (
        f"Equil. Year = {equilibrium_year}"
        if equilibrium_year
        else "NOT in equilibrium"
    )

        
    
