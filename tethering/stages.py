"""
Module for holding core classes for tethering:
StageStatus and StageKind Enums, plus StageState, StageConfig, and Stage
"""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

_WALLTIME_RE = re.compile(r"^\d{2,3}:\d{2}:\d{2}$")
_MEMORY_RE = re.compile(r"^\d+(\.\d+)?(B|KB|MB|GB|TB)$", re.IGNORECASE)
_RUNTIME_KEYS = frozenset(
    {"status", "job_id", "case_root", "submit_time", "end_time", "attempts"}
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StageStatus(Enum):
    """Stage Status Enum"""

    PENDING = "pending"
    SUBMITTED = "submitted"
    DONE = "done"
    FAILED = "failed"

    def to_str(self) -> str:
        """Return value string

        Returns:
            str: output string
        """
        return self.value

    @classmethod
    def from_str(cls, raw: str) -> StageStatus:
        """Instantiate the class from an input raw string

        Args:
            raw (str): input string

        Raises:
            ValueError: invalid status supplied

        Returns:
            StageStatus: StageStatus instance
        """
        try:
            return cls(raw.lower().strip())
        except ValueError as e:
            raise ValueError(
                f"Invalid StageStatus {raw!r}. "
                f"Valid values: {[e.value for e in cls]}"
            ) from e


class StageKind(Enum):
    """Stage Kind Enum"""

    AD = "ad"
    SASU = "sasu"
    POST_SASU = "post-sasu"
    HISTORICAL = "historical"
    CUSTOM = "custom"

    def to_str(self) -> str:
        """Return value string

        Returns:
            str: output string
        """
        return self.value

    @classmethod
    def from_str(cls, raw: str) -> StageKind:
        """Instantiate the class from an input raw string

        Args:
            raw (str): input string

        Raises:
            ValueError: invalid kind supplied

        Returns:
            StageKind: StageKind instance
        """
        try:
            return cls(raw.lower().strip())
        except ValueError as e:
            raise ValueError(
                f"Invalid StageKind {raw!r}. " f"Valid values: {[e.value for e in cls]}"
            ) from e


# ---------------------------------------------------------------------------
# StageStage (mutable runtime state)
# ---------------------------------------------------------------------------


class StageState:
    """Mutable runtime state for one stage. Owned by `Stage`.

    All mutation goes through methods or properties that enforce invariants:
    - submit_time cannot be set after end_time is set
    - end_time requires submit_time to be set first
    - end_time cannot precede submit_time
    - attempts is incremented via increment_attempts(), never set directly

    Attributes
    -----------
    status: current status of the stage
    job_id: PBS job ID assigned after submission
    case_root: absolute path to the CESM case directory
    _submit_time: unix timestamp of the most recent submission
    _end_time: unix timestamp of completion or failure
    _attempts: how many times this stage has been submitted (must be >=0)
    """

    def __init__(
        self,
        status: StageStatus = StageStatus.PENDING,
        job_id: str | None = None,
        case_root: str | None = None,
        submit_time: float | None = None,
        end_time: float | None = None,
        attempts: int = 0,
    ):
        self.status = status
        self.job_id = job_id
        self.case_root = case_root
        self._submit_time = submit_time
        self._end_time = end_time
        self._attempts = attempts
        self._validate()

    def _validate(self):
        if self._attempts < 0:
            raise ValueError(f"attempts must be >=0, got {self._attempts!r}")
        if self._end_time is not None:
            if self._submit_time is None:
                raise ValueError(
                    "end_time is set but submit_time is None; "
                    "a stage cannot finish before it starts."
                )
            if self._end_time < self._submit_time:
                raise ValueError(
                    f"end_time ({self._end_time}) cannot precede "
                    f"submit_time ({self._submit_time})."
                )

    @property
    def submit_time(self) -> float | None:
        """Get the submit time

        Returns:
            float | None: submit time
        """
        return self._submit_time

    @submit_time.setter
    def submit_time(self, value: float | None):
        """Set the submit time

        Args:
            value (float): submit_time to set
        """
        if self._end_time is not None:
            raise ValueError(
                f"end_time ({self._end_time}) is already set; "
                "reset the end_time before setting submit_time."
            )
        self._submit_time = value

    @property
    def end_time(self) -> float | None:
        """Get the end time

        Returns:
            float | None: end time
        """
        return self._end_time

    @end_time.setter
    def end_time(self, value: float | None):
        """Set the end time

        Args:
            value (float): end_time to set
        """
        if self._submit_time is None:
            raise ValueError(
                "cannot set end_time when submit_time is None "
                "a stage cannot finish before it starts."
            )
        if value and value < self._submit_time:
            raise ValueError(
                f"end_time ({value}) cannot precede "
                f"submit_time ({self._submit_time})."
            )
        self._end_time = value

    @property
    def attempts(self) -> int:
        """Get the number of attempts

        Returns:
            int: attempts
        """
        return self._attempts

    def increment_attempts(self):
        """Increment the number of attempts"""
        self._attempts += 1

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StageState):
            return NotImplemented
        return (
            self.status == other.status
            and self.job_id == other.job_id
            and self.case_root == other.case_root
            and self._submit_time == other._submit_time
            and self._end_time == other._end_time
            and self._attempts == other._attempts
        )

    def __repr__(self) -> str:
        return (
            f"StageState(status={self.status!r}, job_id={self.job_id!r}, "
            f"case_root={self.case_root!r}, submit_time={self._submit_time!r}, "
            f"end_time={self._end_time!r}, attempts={self._attempts!r})"
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary

        Note that the ``status`` value is stored as its string representation so that
        the dict is directly JSON-serializable without a custom encoder.

        Returns:
            dict: output dictionary
        """
        return {
            "status": self.status.to_str(),
            "job_id": self.job_id,
            "case_root": self.case_root,
            "submit_time": self._submit_time,
            "end_time": self._end_time,
            "attempts": self._attempts,
        }

    @classmethod
    def from_dict(cls, input_dict: dict) -> StageState:
        """Construct a StageState from an input dictionary

        Args:
            input_dict (dict): input dictionary, must contain at minimum a `status` key

        Returns:
            StageState: StageState instance
        Raises:
            ValueError: If "status" is absent or not a valid StageStatus value
        """
        input_dict = dict(input_dict)
        return cls(
            status=StageStatus.from_str(input_dict.get("status", "")),
            job_id=input_dict.get("job_id"),
            case_root=input_dict.get("case_root"),
            submit_time=input_dict.get("submit_time"),
            end_time=input_dict.get("end_time"),
            attempts=input_dict.get("attempts", 0),
        )


# ---------------------------------------------------------------------------
# StageConfig (immutable configuration)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageConfig:
    """Dataclass that holds immutable properties of a run.

    Frozen so that config cannot be accidentally mutated after construction.
    All attributes are set at creation and never change.

    Attributes
    -----------
    name: unique identifier, e.g., "spinup_ad"
    script: path to setup script; called as bash <script> <case_root> <run_id>
    walltime: PBS walltime string, e.g., "06:00:00"
    queue: PBS queue name
    kind: stage kind, really just a name right now
    spinup_check: if True, advance() reads runs spinup_stability before proceeding
    ncpus: CPUs per node requested from PBS
    select: number of nodes
    memory: memory requested string, e.g. "1GB"
    extra_pbs: additional raw #PBS directives
    """

    name: str
    script: Path
    queue: str
    walltime: str = "01:00:00"
    kind: StageKind = StageKind.CUSTOM
    spinup_check: bool = False
    ncpus: int = 1
    select: int = 1
    memory: str = "10GB"
    no_cime: bool = False
    extra_pbs: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.name:
            raise ValueError("name must not be empty.")
        if not self.script:
            raise ValueError("script must not be empty.")

        object.__setattr__(self, "script", Path(self.script))

        if not self.script.exists():
            raise ValueError(f"cannot open script {self.script!r}.")

        if not _WALLTIME_RE.match(self.walltime):
            raise ValueError(
                f"walltime {self.walltime!r} does not match expected format "
                "HH:MM:SS (or HHH:MM:SS). Example: '06:00:00"
            )
        if not self.queue:
            raise ValueError("queue must not be empty.")
        if self.ncpus < 1:
            raise ValueError(f"ncpus must be >=1, got {self.ncpus!r}.")
        if self.select < 1:
            raise ValueError(f"select must be >=1, got {self.select!r}.")
        if not _MEMORY_RE.match(self.memory):
            raise ValueError(
                f"memory {self.memory!r} does not match expected format "
                "<number><unit> where unit is one of B, KB, MB, GB, TB. "
                "Example: '16GB'"
            )

    def to_dict(self) -> dict:
        """Serialize configuration fields to a plain dictionary"""
        return {
            "name": self.name,
            "script": self.script,
            "walltime": self.walltime,
            "queue": self.queue,
            "kind": self.kind.to_str(),
            "spinup_check": self.spinup_check,
            "ncpus": self.ncpus,
            "select": self.select,
            "memory": self.memory,
            "no_cime": self.no_cime,
            "extra_pbs": list(self.extra_pbs),
        }

    @classmethod
    def from_dict(cls, input_dict: dict) -> StageConfig:
        """Construct a class StageConfig from an input dictionary

        Args:
            input_dict (dict): Mapping of configuration field names to values

        Returns:
            StageConfig: StageConfig instance
        """
        in_dict = dict(input_dict)
        in_dict["kind"] = StageKind.from_str(in_dict.get("kind", "custom"))
        in_dict["extra_pbs"] = tuple(in_dict.get("extra_pbs", []))
        return cls(**in_dict)


# ---------------------------------------------------------------------------
# Stage  (composes config + runtime state)
# ---------------------------------------------------------------------------


@dataclass
class Stage:
    """Dataclass for one stage of a run. Holds both config (set at creation, never
    changes) and runtime state (updated as the stage progresses).

    Attributes
    -----------
    config: StageConfig attributes
    status: StageState instance; reset with stage.status = StageState()
    """

    config: StageConfig
    status: StageState = field(default_factory=StageState)

    @classmethod
    def from_dict(cls, input_dict: dict) -> Stage:
        """Reconstruct class Stage from a flat dictionary

        Args:
            input_dict (dict): input dictionary

        Returns:
            Stage: Stage instance
        """
        in_dict = dict(input_dict)
        runtime_dict = {k: in_dict.pop(k) for k in _RUNTIME_KEYS if k in in_dict}
        return cls(
            config=StageConfig.from_dict(in_dict),
            status=StageState.from_dict(runtime_dict) if runtime_dict else StageState(),
        )

    def to_dict(self) -> dict:
        """Flatten a class Stage to a single-level dictionary

        Returns:
            dict: output dictionary
        """
        return {**self.config.to_dict(), **self.status.to_dict()}
