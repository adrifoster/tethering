"""Tests for ModelRun.submit behavior"""

from __future__ import annotations

import subprocess

import pytest

from tethering.model_run import ModelRun
from tethering.stages import StageStatus


def test_submit_writes_jobscript(created_run, mock_qsub):
    """Test that ModelRun.submit() actually writes a jobscript"""
    created_run.submit()
    job_file = created_run.root / f"{created_run.run_id}_spinup_ad.pbs"
    assert job_file.exists()


def test_submit_raises_if_template_missing(created_run, mocker):
    """Test that submit() raises if the PBS template file is missing"""
    mocker.patch("tethering.model_run._TEMPLATES", created_run.root / "nonexistent")
    with pytest.raises(FileNotFoundError, match="not found"):
        created_run.submit()


@pytest.mark.parametrize(
    "field,expected",
    [
        ("PBS -N ", "job_name"),
        ("#PBS -q ", "queue"),
        ("#PBS -l select=", "select"),
        ("ncpus=", "ncpus"),
        ("mem=", "memory"),
        ("#PBS -l walltime=", "walltime"),
        ("#PBS -A ", "project"),
        ("#PBS -M ", "user"),
    ],
)
def test_submit_script_contains_pbs_directives(created_run, mock_qsub, field, expected):
    """Test that ModelRun.submit() creates a PBS file with the correct PBS directives"""
    created_run.submit()
    job_file = (created_run.root / f"{created_run.run_id}_spinup_ad.pbs").read_text()
    stage = created_run.stages[0]
    values = {
        "job_name": f"{created_run.run_id}_{stage.config.name}",
        "queue": stage.config.queue,
        "select": str(stage.config.select),
        "ncpus": str(stage.config.ncpus),
        "memory": str(stage.config.memory),
        "walltime": stage.config.walltime,
        "project": created_run.project,
        "user": created_run.user,
    }
    assert field + values[expected] in job_file


def test_submit_script_no_depend_line(created_run, mock_qsub):
    """Test that the depend line is not written for the first ModelRun.submit"""
    created_run.submit()
    job_file = (created_run.root / f"{created_run.run_id}_spinup_ad.pbs").read_text()
    assert "#PBS -W depend=" not in job_file


def test_submit_script_trap_references_run_root(created_run, mock_qsub):
    """Test that the ERR trap in the job script references the correct run root"""
    created_run.submit()
    content = (created_run.root / f"{created_run.run_id}_spinup_ad.pbs").read_text()
    assert f"clm-run --root {created_run.root}" in content


def test_submit_script_trap_references_stage_name(created_run, mock_qsub):
    """Test that the ERR trap in the job script references the correct stage name"""
    created_run.submit()
    content = (created_run.root / f"{created_run.run_id}_spinup_ad.pbs").read_text()
    assert f"--fail --stage {created_run.stages[0].config.name}" in content


def test_submit_script_correct_script(created_run, mock_qsub):
    """Test that ModelRun.submit() creates a PBS file with the script"""
    created_run.submit()
    job_file = (created_run.root / f"{created_run.run_id}_spinup_ad.pbs").read_text()
    assert str(created_run.stages[0].config.script) in job_file


def test_submit_script_cd_into_case_root(created_run, mock_qsub):
    """Test that ModelRun.submit() contains a cd into the correct case_root"""
    created_run.submit()
    job_file = (created_run.root / f"{created_run.run_id}_spinup_ad.pbs").read_text()
    case_root = created_run.root / created_run.stages[0].config.name
    assert f"cd {case_root}" in job_file


@pytest.mark.parametrize(
    "field,expected",
    [
        ("--submit-advance --stage ", "name"),
    ],
)
def test_submit_script_correct_clm_run_submit_advance(
    created_run, mock_qsub, field, expected
):
    """Test that ModelRun.submit() creates a PBS file with the correct clm-run commands for failing"""
    created_run.submit()
    job_file = (created_run.root / f"{created_run.run_id}_spinup_ad.pbs").read_text()
    stage = created_run.stages[0]
    values = {
        "name": stage.config.name,
    }
    assert field + values[expected] in job_file


def test_submit_stage_status_set_to_submitted(created_run, mock_qsub):
    """Test that ModelRun.submit() sets the first stage status to SUBMITTED"""
    created_run.submit()
    assert created_run.stages[0].state.status is StageStatus.SUBMITTED


def test_submit_stage_job_id_set(created_run, mock_qsub):
    """Test that ModelRun.submit() stores the job ID returned by qsub on the stage"""
    created_run.submit()
    assert created_run.stages[0].state.job_id == "12345.pbs"


def test_submit_stage_attempts_incremented(created_run, mock_qsub):
    """Test that ModelRun.submit() increments attempts on the stage"""
    created_run.submit()
    assert created_run.stages[0].state.attempts == 1


