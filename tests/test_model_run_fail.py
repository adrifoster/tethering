"""Tests for ModelRun.fail behavior"""

from __future__ import annotations

import time
import pytest

from tethering.model_run import ModelRun
from tethering.stages import StageStatus


def test_fail_sets_stage_status_to_failed(created_run):
    """Test that fail() marks the stage as FAILED"""
    created_run.stages[0].status.status = StageStatus.SUBMITTED
    created_run.stages[0].status.submit_time = time.time() - 100
    created_run.fail("spinup_ad")
    assert created_run.stages[0].status.status is StageStatus.FAILED


def test_fail_on_done_stage_status_to_failed(created_run):
    """Test that fail() marks the stage as FAILED even if it was DONE"""
    created_run.stages[0].status.status = StageStatus.DONE
    created_run.stages[0].status.submit_time = time.time() - 100
    created_run.fail("spinup_ad")
    assert created_run.stages[0].status.status is StageStatus.FAILED


def test_fail_sets_end_time(created_run):
    """Test that fail() sets end_time on the stage"""
    created_run.stages[0].status.status = StageStatus.SUBMITTED
    created_run.stages[0].status.submit_time = time.time() - 100
    created_run.fail("spinup_ad")
    assert created_run.stages[0].status.end_time is not None


def test_fail_persists_to_disk(created_run, mock_qsub):
    """Test that fail() saves the updated state to disk"""
    created_run.submit()
    created_run.fail("spinup_ad")
    loaded = ModelRun.load(created_run.root)
    assert loaded.stages[0].status.status is StageStatus.FAILED


def test_fail_preserves_job_id(created_run, mock_qsub):
    """Test that fail() does not clobber the existing job ID"""
    created_run.submit()
    created_run.fail("spinup_ad")
    assert created_run.stages[0].status.job_id == "12345.pbs"


def test_fail_preserves_attempts(created_run, mock_qsub):
    """Test that fail() does not reset the attempts counter"""
    created_run.submit()
    created_run.fail("spinup_ad")
    assert created_run.stages[0].status.attempts == 1


def test_fail_unknown_stage_raises(created_run):
    """Test that fail() raises for an unknown stage name"""
    with pytest.raises(ValueError, match="nonexistent_stage"):
        created_run.fail("nonexistent_stage")


@pytest.mark.parametrize(
    "cant_fail_status",
    [
        StageStatus.PENDING,
        StageStatus.FAILED,
    ],
)
def test_advance_non_pending_or_failed_rases(created_run, cant_fail_status):
    """Test that ModelRun.fail() raises a value error if status isn't SUBMITTED"""
    created_run.stages[0].status.status = cant_fail_status
    with pytest.raises(ValueError, match="fail"):
        created_run.fail("spinup_ad")
