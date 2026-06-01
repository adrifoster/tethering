"""Tests for ModelRun.advance behavior"""

from __future__ import annotations

import pytest
import time

from tethering.model_run import ModelRun
from tethering.stages import StageStatus


def test_advance_marks_stage_done(two_stage_run, mock_qsub):
    """Test that ModelRun.advance() marks the completed stage as DONE"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad")
    assert two_stage_run.stages[0].state.status is StageStatus.DONE


def test_advance_sets_end_time(two_stage_run, mock_qsub):
    """Test that ModelRun.advance() sets end_time on the completed stage"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad")
    assert two_stage_run.stages[0].state.end_time is not None


def test_advance_persists_completed_stage_to_disk(two_stage_run, mock_qsub):
    """Test that ModelRun.advance() saves the DONE state to disk"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad")
    loaded = ModelRun.load(two_stage_run.root)
    assert loaded.stages[0].state.status is StageStatus.DONE


def test_advance_submits_next_stage(two_stage_run, mock_qsub):
    """Test that advance() submits the next PENDING stage"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad")
    assert two_stage_run.stages[1].state.status is StageStatus.SUBMITTED


def test_advance_next_stage_job_id_set(two_stage_run, mock_qsub):
    """Test that advance() sets a job ID on the next stage"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad")
    assert two_stage_run.stages[1].state.job_id == "12345.pbs"


def test_advance_returns_next_job_id(two_stage_run, mock_qsub):
    """Test that advance() returns the PBS job ID of the next stage"""
    two_stage_run.submit()
    result = two_stage_run.advance("spinup_ad")
    assert result == "12345.pbs"


def test_advance_persists_next_stage_submission(two_stage_run, mock_qsub):
    """Test that advance() persists the next stage submission to disk"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad")
    loaded = ModelRun.load(two_stage_run.root)
    assert loaded.stages[1].state.status is StageStatus.SUBMITTED


def test_advance_last_stage_returns_none(two_stage_run, mock_qsub):
    """Test that advance() returns None when the last stage completes"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad")
    result = two_stage_run.advance("spinup_sasu")
    assert result is None


def test_advance_last_stage_does_not_call_qsub(two_stage_run, mock_qsub):
    """Test that advance() does not call qsub when the last stage completes"""
    two_stage_run.stages[0].state.status = StageStatus.SUBMITTED
    two_stage_run.stages[0].state.status = StageStatus.DONE
    two_stage_run.stages[1].state.status = StageStatus.SUBMITTED
    two_stage_run.stages[1].state.submit_time = time.time() - 100
    two_stage_run.advance("spinup_sasu")
    mock_qsub.assert_not_called()


def test_advance_last_stage_still_marks_done(two_stage_run, mock_qsub):
    """Test that advance() marks the last stage DONE even with no next stage"""
    two_stage_run.stages[0].state.status = StageStatus.SUBMITTED
    two_stage_run.stages[0].state.status = StageStatus.DONE
    two_stage_run.stages[1].state.status = StageStatus.SUBMITTED
    two_stage_run.stages[1].state.submit_time = time.time() - 100
    two_stage_run.advance("spinup_sasu")
    assert two_stage_run.stages[1].state.status is StageStatus.DONE


def test_advance_dry_run_does_not_call_qsub(two_stage_run, mock_qsub):
    """Test that advance(dry_run=True) does not call qsub"""
    two_stage_run.stages[0].state.status = StageStatus.SUBMITTED
    two_stage_run.stages[0].state.submit_time = time.time() - 100
    two_stage_run.advance("spinup_ad", dry_run=True)
    mock_qsub.assert_not_called()


def test_advance_dry_run_still_marks_stage_done(two_stage_run, mock_qsub):
    """Test that advance(dry_run=True) still marks the completed stage as DONE"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad", dry_run=True)
    assert two_stage_run.stages[0].state.status is StageStatus.DONE


def test_advance_dry_run_next_stage_job_id_format(two_stage_run, mock_qsub):
    """Test that advance(dry_run=True) gives the next stage a DRY_ job ID"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad", dry_run=True)
    expected = f"DRY_{two_stage_run.run_id}_spinup_sasu"
    assert two_stage_run.stages[1].state.job_id == expected


def test_advance_unknown_stage_raises(two_stage_run, mock_qsub):
    """Test that advance() raises for an unknown stage name"""
    with pytest.raises(ValueError, match="nonexistent_stage"):
        two_stage_run.advance("nonexistent_stage")


def test_advance_does_not_affect_other_stages(two_stage_run, mock_qsub):
    """Test that advance() only modifies the completed and next stages"""
    two_stage_run.submit()
    two_stage_run.advance("spinup_ad")
    # completed stage is DONE, next is SUBMITTED — no others should change
    assert two_stage_run.stages[0].state.status is StageStatus.DONE
    assert two_stage_run.stages[1].state.status is StageStatus.SUBMITTED

@pytest.mark.parametrize(
    "cant_advance_status",
    [
        StageStatus.FAILED,
        StageStatus.PENDING,
        StageStatus.DONE,
    ],
)
def test_advance_non_pending_or_failed_rases(
    created_run, mock_qsub, cant_advance_status
):
    """Test that ModelRun.advance() raises a value error if status isn't PENDING or FAILED"""
    object.__setattr__(created_run.stages[0].state, "_status", cant_advance_status)
    with pytest.raises(ValueError, match="advance"):
        created_run.advance("spinup_ad")
