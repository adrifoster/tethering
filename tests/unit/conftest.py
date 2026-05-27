"""Fixtures shared across tethering tests."""

import pytest
from pathlib import Path

from tethering.model_run import ModelRun
from tethering.stages import StageConfig, StageState, StageStatus, Stage


@pytest.fixture
def script_file(tmp_path) -> Path:
    """A minimal script"""
    file_path = tmp_path / "setup.sh"
    file_path.touch()
    return file_path


@pytest.fixture
def minimal_config_dict(script_file) -> dict:
    """Smallest valid flat dict for StageConfig."""
    return {
        "name": "spinup_ad",
        "script": str(script_file),
        "walltime": "06:00:00",
        "queue": "regular",
    }


@pytest.fixture
def ad_config_dict(script_file) -> dict:
    """Smallest valid flat dict for an StageConfig."""
    return {
        "name": "spinup_ad",
        "script": str(script_file),
        "walltime": "06:00:00",
        "queue": "regular",
        "kind": "ad",
    }

@pytest.fixture
def postad_config_dict(script_file) -> dict:
    """Smallest valid flat dict for an StageConfig."""
    return {
        "name": "spinup_sasu",
        "script": str(script_file),
        "walltime": "06:00:00",
        "queue": "regular",
        "kind": "sasu",
    }

@pytest.fixture
def full_config_dict(minimal_config_dict) -> dict:
    """Full flat dict for StageConfig with all optional fields set."""
    return {
        **minimal_config_dict,
        "kind": "ad",
        "spinup_check": True,
        "ncpus": 32,
        "select": 4,
        "memory": "64GB",
        "extra_pbs": ["#PBS -l gpu=1"],
    }


@pytest.fixture
def minimal_config(minimal_config_dict) -> StageConfig:
    return StageConfig.from_dict(minimal_config_dict)


@pytest.fixture
def full_config(full_config_dict) -> StageConfig:
    return StageConfig.from_dict(full_config_dict)


@pytest.fixture
def run_config_dict(tmp_path, ad_config_dict) -> dict:
    return {
        "root": str(tmp_path / "myrun"),
        "user": "name@ucar.edu",
        "run_id": "member_0001",
        "project": "PROJ123",
        "stages": [ad_config_dict],
    }


@pytest.fixture
def submitted_state() -> StageState:
    return StageState(
        status=StageStatus.SUBMITTED,
        job_id="12345.pbs",
        case_root="/scratch/cases/spinup_ad",
        submit_time=1_000_000.0,
        end_time=1_003_600.0,
        attempts=1,
    )


@pytest.fixture
def full_stage(full_config, submitted_state) -> Stage:
    return Stage(config=full_config, status=submitted_state)


@pytest.fixture
def ad_stage(ad_config_dict) -> Stage:
    return Stage.from_dict(ad_config_dict)


@pytest.fixture
def created_run(run_config_dict) -> ModelRun:
    return ModelRun.create(run_config_dict)


@pytest.fixture
def mock_qsub(mocker):
    mock = mocker.patch.object(ModelRun, "_qsub", return_value="12345.pbs")
    return mock

@pytest.fixture
def two_stage_run(tmp_path, ad_config_dict, postad_config_dict):
    config = {
        "root": str(tmp_path / "two_stage"),
        "run_id": "member_0001",
        "project": "PROJ123",
        "user": "auser",
        "stages": [ad_config_dict, postad_config_dict],
    }
    return ModelRun.create(config)