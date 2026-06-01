"""Tests for ModelRun.retry behavior"""

from __future__ import annotations

import pytest

from tethering.stages import StageStatus


def test_retry_calls_submit_stage(created_run, mocker):
    """Test that retry() delegates to _submit_stage"""
    created_run.stages[0].state.status = StageStatus.FAILED
    mock = mocker.patch.object(created_run, "_submit_stage", return_value="12345.pbs")
    created_run.retry("spinup_ad")
    mock.assert_called_once_with(created_run.stages[0], dry_run=False)


def test_retry_resets_to_pending_before_submitting(created_run, mocker):
    """Test that retry() resets stage to PENDING before calling _submit_stage"""
    created_run.stages[0].state.status = StageStatus.FAILED

    def check_status(stage, dry_run=False):
        assert stage.state.status is StageStatus.PENDING
        return "12345.pbs"

    mocker.patch.object(created_run, "_submit_stage", side_effect=check_status)
    created_run.retry("spinup_ad")


def test_retry_persists_pending_before_submitting(created_run, mocker):
    """Test that retry() saves PENDING state before calling _submit_stage"""
    created_run.stages[0].state.status = StageStatus.FAILED
    save_calls = []
    original_save = created_run.save

    def tracking_save():
        save_calls.append(created_run.stages[0].state.status)
        original_save()

    created_run.save = tracking_save
    mocker.patch.object(created_run, "_submit_stage", return_value="12345.pbs")
    created_run.retry("spinup_ad")
    assert StageStatus.PENDING in save_calls


def test_retry_failed_stage(created_run, mocker):
    """Test that retry() accepts a FAILED stage"""
    created_run.stages[0].state.status = StageStatus.FAILED
    mock = mocker.patch.object(created_run, "_submit_stage", return_value="12345.pbs")
    created_run.retry("spinup_ad")
    mock.assert_called_once()


def test_retry_pending_stage(created_run, mocker):
    """Test that retry() accepts a PENDING stage"""
    mock = mocker.patch.object(created_run, "_submit_stage", return_value="12345.pbs")
    created_run.retry("spinup_ad")
    mock.assert_called_once()


@pytest.mark.parametrize("status", [StageStatus.SUBMITTED, StageStatus.DONE])
def test_retry_invalid_status_raises(created_run, mocker, status):
    """Test that retry() raises for non-retryable stage statuses"""
    object.__setattr__(created_run.stages[0].state, "_status", status)
    mocker.patch.object(created_run, "_submit_stage")
    with pytest.raises(ValueError, match="spinup_ad"):
        created_run.retry("spinup_ad")


@pytest.mark.parametrize("status", [StageStatus.SUBMITTED, StageStatus.DONE])
def test_retry_invalid_status_does_not_call_submit_stage(created_run, mocker, status):
    """Test that retry() never calls _submit_stage for invalid statuses"""
    object.__setattr__(created_run.stages[0].state, "_status", status)
    mock = mocker.patch.object(created_run, "_submit_stage")
    with pytest.raises(ValueError):
        created_run.retry("spinup_ad")
    mock.assert_not_called()


def test_retry_uses_current_stage_when_no_name_given(two_stage_run, mocker):
    """Test that retry() falls back to current_stage when stage_name is None"""
    two_stage_run.stages[0].state.status = StageStatus.FAILED
    mock = mocker.patch.object(two_stage_run, "_submit_stage", return_value="12345.pbs")
    two_stage_run.retry(None)
    mock.assert_called_once_with(two_stage_run.stages[0], dry_run=False)


def test_retry_returns_none_when_nothing_to_retry(two_stage_run, mocker):
    """Test that retry(None) returns None when all stages are DONE"""
    for stage in two_stage_run.stages:
        stage.state.status = StageStatus.SUBMITTED
        stage.state.status = StageStatus.DONE
    mocker.patch.object(two_stage_run, "_submit_stage")
    result = two_stage_run.retry(None)
    assert result is None


def test_retry_dry_run_passed_through(created_run, mocker):
    """Test that retry() passes dry_run through to _submit_stage"""
    mock = mocker.patch.object(created_run, "_submit_stage", return_value="DRY_run")
    created_run.retry("spinup_ad", dry_run=True)
    mock.assert_called_once_with(created_run.stages[0], dry_run=True)


def test_retry_unknown_stage_raises(created_run, mocker):
    """Test that retry() raises for an unknown stage name"""
    mocker.patch.object(created_run, "_submit_stage")
    with pytest.raises(ValueError, match="nonexistent"):
        created_run.retry("nonexistent")
