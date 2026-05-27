from __future__ import annotations

import pytest

from tethering.stages import StageStatus

def test_current_stage_returns_first_stage_when_all_pending(two_stage_run):
    """Test that current_stage returns the first stage when all are PENDING"""
    assert two_stage_run.current_stage is two_stage_run.stages[0]


def test_current_stage_returns_second_stage_when_first_done(two_stage_run):
    """Test that current_stage skips DONE stages"""
    two_stage_run.stages[0].status.status = StageStatus.DONE
    assert two_stage_run.current_stage is two_stage_run.stages[1]


def test_current_stage_returns_none_when_all_done(two_stage_run):
    """Test that current_stage returns None when all stages are DONE"""
    for stage in two_stage_run.stages:
        stage.status.status = StageStatus.DONE
    assert two_stage_run.current_stage is None


def test_current_stage_returns_failed_stage(two_stage_run):
    """Test that current_stage returns a FAILED stage — it is non-DONE"""
    two_stage_run.stages[0].status.status = StageStatus.FAILED
    assert two_stage_run.current_stage is two_stage_run.stages[0]


def test_current_stage_returns_submitted_stage(two_stage_run):
    """Test that current_stage returns a SUBMITTED stage — it is non-DONE"""
    two_stage_run.stages[0].status.status = StageStatus.SUBMITTED
    assert two_stage_run.current_stage is two_stage_run.stages[0]


def test_current_stage_single_stage_pending(created_run):
    """Test current_stage with a single PENDING stage"""
    assert created_run.current_stage is created_run.stages[0]


def test_current_stage_single_stage_done(created_run):
    """Test current_stage returns None when the only stage is DONE"""
    created_run.stages[0].status.status = StageStatus.DONE
    assert created_run.current_stage is None