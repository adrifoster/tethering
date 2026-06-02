"""Tests for ModelRun.submit_fail behavior"""

from __future__ import annotations

import subprocess
import time
import pytest

from tethering.model_run import ModelRun
from tethering.stages import StageStatus


def test_submit_fail_unknown_stage_raises(created_run, mock_qsub):
    """Test that submit_fail() raises for an unknown stage name"""
    with pytest.raises(ValueError, match="nonexistent_stage"):
        created_run.submit_fail("nonexistent_stage", "5555.deched")


def test_submit_fail_writes_jobscript(created_run, mock_qsub):
    """Test that ModelRun.submit_fail() actually writes a jobscript"""
    created_run.stages[0].state.status = StageStatus.SUBMITTED
    created_run.stages[0].state.submit_time = time.time() - 100
    created_run.submit_fail("spinup_ad", "55555.deched")
    job_file = created_run.root / f"{created_run.run_id}_spinup_ad_fail.pbs"
    assert job_file.exists()


@pytest.mark.parametrize(
    "field,expected",
    [
        ("PBS -N ", "job_name"),
        ("#PBS -q ", "queue"),
        ("#PBS -A ", "project"),
        ("#PBS -M ", "user"),
        ("#PBS -W depend=afternotok:", "cime_job_id"),
    ],
)
def test_submit_fail_script_contains_pbs_directives(
    created_run, mock_qsub, field, expected
):
    """Test that ModelRun.submit_fail() creates a PBS file with the correct PBS directives"""

    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100

    cime_job_id = "55555.deched"
    created_run.submit_fail("spinup_ad", cime_job_id)

    job_file = (
        created_run.root / f"{created_run.run_id}_spinup_ad_fail.pbs"
    ).read_text()
    values = {
        "job_name": f"{created_run.run_id}_{stage.config.name}",
        "queue": stage.config.queue,
        "project": created_run.project,
        "user": created_run.user,
        "cime_job_id": cime_job_id,
    }
    assert field + values[expected] in job_file


def test_submit_fail_script_references_run_root(created_run, mock_qsub):
    """Test that the job script references the correct run root"""
    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100

    created_run.submit_fail("spinup_ad", "55555.deched")
    content = (
        created_run.root / f"{created_run.run_id}_spinup_ad_fail.pbs"
    ).read_text()
    assert f"clm-run --root {created_run.root}" in content


def test_submit_fail_script_references_stage_name(created_run, mock_qsub):
    """Test that the job script references the correct stage name"""
    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100

    created_run.submit_fail("spinup_ad", "55555.deched")
    content = (
        created_run.root / f"{created_run.run_id}_spinup_ad_fail.pbs"
    ).read_text()
    assert f"--stage {created_run.stages[0].config.name}" in content


def test_submit_fail_returns_job_id(created_run, mock_qsub):
    """Test that submit_fail() returns the PBS job ID"""
    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100
    result = created_run.submit_fail("spinup_ad", "55555.pbs")
    assert result == "12345.pbs"


def test_submit_fail_calls_qsub(created_run, mock_qsub):
    """Test that submit_fail() calls qsub"""
    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100
    created_run.submit_fail("spinup_ad", "55555.pbs")
    mock_qsub.assert_called_once()


def test_submit_fail_dry_run_does_not_call_qsub(created_run, mock_qsub):
    """Test that submit_fail(dry_run=True) does not call qsub"""
    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100
    created_run.submit_fail("spinup_ad", "55555.pbs", dry_run=True)
    mock_qsub.assert_not_called()


def test_submit_fail_dry_run_job_id_format(created_run, mock_qsub):
    """Test that submit_fail(dry_run=True) produces a synthetic DRY_ job ID"""
    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100
    result = created_run.submit_fail("spinup_ad", "55555.pbs", dry_run=True)
    assert result == f"DRY_fail_{created_run.run_id}_spinup_ad"


def test_submit_fail_dry_run_still_writes_script(created_run, mock_qsub):
    """Test that submit_fail(dry_run=True) still writes the advance script"""
    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100
    created_run.submit_fail("spinup_ad", "55555.pbs", dry_run=True)
    job_file = created_run.root / f"{created_run.run_id}_spinup_ad_fail.pbs"
    assert job_file.exists()


def test_submit_fail_qsub_failure_raises(created_run, mocker):
    """Test that a qsub failure propagates out of submit_advance()"""
    mocker.patch.object(
        created_run, "_qsub", side_effect=subprocess.CalledProcessError(1, "qsub")
    )
    with pytest.raises(subprocess.CalledProcessError):
        created_run.submit_fail("spinup_ad", "55555.pbs")


def test_submit_fail_does_not_update_stage_state(created_run, mock_qsub):
    """submit_fail() does not update stage status or job_id
    The advance job ID belongs to the *next* stage, not the current one.
    """
    stage = created_run.stages[0]
    stage.state.status = StageStatus.SUBMITTED
    stage.state.submit_time = time.time() - 100
    created_run.submit_fail("spinup_ad", "55555.pbs")
    assert created_run.stages[0].state.status is StageStatus.SUBMITTED
    assert created_run.stages[0].state.job_id is None
