"""
Tests for tethering.stages:
"""

from __future__ import annotations

import inspect
from pathlib import Path
import pytest

from tethering.stages import (
    Stage,
    StageConfig,
    StageKind,
    StageState,
    StageStatus,
    _RUNTIME_KEYS,
)

# ---------------------------------------------------------------------------
# StageStatus
# ---------------------------------------------------------------------------


def test_stage_status_from_str_valid():
    """Test that the StageStatus.from_str works as intended"""
    assert StageStatus.from_str("pending") is StageStatus.PENDING
    assert StageStatus.from_str("failed") is StageStatus.FAILED
    assert StageStatus.from_str("failed ") is StageStatus.FAILED
    assert StageStatus.from_str("FAILED") is StageStatus.FAILED


def test_stage_status_to_str_valid():
    """Test that the StageStatus.to_str works as intended"""
    assert StageStatus.PENDING.to_str() == "pending"
    assert StageStatus.SUBMITTED.to_str() == "submitted"


def test_stage_status_roundtrip():
    """Test that all members of StageStatus can be "roundtripped" from the Enum
    to a string, and back to a member
    """
    for member in StageStatus:
        assert StageStatus.from_str(member.to_str()) is member


def test_stage_status_from_str_invalid_rases():
    """Test that StageStatus.from_str raises a ValueError with an invalid str"""
    with pytest.raises(ValueError, match="Invalid StageStatus"):
        StageStatus.from_str("not_a_status")


def test_stage_status_no_implicit_string_equality():
    """Enum members must not compare equal to raw strings"""
    assert StageStatus.DONE != "done"


# ---------------------------------------------------------------------------
# StageKind
# ---------------------------------------------------------------------------


def test_stage_kind_from_str_valid():
    """Test that StageKind.from_str works as intended"""
    assert StageKind.from_str("ad") is StageKind.AD
    assert StageKind.from_str("sasu") is StageKind.SASU
    assert StageKind.from_str("SASU") is StageKind.SASU
    assert StageKind.from_str("sasu ") is StageKind.SASU


def test_stage_kind_to_str_valid():
    """Test that the StageKind.to_str works as intended"""
    assert StageKind.AD.to_str() == "ad"
    assert StageKind.SASU.to_str() == "sasu"


def test_stage_kind_roundtrip():
    """Test that all members of StageStatus can be "roundtripped" from the Enum
    to a string, and back to a member
    """
    for member in StageKind:
        assert StageKind.from_str(member.to_str()) is member


def test_stage_kind_from_str_invalid_rases():
    """Test that StageKind.from_str raises a ValueError with an invalid str"""
    with pytest.raises(ValueError, match="Invalid StageKind"):
        StageKind.from_str("not_a_status")


def test_stage_kind_no_implicit_string_equality():
    """Enum members must not compare equal to raw strings"""
    assert StageKind.AD != "ad"


# ---------------------------------------------------------------------------
# StageState
# ---------------------------------------------------------------------------


def test_stage_state_can_set_submit_time():
    """Test StageState can set the submit time correctly"""
    state = StageState()
    state.submit_time = 1000000.0
    assert state.submit_time == 1000000.0


def test_stage_state_can_set_end_time():
    """Test StageState can set the end time correctly"""
    state = StageState()
    state.submit_time = 1000000.0
    state.end_time = 3000000.0
    assert state.end_time == 3000000.0


def test_stage_state_cannot_set_submit_time_after_end_time(failed_state):
    """Test StageState cannot set submit time after end_time"""
    with pytest.raises(ValueError, match="end_time"):
        failed_state.submit_time = 5_000_000.0


def test_stage_state_cannot_set_end_time_before_submit_time(submitted_state):
    """Test StageState cannot set end_time before submit_time"""
    state = StageState(submit_time=1_000_000.0)
    with pytest.raises(ValueError, match="cannot precede"):
        state.end_time = 500_000.0


def test_stage_state_increment_attempts():
    """Test StageState.increment_attempts"""
    state = StageState()
    state.increment_attempts()
    assert state.attempts == 1
    state.increment_attempts()
    assert state.attempts == 2


