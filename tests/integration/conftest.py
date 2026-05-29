import shutil
import pytest
from pathlib import Path

from tethering.model_run import ModelRun

pbs = pytest.mark.skipif(
  shutil.which("qsub") is None,
  reason="PBS not available - run on a cluster"
)

@pytest.fixture
def script_file(tmp_path) -> Path:
    """A minimal script"""
    file_path = tmp_path / "setup.sh"
    file_path.touch()
    return file_path


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
def run_config_dict(tmp_path, ad_config_dict) -> dict:
    return {
        "root": str(tmp_path / "myrun"),
        "user": "name@ucar.edu",
        "run_id": "member_0001",
        "project": "PROJ123",
        "stages": [ad_config_dict],
    }

@pytest.fixture
def created_run(run_config_dict) -> ModelRun:
    return ModelRun.create(run_config_dict)

@pytest.fixture
def mock_qsub(mocker):
    mock = mocker.patch.object(ModelRun, "_qsub", return_value="12345.pbs")
    return mock