#!/usr/bin/env python3
"""
CLI for a single CLM ModelRun.

First-time setup: clm-run --create --config run.yaml

All other commands (many called automatically by pipeline):
    clm-run --root /path/to/run --submit [--dry-run]
    clm-run --root /path/to/run --submit-advance --stage spinup_ad --cime-job-id 2003.desched1
    clm-run --root /path/to/run --advance --stage spinup_ad
    clm-run --root /path/to/run --fail --stage spinup_ad
    clm-run --root /path/to/run --retry [--stage spinup_ad]
    clm-run --root /path/to/run --print-status
"""

import argparse
import sys
from pathlib import Path

from .model_run import ModelRun


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser.

    Returns:
        argparse.ArgumentParser: argument parser
    """
    parser = argparse.ArgumentParser(
        description="Drive a single CLM ModelRun",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--create",
        action="store_true",
        help="Initialize a new run from a YAML config (use with --config)",
    )
    actions.add_argument(
        "--submit", action="store_true", help="Submit the first stage."
    )
    actions.add_argument(
        "--submit-advance",
        action="store_true",
        help="Write and submit the advance job (use with --stage and --cime-job-id)",
    )
    actions.add_argument(
        "--advance",
        action="store_true",
        help="Mark stage done and submit the next stage",
    )
    actions.add_argument("--fail", action="store_true", help="Mark stage as failed")
    actions.add_argument(
        "--retry",
        action="store_true",
        help="Reset and resubmit a failed or stuck stage",
    )
    actions.add_argument("--print-status", action="store_true", help="Print run status")

    parser.add_argument("--config", help="Path to run.yaml (required with --create)")
    parser.add_argument(
        "--root", help="Run root directory (required for all other actions)"
    )
    parser.add_argument("--stage", help="Stage name")
    parser.add_argument(
        "--cime-job-id", help="CIME PBS job ID (required with --submit-advance)"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser):
    """Validate argument combinations.

    Calls parser.error() on failure, which prints usage and exits with code 2

    Args:
        args (argparse.Namespace): parsed namespace from argparse
        parser (argparse.ArgumentParser): ArgumentParser
    """
    if args.create:
        if not args.config:
            parser.error("--config is required with --create")
        return
    if not args.root:
        parser.error("--root is required")

    if args.submit_advance:
        if not args.stage:
            parser.error("--stage is required with --submit-advance")
        if not args.cime_job_id:
            parser.error("--cime-job-id is required with --submit-advance")

    if args.advance and not args.stage:
        parser.error("--stage is required with --advance")

    if args.fail and not args.stage:
        parser.error("--stage is required with --fail")


def dispatch(args: argparse.Namespace) -> int:
    """Execute requested action and return an exit code

    Args:
        args (argparse.Namespace): parsed namespace from argparse

    Returns:
        int: 0 on success, 1 on runtime error
    """
    if args.create:
        run = ModelRun.create(args.config)
        print(f"Initialised run '{run.run_id}' at {run.root}")
        print(f"Next step:  clm-run --root {run.root} --submit")
        return 0

    run = ModelRun.load(Path(args.root))

    if args.print_status:
        print(run.format_status())

    elif args.submit:
        job_id = run.submit(dry_run=args.dry_run)
        if job_id:
            print(f"Submitted: {job_id}")

    elif args.submit_advance:
        job_id = run.submit_advance(args.stage, args.cime_job_id, dry_run=args.dry_run)
        if job_id:
            print(f"Advance job submitted: {job_id}")

    elif args.advance:
        job_id = run.advance(args.stage, dry_run=args.dry_run)
        if job_id:
            print(f"Next stage submitted: {job_id}")

    elif args.fail:
        run.fail(args.stage)

    elif args.retry:
        job_id = run.retry(args.stage, dry_run=args.dry_run)
        if job_id:
            print(f"Resubmitted: {job_id}")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the clm-run CLI.

    Args:
        argv (list[str] | None): argument list (defaults to sys.argv if None). Defaults to None.

    Returns:
        int: exit code, 0 on success, 1 on runtime error, 2 on argument error
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(args, parser)

    try:
        return dispatch(args)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        if args.debug:
            raise
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main()) # pragma: no cover