def test_stage_state_status_setter():
    """Test StageState status setter"""
    state = StageState()
    state.status = StageStatus.SUBMITTED
    assert state.status is StageStatus.SUBMITTED


def test_stage_state_status_setter_with_string_failes():
    """Test StageState status setter"""
    state = StageState()
    with pytest.raises(TypeError, match="status"):
        state.status = "done"


def test_stage_state_cannot_set_end_time_without_submit_time():
    """Test StageState cannot set end_time without submit_time"""
    state = StageState()
    with pytest.raises(ValueError, match="submit_time"):
        state.end_time = 1_000_000.0


def test_stage_state_default_construction():
    """Test that a default StageState is constructed correctly"""
    stage_state = StageState()
    assert stage_state.status is StageStatus.PENDING
    assert stage_state.attempts == 0
    assert stage_state.job_id is None


def test_stage_state_negative_attempts_raises():
    """Test that a StageState ininitialized with negative attempts fails"""
    with pytest.raises(ValueError, match="attempts"):
        StageState(attempts=-1)


def test_stage_state_end_time_without_submit_time_raises():
    """Test that a StageState initialized with an end time but no submit time fails"""
    with pytest.raises(ValueError, match="submit_time"):
        StageState(end_time=1_000_000.0)


def test_stage_state_end_time_before_submit_time_raises():
    """Test that a StageState initialized with end time < submit time fails"""
    with pytest.raises(ValueError, match="cannot precede"):
        StageState(submit_time=1_000_000.0, end_time=999_999.0)


def test_stage_state_equal_submit_and_end_time_is_valid():
    """Test that a StageStat initialied with submit time == end time is valid.
    This is a degenerate state but technically valid.
    """
    stage_state = StageState(submit_time=1_000_000.0, end_time=1_000_000.0)
    assert stage_state.end_time == stage_state.submit_time


def test_stage_state_to_dict_all_fields_present(failed_state):
    """Test that a StageState dict is creating correctly"""
    stage_dict = failed_state.to_dict()
    assert isinstance(stage_dict["status"], str)
    assert stage_dict["status"] == "failed"
    assert stage_dict["job_id"] == "12345.pbs"
    assert stage_dict["case_root"] == "/scratch/cases/spinup_ad"
    assert stage_dict["attempts"] == 1
    assert stage_dict["submit_time"] == 1000000.0
    assert stage_dict["end_time"] == 3000000.0


def test_stage_state_from_dict_roundtrip(submitted_state):
    """Test that a StageState can be "round tripped" to a dict and back"""
    assert StageState.from_dict(submitted_state.to_dict()) == submitted_state


def test_stage_state_from_dict_defaults_optional_fields():
    """Test that a StageState.from_dict correctly instantiates optional fields"""
    stage_state = StageState.from_dict({"status": "pending"})
    assert stage_state.job_id is None
    assert stage_state.attempts == 0


def test_stage_state_from_dict_missing_status_raises():
    """Test that StageState.from_dict called with an empty dict raises for a missing status"""
    with pytest.raises(ValueError, match="Invalid StageStatus"):
        StageState.from_dict({})


def test_stage_state_from_dict_invalid_status_raises():
    """Test that StageState.from_dict called with an invalid StageStatus fails"""
    with pytest.raises(ValueError, match="Invalid StageStatus"):
        StageState.from_dict({"status": "bogus"})


def test_stage_state_from_dict_does_not_mutate_input():
    """Test that StageState.from_dict does not mutate the original input"""
    original = {"status": "pending", "attempts": 2}
    copy = dict(original)
    StageState.from_dict(original)
    assert original == copy


def test_stage_state_equality(submitted_state):
    """Test that two identical StageStates are equal"""
    other = StageState.from_dict(submitted_state.to_dict())
    assert submitted_state == other


