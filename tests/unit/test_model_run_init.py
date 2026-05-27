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
            user="user@ucar.edu",
            stages=[ad_stage],
            project="PROJ",
        )


@pytest.mark.parametrize("bad_id", ["has space", "has/slash", "has@symbol"])
def test_model_run_invalid_run_id_characters_raises(tmp_path, ad_stage, bad_id):
    """Test that ModelRun initialized with run_id with bad characters raises a ValueError"""
    with pytest.raises(ValueError, match="run_id"):
        ModelRun(
            root=tmp_path,
            run_id=bad_id,
            user="user@ucar.edu",
            stages=[ad_stage],
            project="PROJ",
        )


@pytest.mark.parametrize("good_id", ["run", "member_0042", "my-spinup", "RUN01"])
def test_model_run_valid_run_id_accepted(tmp_path, ad_stage, good_id):
    """Test that ModelRun initialized with run_id with allowed characters works"""
    run = ModelRun(
        root=tmp_path,
        run_id=good_id,
        user="user@ucar.edu",
        stages=[ad_stage],
        project="PROJ",
    )
    assert run.run_id == good_id


def test_model_run_empty_project_raises(tmp_path, ad_stage):
    """Test that ModelRun initialized without a project code raises a ValueError"""
    with pytest.raises(ValueError, match="project"):
        ModelRun(
            root=tmp_path,
            run_id="run",
            user="user@ucar.edu",
            stages=[ad_stage],
            project="",
        )


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
        user="user@ucar.edu",
        stages=[ad_stage],
        project="PROJ",
    )
    assert isinstance(run.stages, tuple)


def test_model_run_root_coerced_to_path(tmp_path, ad_stage):
    """Test that ModelRun initializes run as a Path"""
    run = ModelRun(
        root=str(tmp_path),
        run_id="run",
        user="user@ucar.edu",
        stages=[ad_stage],
        project="PROJ",
    )
    assert isinstance(run.root, Path)
