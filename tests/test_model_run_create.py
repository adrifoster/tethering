"""Tests for ModelRun.create behavior"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from tethering.model_run import ModelRun, _STATE_FILE


def test_model_run_create_valid_config_passes(run_config_dict):
    """Test ModelRun.create with a valid config passes"""
    ModelRun.create(run_config_dict)


def test_model_run_create_dict_returned_unchanged(run_config_dict):
    """Test ModelRun.create does not modify the input dict"""
    original = copy.deepcopy(run_config_dict)
    ModelRun.create(run_config_dict)
    assert run_config_dict == original


def test_model_run_create_yaml_passes(tmp_path, run_config_dict):
    """Test that ModelRun.create with a yaml file passes"""
    yaml_path = tmp_path / "config.yml"
    yaml_path.write_text(yaml.dump(run_config_dict), encoding="utf-8")
    ModelRun.create(yaml_path)


def test_model_run_create_yaml_path_as_string_passes(tmp_path, run_config_dict):
    """Test that ModelRun.create with a yaml file as a string passes"""
    yaml_path = tmp_path / "config.yml"
    yaml_path.write_text(yaml.dump(run_config_dict), encoding="utf-8")
    ModelRun.create(str(yaml_path))


def test_model_run_create_invalid_type_raises():
    """Test that ModelRun.create with an invalid type raises a TypeError"""
    with pytest.raises(TypeError, match="config must be"):
        ModelRun.create(42)


@pytest.mark.parametrize("missing_key", ["root", "project", "stages", "user"])
def test_model_run_create_missing_required_key_raises(run_config_dict, missing_key):
    """Test that ModelRun.create with missing keys raises a ValueError"""
    del run_config_dict[missing_key]
    with pytest.raises(ValueError, match=missing_key):
        ModelRun.create(run_config_dict)


def test_model_run_create_empty_stages_list_raises(run_config_dict):
    """Test that ModelRun.create with a dict with empty stages list raises a ValueError"""
    run_config_dict["stages"] = []
    with pytest.raises(ValueError, match="stages"):
        ModelRun.create(run_config_dict)


def test_model_run_create_stages_not_a_list_raises(run_config_dict):
    """Test that ModelRun.create with a dict with stages not a list raises a ValueError"""
    run_config_dict["stages"] = "not_a_list"
    with pytest.raises(ValueError, match="stages"):
        ModelRun.create(run_config_dict)


def test_model_run_create_creates_root_directory(run_config_dict):
    """Test that ModelRun.create creates the root directory"""
    run = ModelRun.create(run_config_dict)
    assert run.root.is_dir()


def test_model_run_create_writes_state_file(run_config_dict):
    """Test that ModelRun.create writes the state file"""
    run = ModelRun.create(run_config_dict)
    assert (run.root / _STATE_FILE).exists()


def test_model_run_create_fields_set_correctly(run_config_dict):
    """Test that ModelRun.create sets the fields correctly"""
    run = ModelRun.create(run_config_dict)
    assert run.run_id == "member_0001"
    assert run.project == "PROJ123"
    assert len(run.stages) == 1


def test_model_run_create_default_run_id(run_config_dict):
    """Test that ModelRun.create sets the default run_id if left blank"""
    del run_config_dict["run_id"]
    run = ModelRun.create(run_config_dict)
    assert run.run_id == "run"


def test_model_run_raises_if_state_file_already_exists(run_config_dict):
    """Test that ModelRun.create raises a ValueError if the state file already exists"""
    ModelRun.create(run_config_dict)
    with pytest.raises(FileExistsError, match="already exists"):
        ModelRun.create(run_config_dict)


def test_model_run_creates_nested_root(tmp_path, run_config_dict):
    """Test that ModelRun.create can create a nested root file"""
    run_config_dict["root"] = str(tmp_path / "a" / "b" / "c")
    run = ModelRun.create(run_config_dict)
    assert run.root.is_dir()


def test_model_run_create_test_invalid_config_raises_before_touching_filesystem(
    run_config_dict,
):
    """Test that ModelRun.create with an invalid input dict fails before it creates the root"""
    run_config_dict["stages"] = []
    with pytest.raises(ValueError):
        ModelRun.create(run_config_dict)
    # root should not have been created
    assert not Path(run_config_dict["root"]).exists()


def test_model_run_create_from_yaml(tmp_path, run_config_dict):
    """Test that ModelRun.create can be created from a yaml"""
    yaml_path = tmp_path / "config.yml"
    yaml_path.write_text(yaml.dump(run_config_dict), encoding="utf-8")
    run = ModelRun.create(yaml_path)
    assert run.project == "PROJ123"
