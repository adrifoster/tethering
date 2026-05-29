"""Test that generated scripts pass PBS validation"""

import subprocess
import pytest


@pytest.mark.pbs
def test_qsub_accepts_submit_script(integration_run):
    """Test that generated PBS submit script is accepted by PBS"""
    job_id = integration_run.submit()
    assert job_id, "expected a job ID from qsub"
    result = subprocess.run(["qdel", job_id], capture_output=True, text=True)
    assert result.returncode == 0, f"qdel failed:\n{result.stderr}"


@pytest.mark.pbs
def test_qsub_accepts_advance_script(integration_run):
    """Submit setup job, use real job ID to test advance script submission"""
    # submit setup job — get a real PBS job ID
    setup_job_id = integration_run.submit()
    assert setup_job_id

    try:
        # now submit advance script with the real job ID
        advance_job_id = integration_run.submit_advance("spinup_ad", setup_job_id)
        assert advance_job_id

        # cancel both immediately
        subprocess.run(["qdel", advance_job_id], check=False)
    finally:
        # always cancel the setup job
        subprocess.run(["qdel", setup_job_id], check=False)
