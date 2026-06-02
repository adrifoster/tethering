#!/usr/bin/env python3
"""
Verify that a tethering smoke test pipeline completed successfully.

Usage:
    python check_smoke_test.py <root>

Exit codes:
    0 — all stages DONE, smoke_result.txt contains PASSED
    1 — pipeline incomplete or failed
"""

from __future__ import annotations

import sys
from pathlib import Path

from tethering.model_run import ModelRun
from tethering.stages import StageStatus


def check(root: Path) -> int:
    # load the run
    try:
        run = ModelRun.load(root)
    except FileNotFoundError:
        print(f"ERROR: no state file found at {root}")
        print("Has the smoke test been submitted?")
        return 1

    # print current status
    print(run.format_status())
    print()

    # check all stages are DONE
    failed = [s for s in run.stages if s.status.status is StageStatus.FAILED]
    pending = [s for s in run.stages if s.status.status is StageStatus.PENDING]
    submitted = [s for s in run.stages if s.status.status is StageStatus.SUBMITTED]
    done = [s for s in run.stages if s.status.status is StageStatus.DONE]

    if failed:
        print(f"FAILED: {len(failed)} stage(s) failed:")
        for s in failed:
            print(f"  ✗ {s.config.name}")
        return 1

    if pending or submitted:
        print("INCOMPLETE: pipeline has not finished yet")
        if submitted:
            print(f"  {len(submitted)} stage(s) still submitted/running")
        if pending:
            print(f"  {len(pending)} stage(s) still pending")
        return 1

    if len(done) != len(run.stages):
        print("INCOMPLETE: not all stages are DONE")
        return 1

    # check smoke_result.txt
    result_file = root / "smoke_result.txt"
    if not result_file.exists():
        print("FAILED: smoke_result.txt not found — smoke_check stage did not complete")
        return 1

    result = result_file.read_text().strip()
    if result != "PASSED":
        print(f"FAILED: smoke_result.txt contains {result!r}, expected 'PASSED'")
        return 1

    # we passed
    print(f"✓ Smoke test PASSED — all {len(done)} stages complete")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(check(Path(sys.argv[1])))
