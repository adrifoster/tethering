import shutil
import pytest
from pathlib import Path

from tethering.model_run import ModelRun

def pytest_collection_modifyitems(items):
    """Auto-skip PBS tests when qsub is not available."""
    skip_pbs = pytest.mark.skip(reason="PBS not available — run on cluster")
    for item in items:
        if "pbs" in item.keywords:
            if shutil.which("qsub") is None:
                item.add_marker(skip_pbs)

@pytest.fixture
def script_file(tmp_path) -> Path:
    """A minimal script"""
    file_path = tmp_path / "setup.sh"
    file_path.touch()
    return file_path


@pytest.fixture
def ad_stage_config_dict(script_file) -> dict:
    """Smallest valid flat dict for an StageConfig."""
    return {
        "name": "spinup_ad",
        "script": str(script_file),
        "walltime": "06:00:00",
        "queue": "develop",
        "kind": "ad",
    }

@pytest.fixture
def run_config_dict(tmp_path, ad_stage_config_dict) -> dict:
    return {
        "root": str(tmp_path / "myrun"),
        "user": "name@ucar.edu",
        "run_id": "member_0001",
        "project": "PROJ123",
        "stages": [ad_stage_config_dict],
    }

@pytest.fixture
def created_run(run_config_dict) -> ModelRun:
    return ModelRun.create(run_config_dict)

@pytest.fixture
def mock_qsub(mocker):
    mock = mocker.patch.object(ModelRun, "_qsub", return_value="12345.pbs")
    return mock

@pytest.fixture
def integration_run(tmp_path, ad_stage_config_dict):
    """A ModelRun with a real Derecho project code for integration tests."""
    return ModelRun.create({
        "root": str(tmp_path / "myrun"),
        "run_id": "member_0001",
        "project": "",
        "user": "",
        "stages": [ad_stage_config_dict],
    })