@pytest.mark.parametrize(
    "field,value",
    [
        ("_status", StageStatus.DONE),
        ("job_id", "99999.pbs"),  # no underscore
        ("case_root", "/scratch/cases/other"),  # no underscore
        ("_submit_time", 2_000_000.0),
        ("_end_time", 2_003_600.0),
        ("_attempts", 5),
    ],
)
def test_stage_state_inequality_on_each_field(submitted_state, field, value):
    """Test that changing any individual field makes StageStates unequal"""
    other = StageState.from_dict(submitted_state.to_dict())
    object.__setattr__(other, field, value)
    assert submitted_state != other


def test_runtime_keys_match_stage_state_init():
    """Ensure _RUNTIME_KEYS stays in sync with StageState.__init__"""
    actual = frozenset(
        p for p in inspect.signature(StageState.__init__).parameters if p != "self"
    )
    assert _RUNTIME_KEYS == actual, (
        f"_RUNTIME_KEYS is out of sync with StageState.__init__. "
        f"Missing: {actual - _RUNTIME_KEYS}, Extra: {_RUNTIME_KEYS - actual}"
    )


# ---------------------------------------------------------------------------
# StageConfig
# ---------------------------------------------------------------------------


def test_stage_config_valid_minimal(minimal_stage_config):
    """Test that StageConfig can be constructed with a minimal dict"""
    assert minimal_stage_config.name == "spinup_ad"
    assert minimal_stage_config.kind is StageKind.CUSTOM


def test_stage_config_empty_name_raises(minimal_stage_config_dict):
    """Test that StageConfig with a dict with an empty name raises a ValueError"""
    config = {**minimal_stage_config_dict, "name": ""}
    with pytest.raises(ValueError, match="name"):
        StageConfig.from_dict(config)


def test_stage_config_empty_script_raises(minimal_stage_config_dict):
    """Test that StageConfig initiated with a dict with an empty script raises a ValueError"""
    config = {**minimal_stage_config_dict, "script": ""}
    with pytest.raises(ValueError, match="script"):
        StageConfig.from_dict(config)


def test_stage_config_bad_script_raises_on_validate(minimal_stage_config_dict):
    """Test that StageConfig initiated with a dict with an nonexistant script raises a ValueError"""
    config = {**minimal_stage_config_dict, "script": Path("doesnt_exist.sh")}
    stage = StageConfig.from_dict(config)
    with pytest.raises(ValueError, match="script"):
        stage.validate()


def test_stage_config_converts_string_to_path(minimal_stage_config_dict):
    """Test that a string path is automatically converted to a Path object."""
    config = {
        **minimal_stage_config_dict,
        "script": str(minimal_stage_config_dict["script"]),
    }
    stage_config = StageConfig.from_dict(config)
    assert isinstance(stage_config.script, Path)
    assert stage_config.script.exists()


def test_stage_config_empty_queue_raises(minimal_stage_config_dict):
    """Test that StageConfig initiated with an empty queue raises a ValueError"""
    config = {**minimal_stage_config_dict, "queue": ""}
    with pytest.raises(ValueError, match="queue"):
        StageConfig.from_dict(config)


@pytest.mark.parametrize(
    "bad_walltime",
    [
        "06-00-00",  # wrong separator
        "06:99:00",  # minutes out of range
        "06:00:99",  # seconds out of range
        "1:2:3:4:5",  # too many components
        "00:00:00",  # zero walltime
        "0:0:0",  # zero walltime, no padding
        "0",  # zero walltime, single component
        "",  # empty
    ],
)
def test_stage_config_invalid_walltime_raises(minimal_stage_config_dict, bad_walltime):
    """Test that StageConfig initialized with a bad walltime raises a ValueError"""
    config = {**minimal_stage_config_dict, "walltime": bad_walltime}
    with pytest.raises(ValueError, match="walltime"):
        StageConfig.from_dict(config)


@pytest.mark.parametrize(
    "good_walltime",
    [
        "06:00:00",
        "00:30:00",
        "120:00:00",
    ],
)
def test_stage_config_valid_walltime(minimal_stage_config_dict, good_walltime):
    """Test that StageConfig initialized with a good walltime values works"""
    config = {**minimal_stage_config_dict, "walltime": good_walltime}
    stage_config = StageConfig.from_dict(config)
    assert stage_config.walltime == good_walltime


