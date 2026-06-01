"""Test that generated scripts are valid bash scripts"""

import subprocess
import pytest
import time
from pathlib import Path

from tethering.stages import StageStatus

SCRIPTS = Path(__file__).parent.parent / "smoke" / "scripts"


@pytest.mark.parametrize("script", SCRIPTS.glob("*.sh"))
def test_smoke_script_syntax(script):
    """Test that smoke test scripts have valid bash syntax"""
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"Syntax error in {script.name}:\n{result.stderr}"


def test_submit_script_passes_bash_validation(created_run, mock_qsub):
    """Test that generated PBS submit script passes bash -n validation"""
    created_run.submit()
    job_file = created_run.root / f"{created_run.run_id}_spinup_ad.pbs"
    result = subprocess.run(
        ["bash", "-n", str(job_file)], capture_output=True, text=True
    )
    assert result.returncode == 0, f"Syntax error in {job_file.name}:\n{result.stderr}"


def test_submit_advance_script_passes_bash_validation(created_run, mock_qsub):
    """Test that ModelRun.submit_advance() script passes bash -n validation"""
    created_run.stages[0].state.status = StageStatus.SUBMITTED
    created_run.stages[0].state.submit_time = time.time() - 100
    created_run.submit_advance("spinup_ad", "55555.deched")
    job_file = created_run.root / f"{created_run.run_id}_spinup_ad_advance.pbs"
    result = subprocess.run(
        ["bash", "-n", str(job_file)], capture_output=True, text=True
    )
    assert result.returncode == 0, f"Syntax error in {job_file.name}:\n{result.stderr}"
