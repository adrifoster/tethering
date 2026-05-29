"""Tests for ModelRun.__init__ behavior"""

from __future__ import annotations

from pathlib import Path
import pytest

from tethering.model_run import ModelRun


def test_model_run_empty_run_id_raises(tmp_path, ad_stage):
    """Test that ModelRun initialized with an empty run_id raises a ValueError"""
    with pytest.raises(ValueError, match="run_id"):
        ModelRun(
            root=tmp_path,
            run_id="",
            stages=[ad_stage],
            user="user@ucar.edu",
            project="PROJ",
        )


@pytest.mark.parametrize("bad_id", ["has space", "has/slash", "has@symbol"])
def test_model_run_invalid_run_id_characters_raises(tmp_path, ad_stage, bad_id):
    """Test that ModelRun initialized with run_id with bad characters raises a ValueError"""
    with pytest.raises(ValueError, match="run_id"):
        ModelRun(
            root=tmp_path,
            run_id=bad_id,
            stages=[ad_stage],
            user="user@ucar.edu",
            project="PROJ",
        )


@pytest.mark.parametrize("good_id", ["run", "member_0042", "my-spinup", "RUN01"])
def test_model_run_valid_run_id_accepted(tmp_path, ad_stage, good_id):
    """Test that ModelRun initialized with run_id with allowed characters works"""
    run = ModelRun(
        root=tmp_path,
        run_id=good_id,
        stages=[ad_stage],
        user="user@ucar.edu",
        project="PROJ",
    )
    assert run.run_id == good_id


def test_model_run_env_project_accempted(tmp_path, ad_stage, monkeypatch):
    """Test that ModelRun initialized without a project code uses the environment variable"""
    monkeypatch.setenv("PROJECT", "PROJ")
    run = ModelRun(
        root=tmp_path,
        run_id="run",
        stages=[ad_stage],
        user="user@ucar.edu",
        project="",
    )
    assert run.project == "PROJ"
    monkeypatch.delenv("PROJECT", raising=False)


def test_model_run_env_user_accempted(tmp_path, ad_stage, monkeypatch):
    """Test that ModelRun initialized without a user uses the environment variable"""
    monkeypatch.setenv("USER", "user@ucar.edu")
    run = ModelRun(
        root=tmp_path,
        run_id="run",
        stages=[ad_stage],
        user="",
        project="",
    )
    assert run.user == "user@ucar.edu"
    monkeypatch.delenv("USER", raising=False)


def test_model_run_empty_project_raises(tmp_path, ad_stage, monkeypatch):
    """Test that ModelRun initialized without a project code raises a ValueError"""
    monkeypatch.setenv("PROJECT", "")
    with pytest.raises(ValueError, match="project"):
        ModelRun(
            root=tmp_path,
            run_id="run",
            stages=[ad_stage],
            user="user@ucar.edu",
            project="",
        )
    monkeypatch.delenv("PROJECT", raising=False)


def test_model_run_empty_user_raises(tmp_path, ad_stage, monkeypatch):
    """Test that ModelRun initialized without a user raises a ValueError"""
    monkeypatch.setenv("USER", "")
    with pytest.raises(ValueError, match="user"):
        ModelRun(
            root=tmp_path,
            run_id="run",
            stages=[ad_stage],
            user="",
            project="PROJ",
        )
    monkeypatch.delenv("USER", raising=False)


def test_model_run_empty_stages_raises(tmp_path):
    """Test that ModelRun initialized with an empty stages list raises a ValueError"""
    with pytest.raises(ValueError, match="stages"):
        ModelRun(
            root=tmp_path, run_id="run", user="user@ucar.edu", stages=[], project="PROJ"
        )


def test_model_run_stages_stored_as_tuple(tmp_path, ad_stage):
    """Test that ModelRun initializes stages as a tuple"""
    run = ModelRun(
        root=tmp_path,
        run_id="run",
        stages=[ad_stage],
        user="user@ucar.edu",
        project="PROJ",
    )
    assert isinstance(run.stages, tuple)


def test_model_run_root_coerced_to_path(tmp_path, ad_stage):
    """Test that ModelRun initializes run as a Path"""
    run = ModelRun(
        root=str(tmp_path),
        run_id="run",
        stages=[ad_stage],
        user="user@ucar.edu",
        project="PROJ",
    )
    assert isinstance(run.root, Path)