@pytest.mark.parametrize("bad_memory", ["1", "GB", "1 GB", "16gb x", ""])
def test_stage_config_invalid_memory_raises(minimal_stage_config_dict, bad_memory):
    """Test that StageConfig initialized with bad memory values raises a ValueError"""
    config = {**minimal_stage_config_dict, "memory": bad_memory}
    with pytest.raises(ValueError, match="memory"):
        StageConfig.from_dict(config)


@pytest.mark.parametrize("good_memory", ["1B", "512MB", "16GB", "1TB", "1.5GB"])
def test_stage_config_valid_memory(minimal_stage_config_dict, good_memory):
    """Test that StageConfig initialized with a good memory values works"""
    config = {**minimal_stage_config_dict, "memory": good_memory}
    stage_config = StageConfig.from_dict(config)
    assert stage_config.memory == good_memory


def test_stage_config_ncpus_zero_raises(minimal_stage_config_dict):
    """Test that StageConfig initialized with 0 ncpus raises a ValueError"""
    config = {**minimal_stage_config_dict, "ncpus": 0}
    with pytest.raises(ValueError, match="ncpus"):
        StageConfig.from_dict(config)


def test_stage_config_select_zero_raises(minimal_stage_config_dict):
    """Test that StageConfig initialized with select: 0 raises a ValueError"""
    config = {**minimal_stage_config_dict, "select": 0}
    with pytest.raises(ValueError, match="select"):
        StageConfig.from_dict(config)


def test_stage_config_invalid_kind_raises(minimal_stage_config_dict):
    """Test that StageConfig initialized with a bad StageKind raises a ValueError"""
    config = {**minimal_stage_config_dict, "kind": "nonsense"}
    with pytest.raises(ValueError, match="Invalid StageKind"):
        StageConfig.from_dict(config)


def test_stage_config_is_frozen(minimal_stage_config):
    """Test that StageConfig is actually immutable"""
    with pytest.raises(Exception):
        minimal_stage_config.name = "mutated"


def test_stage_config_extra_pbs_stored_as_tuple(full_stage_config):
    """Test that StageConfig's extra_pbs attribute is stored as a tuple"""
    assert isinstance(full_stage_config.extra_pbs, tuple)


def test_stage_config_to_dict_kind_is_string(full_stage_config):
    """Test that StageConfig's to_dict correctly sets the kind as a string"""
    assert full_stage_config.to_dict()["kind"] == "ad"


def test_stage_config_to_dict_extra_pbs_is_list(full_stage_config):
    """Test that StageConfig's to_dict extra_bs is set as a list"""
    assert isinstance(full_stage_config.to_dict()["extra_pbs"], list)


def test_stage_config_roundtrip_minimal(minimal_stage_config):
    """Test that StageConfig can be "round tripped" to a dict and back with a minimal config"""
    assert StageConfig.from_dict(minimal_stage_config.to_dict()) == minimal_stage_config


def test_stage_config_roundtrip_full(full_stage_config):
    """Test that StageConfig can be "round tripped" to a dict and back with a full config"""
    assert StageConfig.from_dict(full_stage_config.to_dict()) == full_stage_config


def test_stage_config_from_dict_defaults_kind_to_custom(minimal_stage_config_dict):
    """Test that StageConfig initiated without a kind defaults to CUSTOM"""
    # kind absent from dict should default to "custom"
    stage_config = StageConfig.from_dict(minimal_stage_config_dict)
    assert stage_config.kind is StageKind.CUSTOM


def test_stage_config_from_dict_defaults_memory_to_10gb(minimal_stage_config_dict):
    """Test that StageConfig initiated without memory defaults to 10GB"""
    stage_config = StageConfig.from_dict(minimal_stage_config_dict)
    assert stage_config.memory == "10GB"


def test_stage_config_from_dict_defaults_no_cime_to_false(minimal_stage_config_dict):
    """Test that StageConfig initiated without no_cime defaults to False"""
    stage_config = StageConfig.from_dict(minimal_stage_config_dict)
    assert stage_config.no_cime is False


