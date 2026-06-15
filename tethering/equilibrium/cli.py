"""Command-line interface for the CLM spinup equilibrium checker."""

from __future__ import annotations
import argparse
import logging
import os
from pathlib import Path

from .equilibrium_config import EquilibriumConfig
from .equilibrium_checker import EquilibriumChecker

log = logging.getLogger(__name__)

# exit codes chosen so callers can easily interpret output
EXIT_EQUILIBRIUM = 0  # ran fine, in equilibrium
EXIT_NOT_EQUILIBRIUM = 1  # ran fine, not yet equilibrated
EXIT_ERROR = 2  # something broke


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spinup-stability",
        description="Check whether a CLM spinup run has reached equilibrium.",
    )
    p.add_argument("case_name", help="CLM case name, e.g. ctsm53026_BNF_AD")
    p.add_argument(
        "--hist-dir",
        type=Path,
        default=None,
        help="History directory. Overrides the derived "
        "base-dir/<user>/archive/<case>/lnd/hist path when set "
        "(use for non-standard layouts or single-point cases).",
    )
    p.add_argument(
        "--base-dir",
        type=Path,
        default=_env_path("SCRATCH"),
        help="Archive root. Defaults to $SCRATCH.",
    )
    p.add_argument(
        "--user",
        default=os.environ.get("USER"),
        help="Username component of the archive path. Defaults to $USER.",
    )
    p.add_argument(
        "--tape", default="h0", help="History tape (h0, h0a, ...). Default: h0."
    )

    p.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory for the concatenated NetCDF and diagnostic PNG. Default: cwd.",
    )
    p.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="YAML config (thresholds, cycle_years, fates, pct_landarea, se_grid). "
        "Unspecified keys fall back to built-in defaults.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the concatenated file even if a current one exists.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (-v info, -vv debug).",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress the stdout summary (exit code still reflects result).",
    )
    return p


def _env_path(var: str) -> Path | None:
    val = os.environ.get(var)
    return Path(val) if val else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING - 10 * min(args.verbose, 2),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # resolve the path inputs up front so the error names the actual problem
    if args.hist_dir is None:
        if args.base_dir is None:
            log.error(
                "No --base-dir and $SCRATCH is unset; pass --base-dir or --hist-dir."
            )
            return EXIT_ERROR
        if args.user is None:
            log.error("No --user and $USER is unset; pass --user or --hist-dir.")
            return EXIT_ERROR

    try:
        config = EquilibriumConfig.create(args.config)
        result = EquilibriumChecker(config).run(
            case_name=args.case_name,
            output_dir=args.output_dir,
            base_dir=args.base_dir,
            user_name=args.user,
            hist_dir=args.hist_dir,
            tape=args.tape,
            force=args.force,
        )
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        return EXIT_ERROR

    if not args.quiet:
        print(result.summary())
        if result.plot_path is not None:
            print(f"\nDiagnostic plot: {result.plot_path}")

    return EXIT_EQUILIBRIUM if result.passed else EXIT_NOT_EQUILIBRIUM