def test_submit_stage_submit_time_set(created_run, mock_qsub):
    """Test that ModelRun.submit() sets submit_time on the stage"""
    created_run.submit()
    assert created_run.stages[0].state.submit_time is not None


def test_submit_state_persisted_to_disk(created_run, mock_qsub):
    """Test that ModelRun.submit() persists updated stage state to disk"""
    created_run.submit()
    loaded = ModelRun.load(created_run.root)
    assert loaded.stages[0].state.job_id == "12345.pbs"
    assert loaded.stages[0].state.status is StageStatus.SUBMITTED
    assert loaded.stages[0].state.attempts == 1


def test_submit_returns_job_id(created_run, mock_qsub):
    """Test that ModelRun.submit() returns the PBS job ID"""
    assert created_run.submit() == "12345.pbs"


@pytest.mark.parametrize(
    "non_pending_status",
    [
        StageStatus.SUBMITTED,
        StageStatus.DONE,
        StageStatus.FAILED,
    ],
)
def test_submit_skips_if_first_stage_not_pending(
    created_run, mock_qsub, non_pending_status
):
    """Test that ModelRun.submit() is a no-op if the first stage is not PENDING"""
    object.__setattr__(created_run.stages[0].state, "_status", non_pending_status)
    created_run.submit()
    mock_qsub.assert_not_called()


def test_qsub_calls_subprocess_with_correct_args(created_run, mocker):
    """Test that _qsub calls qsub with the correct arguments"""
    mock_run = mocker.patch("tethering.model_run.subprocess.run")
    mock_run.return_value.stdout = "12345.pbs\n"

    created_run.submit()

    job_file = created_run.root / f"{created_run.run_id}_spinup_ad.pbs"
    mock_run.assert_called_once_with(
        ["qsub", str(job_file)],
        capture_output=True,
        text=True,
        check=True,
    )


def test_submit_returns_existing_job_id_when_skipping(created_run, mock_qsub):
    """Test that ModelRun.submit() returns the existing job ID when skipping"""
    created_run.stages[0].state.status = StageStatus.SUBMITTED
    created_run.stages[0].state.job_id = "existing.pbs"
    assert created_run.submit() == "existing.pbs"


def test_submit_returns_empty_string_when_skipping_with_no_job_id(
    created_run, mock_qsub
):
    """Test that ModelRun.submit() returns empty string when skipping a stage with no job ID"""
    created_run.stages[0].state.status = StageStatus.SUBMITTED
    assert created_run.submit() == ""


def test_submit_does_not_mutate_stage_when_skipping(created_run, mock_qsub):
    """Test that ModelRun.submit() does not change stage state when skipping"""
    created_run.stages[0].state.status = StageStatus.SUBMITTED
    created_run.stages[0].state.increment_attempts()
    created_run.stages[0].state.increment_attempts()
    created_run.stages[0].state.increment_attempts()
    created_run.submit()
    assert created_run.stages[0].state.attempts == 3


def test_submit_dry_run_does_not_call_qsub(created_run, mock_qsub):
    """Test that submit(dry_run=True) does not call qsub"""
    created_run.submit(dry_run=True)
    mock_qsub.assert_not_called()


def test_submit_dry_run_job_id_format(created_run, mock_qsub):
    """Test that submit(dry_run=True) produces a synthetic DRY_ job ID"""
    created_run.submit(dry_run=True)
    expected = f"DRY_{created_run.run_id}_{created_run.stages[0].config.name}"
    assert created_run.stages[0].state.job_id == expected


def test_submit_dry_run_still_writes_job_script(created_run, mock_qsub):
    """Test that submit(dry_run=True) still generates the PBS script"""
    created_run.submit(dry_run=True)
    job_file = created_run.root / f"{created_run.run_id}_spinup_ad.pbs"
    assert job_file.exists()


def test_submit_dry_run_still_updates_stage_state(created_run, mock_qsub):
    """Test that submit(dry_run=True) still marks the stage as SUBMITTED"""
    created_run.submit(dry_run=True)
    assert created_run.stages[0].state.status is StageStatus.SUBMITTED


def test_submit_qsub_failure_leaves_stage_pending(created_run, mocker):
    """Test that a qsub failure does not mutate stage state"""
    mocker.patch.object(
        created_run, "_qsub", side_effect=subprocess.CalledProcessError(1, "qsub")
    )
    with pytest.raises(subprocess.CalledProcessError):
        created_run.submit()
    assert created_run.stages[0].state.status is StageStatus.PENDING


def test_submit_qsub_failure_does_not_persist(created_run, mocker):
    """Test that a qsub failure does not write SUBMITTED state to disk"""
    mocker.patch.object(
        created_run, "_qsub", side_effect=subprocess.CalledProcessError(1, "qsub")
    )
    with pytest.raises(subprocess.CalledProcessError):
        created_run.submit()
    loaded = ModelRun.load(created_run.root)
    assert loaded.stages[0].state.status is StageStatus.PENDING
