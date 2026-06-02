"""Fixtures shared across tethering unit tests."""

from pathlib import Path
import pytest

from tethering.model_run import ModelRun
from tethering.stages import StageConfig, StageState, StageStatus, Stage


@pytest.fixture
def script_file(tmp_path) -> Path:
    """A minimal script"""
    file_path = tmp_path / "setup.sh"
    file_path.touch()
    return file_path


@pytest.fixture
def minimal_stage_config_dict(script_file) -> dict:
    """Smallest valid flat dict for StageConfig."""
    return {
        "name": "spinup_ad",
        "script": str(script_file),
        "queue": "regular",
    }


@pytest.fixture
def minimal_stage_config(minimal_stage_config_dict) -> StageConfig:
    """StageConfig from the minimal_stage_config_dict"""
    return StageConfig.from_dict(minimal_stage_config_dict)


@pytest.fixture
def no_cime_stage_config_dict(minimal_stage_config_dict) -> dict:
    """Minimal StageConfig dict with no_cime set to True."""
    return {
        **minimal_stage_config_dict,
        "no_cime": True,
    }


@pytest.fixture
def full_stage_config_dict(minimal_stage_config_dict) -> dict:
    """Full flat dict for StageConfig with all optional fields set."""
    return {
        **minimal_stage_config_dict,
        "kind": "ad",
        "walltime": "06:00:00",
        "spinup_check": False,
        "ncpus": 1,
        "select": 1,
        "memory": "24GB",
        "no_cime": False,
        "extra_pbs": ["#PBS -l gpu=1"],
    }


@pytest.fixture
def full_stage_config(full_stage_config_dict) -> StageConfig:
    """StageConfig from the full_stage_config_dict"""
    return StageConfig.from_dict(full_stage_config_dict)


@pytest.fixture
def ad_stage_config_dict(script_file) -> dict:
    """StageConfig dict with kind ad"""
    return {
        "name": "spinup_ad",
        "script": str(script_file),
        "queue": "regular",
        "kind": "ad",
    }


@pytest.fixture
def sasu_stage_config_dict(script_file) -> dict:
    """StageConfig dict with kind sasu."""
    return {
        "name": "spinup_sasu",
        "script": str(script_file),
        "queue": "regular",
        "kind": "sasu",
    }


@pytest.fixture
def run_config_dict(tmp_path, ad_stage_config_dict) -> dict:
    """Run config dict for instantating a ModelRun"""
    return {
        "root": str(tmp_path / "myrun"),
        "user": "name@ucar.edu",
        "run_id": "member_0001",
        "project": "PROJ123",
        "stages": [ad_stage_config_dict],
    }


@pytest.fixture
def submitted_state() -> StageState:
    """A StageState with a SUBMITTED status"""
    return StageState(
        status=StageStatus.SUBMITTED,
        job_id="12345.pbs",
        case_root="/scratch/cases/spinup_ad",
        submit_time=1_000_000.0,
        end_time=None,
        attempts=1,
    )


@pytest.fixture
def failed_state() -> StageState:
    """A StageState with a FAILED status"""
    return StageState(
        status=StageStatus.FAILED,
        job_id="12345.pbs",
        case_root="/scratch/cases/spinup_ad",
        submit_time=1_000_000.0,
        end_time=3_000_000.0,
        attempts=1,
    )


@pytest.fixture
def full_stage(full_stage_config, submitted_state) -> Stage:
    """A fully instantiated Stage instance"""
    return Stage(config=full_stage_config, state=submitted_state)


@pytest.fixture
def ad_stage(ad_stage_config_dict) -> Stage:
    """A instanted Stage instance from ad_stage_config_dict"""
    return Stage.from_dict(ad_stage_config_dict)


@pytest.fixture
def created_run(run_config_dict) -> ModelRun:
    """An instantiated ModelRun instance from run_config_dict"""
    return ModelRun.create(run_config_dict)


@pytest.fixture
def mock_qsub(mocker):
    """Mock qsub so we can unit test it"""
    mock = mocker.patch.object(ModelRun, "_qsub", return_value="12345.pbs")
    return mock


@pytest.fixture
def two_stage_run(tmp_path, ad_stage_config_dict, sasu_stage_config_dict):
    """A two-stage ModelRun instance"""
    config = {
        "root": str(tmp_path / "two_stage"),
        "run_id": "member_0001",
        "project": "PROJ123",
        "user": "auser",
        "stages": [ad_stage_config_dict, sasu_stage_config_dict],
    }
    return ModelRun.create(config)
