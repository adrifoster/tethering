"""Tests for ModelRun.save behavior"""

from __future__ import annotations

import json
import pytest
import yaml

from tethering.model_run import ModelRun
from tethering.stages import StageStatus


def test_model_run_load_restores_run(created_run):
    """Test that ModelRun.load correctly loads the attributes"""
    loaded = ModelRun.load(created_run.root)
    assert loaded.run_id == created_run.run_id
    assert loaded.project == created_run.project
    assert loaded.stages == created_run.stages


def test_model_run_load_root_as_string(created_run):
    """Test that ModelRun.load runs from a string input"""
    loaded = ModelRun.load(str(created_run.root))
    assert loaded.run_id == created_run.run_id


def test_model_run_save_is_atomic(created_run):
    """Test that temp file must not persist after save."""
    created_run.save()
    tmp_file = created_run.root / "run_state.json.tmp"
    assert not tmp_file.exists()


def test_model_run_state_file_does_not_contain_root(created_run):
    """root is supplied to load() explicitly; should not be in the file."""
    state = json.loads((created_run.root / "run_state.json").read_text())
    assert "root" not in state


def test_model_run_roundtrip_preserves_stage_runtime_state(created_run):
    """Mutate runtime state, save, reload — changes must survive."""
    created_run.stages[0].state.status = StageStatus.SUBMITTED
    created_run.stages[0].state.job_id = "99999.pbs"
    created_run.save()
    loaded = ModelRun.load(created_run.root)
    assert loaded.stages[0].state.status is StageStatus.SUBMITTED
    assert loaded.stages[0].state.job_id == "99999.pbs"


def test_model_run_load_missing_state_file_raises(tmp_path):
    """Test that ModelRun.load() raises a ValueError for a missing state file"""
    with pytest.raises(FileNotFoundError, match="run_state.json"):
        ModelRun.load(tmp_path)


def test_load_config_expands_env_vars(tmp_path, run_config_dict, monkeypatch):
    """Test that _load_config expands environment variables in YAML"""
    monkeypatch.setenv("TEST_ROOT", str(tmp_path / "myrun"))
    run_config_dict["root"] = "$TEST_ROOT"
    yaml_path = tmp_path / "config.yml"
    yaml_path.write_text(yaml.dump(run_config_dict))
    run = ModelRun.create(yaml_path)
    assert run.root == tmp_path / "myrun"


def test_save_content_structure(created_run):
    """Test that the state file contains all expected top-level keys
    with correct types"""
    state = json.loads((created_run.root / "run_state.json").read_text())
    assert state["run_id"] == created_run.run_id
    assert state["user"] == created_run.user
    assert state["project"] == created_run.project
    assert isinstance(state["stages"], list)
    assert len(state["stages"]) == len(created_run.stages)
    assert "root" not in state


def test_save_stage_content(created_run):
    """Test that each stage in the state file contains expected keys"""
    state = json.loads((created_run.root / "run_state.json").read_text())
    stage_dict = state["stages"][0]
    assert stage_dict["name"] == created_run.stages[0].config.name
    assert stage_dict["status"] == created_run.stages[0].state.status.to_str()
    assert isinstance(stage_dict["script"], str)  # not a Path object