def test_stage_config_from_dict_no_cime_read(no_cime_stage_config_dict):
    """Test that StageConfig gets no_cime correctly"""
    stage_config = StageConfig.from_dict(no_cime_stage_config_dict)
    assert stage_config.no_cime is True


def test_stage_config_from_dict_does_not_mutate_input(full_stage_config_dict):
    """Test that initializing StageConfig doesn't mutate the input"""
    copy = dict(full_stage_config_dict)
    StageConfig.from_dict(full_stage_config_dict)
    assert full_stage_config_dict == copy


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


def test_stage_equality(minimal_stage_config):
    """Test Stage__eq__ with equal stages"""
    s1 = Stage(config=minimal_stage_config)
    s2 = Stage(config=minimal_stage_config)
    assert s1 == s2


def test_stage_inequality_on_state(minimal_stage_config):
    """Test Stage__eq__ with inequalities"""
    s1 = Stage(config=minimal_stage_config)
    s2 = Stage(config=minimal_stage_config)
    s2.state.increment_attempts()
    assert s1 != s2


def test_stage_default_status_is_pending(minimal_stage_config):
    """Test that initializing Stage without a status sets to PENDING"""
    stage = Stage(config=minimal_stage_config)
    assert stage.state.status is StageStatus.PENDING


def test_stage_status_reset(full_stage):
    """Assert that we can reset the status"""
    full_stage.state = StageState()
    assert full_stage.state.status is StageStatus.PENDING
    assert full_stage.state.attempts == 0


def test_stage_to_dict_is_flat(full_stage):
    """Test that the Stage.to_dict produces a flat dict"""
    stage_dict = full_stage.to_dict()
    # want config and state keys all at the top level with no nesting
    assert "name" in stage_dict
    assert "status" in stage_dict
    assert "config" not in stage_dict
    assert "attempts" in stage_dict


def test_stage_roundtrip_with_runtime_state(full_stage):
    """Test that Stage can be 'roundtripped' to a dict and back with a full config"""
    assert Stage.from_dict(full_stage.to_dict()) == full_stage


def test_stage_roundtrip_default_state(minimal_stage_config):
    """Test that Stage can be 'roundtripped' to a dict and back with a minimal config"""
    stage = Stage(config=minimal_stage_config)
    assert Stage.from_dict(stage.to_dict()) == stage


def test_stage_from_dict_missing_status_defaults_to_pending(minimal_stage_config_dict):
    """Test that if runtime keys are absent entirely, state defaults to PENDING."""
    stage = Stage.from_dict(minimal_stage_config_dict)
    assert stage.state.status is StageStatus.PENDING


def test_stage_from_dict_does_not_mutate_input(full_stage):
    """Test that the Stage.from_dict() doesn't mutate the input dict"""
    stage_dict = full_stage.to_dict()
    copy = dict(stage_dict)
    Stage.from_dict(stage_dict)
    assert stage_dict == copy


def test_stage_config_is_frozen_through_stage(full_stage):
    """Test that StageConfig is immutable when owned by Stage"""
    with pytest.raises(Exception):
        full_stage.config.name = "mutated"


@pytest.mark.parametrize(
    "partial_state",
    [
        {"status": "submitted"},
        {"status": "submitted", "job_id": "12345.pbs"},
        {"status": "submitted", "job_id": "12345.pbs", "attempts": 2},
        {"status": "submitted", "submit_time": 1_000_000.0},
    ],
)
def test_stage_from_dict_partial_state(minimal_stage_config_dict, partial_state):
    """Test that Stage.from_dict correctly handles partial runtime state,
    as might occur when recovering from a checkpoint written mid-run.
    """
    stage_dict = {**minimal_stage_config_dict, **partial_state}
    stage = Stage.from_dict(stage_dict)

    assert stage.state.status == StageStatus.from_str(partial_state["status"])
    assert stage.state.job_id == partial_state.get("job_id")
    assert stage.state.attempts == partial_state.get("attempts", 0)
    assert stage.state.submit_time == partial_state.get("submit_time")
    assert stage.state.end_time is None
