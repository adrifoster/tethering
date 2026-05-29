"""ModelRun class - manages full lifecycle of a multi-stage run"""

from __future__ import annotations

import os
import subprocess
import time
import json
from pathlib import Path
import re

import yaml

from .stages import Stage, StageStatus

# templates dir
_TEMPLATES = Path(__file__).parents[1] / "templates"

# state file name
_STATE_FILE = "run_state.json"

# characters that are safe in a run_id (used as a directory component).
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

# keys that must be present in a config dict.
_REQUIRED_CONFIG_KEYS = frozenset({"root", "stages"})


class ModelRun:
    """
    Manages the full lifecycle of a multi-stage CESM run.

    Use ModelRun.create() to initialise a new run on disk, or
    ModelRun.load() to resume an existing one.

    Attributes
    ===========
    root: working directory; all CIME cases live under here
    run_id: short identifier, e.g. "member_0042" or "my_spinup"
    stages: ordered tuple of Stage instances
    user: username for the machine - used for PBS job submission. can use os.environ variable
    project: PBS project code to use for job submission. can use os.environ variable
    """

    def __init__(
        self,
        root: Path | str,
        run_id: str,
        stages: tuple[Stage, ...] | list[Stage],
        user: str,
        project: str,
    ):
        self.root = Path(root)
        self.run_id = run_id
        self.stages: tuple[Stage, ...] = tuple(stages)
        self.user = user if user else os.getenv("USER")
        self.project = project if project else os.getenv("PROJECT")
        self._validate()

    def _validate(self):
        if not self.run_id:
            raise ValueError("run_id must not be empty")
        if not _RUN_ID_RE.match(self.run_id):
            raise ValueError(
                f"run_id {self.run_id!r} contains invalid characters. "
                "Only letters, digits, hyphens, and underscores are allowed."
            )
        if not self.user:
            raise ValueError("user must not be empty.")
        if not self.project:
            raise ValueError("project must not be empty.")
        if not self.stages:
            raise ValueError("stages must not be empty")

    @classmethod
    def create(
        cls,
        config: Path | str | dict,
    ) -> ModelRun:
        """Initialise a brand-new run from a YAML file or config dict.

        Creates root on disk and writes the initial state file.
        Call this once; use load for all subsequent access.

        Args:
            config: path to a YAML file, or a dict with the same schema

        Returns:
            ModelRun: ModelRun instance
        Raises:
            ValueError: if required config keys are missing or invalid
            FileExistsError: if a state file already exists at the target root,
            indicating that the run has already been initialized
        """
        cfg = _load_config(config)
        _validate_config(cfg)

        root = Path(cfg["root"])
        state_path = root / _STATE_FILE
        if state_path.exists():
            raise FileExistsError(
                f"A state file already exists at {state_path}. "
                "Use ModelRun.load() to resume an existing run."
            )

        stages = [Stage.from_dict(stage) for stage in cfg["stages"]]
        run = cls(
            root=root,
            run_id=cfg.get("run_id", "run"),
            stages=stages,
            user=cfg["user"],
            project=cfg["project"],
        )
        run.root.mkdir(parents=True, exist_ok=True)
        run.save()
        return run

    @classmethod
    def load(cls, root: Path | str) -> ModelRun:
        """Load an existing run from its state file.

        Args:
            root (Path | str): Path to root

        Returns:
            ModelRun: ModelRun instance
        Raises:
            FileNotFoundError: if no state file exists at root
        """
        root = Path(root)
        state_path = root / _STATE_FILE
        if not state_path.exists():
            raise FileNotFoundError(
                f"No state file found at {state_path}. "
                "Has this run been initialised with ModelRun.create()?"
            )

        state = json.loads(state_path.read_text(encoding="utf-8"))

        return cls(
            root=root,
            run_id=state["run_id"],
            user=state["user"],
            stages=[Stage.from_dict(stage) for stage in state["stages"]],
            project=state["project"],
        )

    def save(self):
        """Atomically write current state to ``<root>/run_state.json``.

        Uses a write-to-temp-then-rename pattern so the state file is
        never left in a partially written state if the process is killed.
        """
        state = {
            "run_id": self.run_id,
            "user": self.user,
            "project": self.project,
            "stages": [stage.to_dict() for stage in self.stages],
        }
        tmp = self.root / f"{_STATE_FILE}.tmp"
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.rename(self.root / _STATE_FILE)

    @property
    def current_stage(self) -> Stage | None:
        """Get the first non-DONE stage

        Returns:
            Stage | None: Stage, or None if all complete
        """
        for stage in self.stages:
            if stage.status.status != StageStatus.DONE:
                return stage
        return None

    def _stage(self, name: str) -> Stage:
        """Get the Stage given an input name

        Args:
            name (str): stage.config.name

        Returns:
            Stage: stage
        """
        names = [stage.config.name for stage in self.stages]
        try:
            idx = names.index(name)
        except ValueError as exc:
            raise ValueError(
                f"No stage named {name!r}. "
                f"Known stages: {[stage.config.name for stage in self.stages]}"
            ) from exc
        return self.stages[idx]

    def _next_stage(self, after: str) -> Stage | None:
        """Get the next stage given an input name

        Args:
            after (str): stage before the stage we want

        Raises:
            ValueError: Can't find supplied stage

        Returns:
            Stage | None: next Stage, or None if no more stages
        """
        names = [stage.config.name for stage in self.stages]
        try:
            idx = names.index(after)
        except ValueError as exc:
            raise ValueError(
                f"No stage named {after!r}. " f"Known stages: {names}"
            ) from exc
        return self.stages[idx + 1] if idx + 1 < len(self.stages) else None
    
    def _previous_stage(self, before: str) -> Stage | None:
        """Get the previous stage given an input name

        Args:
            after (str): stage before the stage we want

        Raises:
            ValueError: Can't find supplied stage

        Returns:
            Stage | None: previous Stage, or None if first stage
        """
        names = [stage.config.name for stage in self.stages]
        try:
            idx = names.index(before)
        except ValueError as exc:
            raise ValueError(
                f"No stage named {before!r}. " f"Known stages: {names}"
            ) from exc
        return self.stages[idx - 1] if idx > 0 else None

    def _case_root_for(self, stage: Stage) -> Path:
        """Generate the case root name for this stage

        Args:
            stage (Stage): input Stage

        Returns:
            Path: path to stage's case root
        """
        return self.root / stage.config.name

    def format_status(self):
        """Format the status of the run that can be printed to the screen"""
        icons = {
            StageStatus.PENDING: "·",
            StageStatus.SUBMITTED: "...",
            StageStatus.DONE: "✓",
            StageStatus.FAILED: "✗",
        }
        lines = [f"Run: {self.run_id} ({self.root})"]
        for stage in self.stages:
            icon = icons.get(stage.status.status, "?")
            job = f" [{stage.status.job_id}]" if stage.status.job_id else ""
            # only show attempts if the stage has been retried at least once
            attempts = (
                f" attempts={stage.status.attempts}"
                if stage.status.attempts > 1
                else ""
            )
            lines.append(
                f" {icon} {stage.config.name:<20}  {stage.status.status.value:<10}{job}{attempts}"
            )
        return "\n".join(lines)

    def submit(self, dry_run: bool = False) -> str:
        """Submit the first pending stage.

        Args:
            dry_run (bool, optional): If True, only print text to screen and don't
            submit anything. Defaults to False.

        Returns:
            str: PBS job ID of the submit script
        """
        first = self.stages[0]
        if first.status.status != StageStatus.PENDING:
            print(
                f"  {self.run_id}: skipping submit (first stage is {first.status.status.value})"
            )
            return first.status.job_id or ""
        return self._submit_stage(first, dry_run=dry_run)

    def fail(self, stage_name: str):
        """Mark a stage as failed (called from the ERR trap).

        Args:
            stage_name (str): stage name
        """
        stage = self._stage(stage_name)
        if stage.status.status not in (StageStatus.SUBMITTED, StageStatus.DONE):
            raise ValueError(
                f"Stage {stage.config.name!r} is {stage.status.status.value} "
                "- can only fail SUBMITTED or DONE stages."
            )
        stage.status.status = StageStatus.FAILED
        stage.status.end_time = time.time()
        self.save()
        print(f"  {self.run_id} / {stage_name}: FAILED")

    def submit_advance(
        self, stage_name: str, cime_job_id: str, dry_run: bool = False
    ) -> str:
        """Write the advance script with the CIME job ID and submit it
        Called from the setup job script after case.submit completes

        Args:
            stage_name (str): name of stage
            cime_job_id (str): CIME job ID
            dry_run (bool, optional): If True, only print text to screen and don't
            submit anything. Defaults to False.

        Returns:
            str: PBS job ID of the advance script
        """
        stage = self._stage(stage_name)
        job_file = self._write_advance_script(stage, cime_job_id)
        job_id = (
            f"DRY_advance_{self.run_id}_{stage_name}"
            if dry_run
            else self._qsub(job_file)
        )
        print(
            f"  {self.run_id} / {stage_name}: advance job submitted {job_id} (afterok:{cime_job_id})"
        )
        return job_id

    def advance(self, completed_stage_name: str, dry_run: bool = False) -> str | None:
        """Advance the pipeline and submit the next stage

        Args:
            completed_stage_name (str): completed stage name
            dry_run (bool, optional): If True, only print text to screen and don't
            submit anything. Defaults to False.

        Returns:
            str | None: PBS job ID of the advance script, or None if all stages complete
        """
        stage = self._stage(completed_stage_name)
        if stage.status.status != StageStatus.SUBMITTED:
            raise ValueError(
                f"Stage {stage.config.name!r} is {stage.status.status.value} "
                "— can only advance SUBMITTED stages."
            )
        stage.status.status = StageStatus.DONE
        stage.status.end_time = time.time()
        self.save()
        print(f"  {self.run_id} / {completed_stage_name}: DONE")

        next_stage = self._next_stage(completed_stage_name)
        if next_stage is None:
            print(f" {self.run_id}: all stages complete!")
            return None
        return self._submit_stage(next_stage, dry_run=dry_run)

    def retry(self, stage_name: str | None, dry_run: bool = False) -> str | None:
        """Reset a failed or stuck stage and resubmit it.

        Args:
            stage_name (str | None): stage name
            dry_run (bool, optional): If True, only print text to screen and don't
            submit anything. Defaults to False.

        Returns:
            str | None: PBS job ID of the advance script, or None if all stages complete
        """
        stage = self._stage(stage_name) if stage_name else self.current_stage
        if stage is None:
            print(f"  {self.run_id}: nothing to retry")
            return None
        if stage.status.status not in (StageStatus.PENDING, StageStatus.FAILED):
            raise ValueError(
                f"Stage {stage.config.name!r} is {stage.status.status.value} "
                "— can only retry PENDING or FAILED stages."
            )
        stage.status.status = StageStatus.PENDING
        self.save()
        return self._submit_stage(stage, dry_run=dry_run)

    def _submit_stage(
        self, stage: Stage, depend_job_id: str | None = None, dry_run: bool = False
    ) -> str:
        if stage.status.status not in (StageStatus.PENDING, StageStatus.FAILED):
            raise ValueError(
                f"Stage {stage.config.name!r} is {stage.status.status.value} "
                "- can only submit PENDING or FAILED stages."
            )
        job_file = self._write_job_script(stage, depend_job_id)
        job_id = (
            f"DRY_{self.run_id}_{stage.config.name}"
            if dry_run
            else self._qsub(job_file)
        )
        stage.status.job_id = job_id
        stage.status.status = StageStatus.SUBMITTED
        stage.status.submit_time = time.time()
        stage.status.increment_attempts()
        self.save()
        print(f"{self.run_id} / {stage.config.name}: submitted {job_id}")
        return job_id

    def _write_job_script(self, stage: Stage, depend_job_id: str | None = None) -> Path:
        """Write the setup job script for one stage.

        The script:
        1. Runs the user's setup script (creates/configures/builds the CIME case)
        2. Submits the CIME case, captures its final PBS job ID
        3. Calls clm-run --submit-advance, which writes and submits the
             advance script in Python with the CIME job ID already baked in

        Args:
            stage (Stage): input Stage
            depend_job_id (str | None, optional): Depend Job ID. Defaults to None.

        Returns:
            Path: path to job script
        """
        case_root = self._case_root_for(stage)
        previous_stage = self._previous_stage(stage.config.name)
        previous_stage_name = previous_stage.config.name if previous_stage else ""
        
        job_name = f"{self.run_id}_{stage.config.name}"
        job_file = self.root / f"{job_name}.pbs"
        depend_line = (
            f"#PBS -W depend=afterok:{depend_job_id}\n" if depend_job_id else ""
        )
        extra = "\n".join(f"#PBS {d}" for d in stage.config.extra_pbs)

        log_file = self.root / f"{job_name}.log"

        template = _load_template(_TEMPLATES / "submit_script_template.txt")
        template = template.format(
            job_name=job_name,
            queue=stage.config.queue,
            select=stage.config.select,
            ncpus=stage.config.ncpus,
            memory=stage.config.memory,
            walltime=stage.config.walltime,
            project=self.project,
            log_file=log_file,
            user=self.user,
            depend_line=depend_line,
            extra=extra,
            root=self.root,
            name=stage.config.name,
            previous_case=previous_stage_name,
            run_id=self.run_id,
            script=stage.config.script,
            case_root=case_root,
        )
        job_file.write_text(template, encoding="utf-8")
        return job_file

    def _write_advance_script(self, stage: Stage, cime_job_id: str) -> Path:
        """Write the advance job script with the real CIME job ID already in
        the afterok dependency line

        Args:
            stage (Stage): Stage to advance
            cime_job_id (str): CIME job ID

        Returns:
            Path: path to script
        """
        job_name = f"{self.run_id}_{stage.config.name}_advance"
        job_file = self.root / f"{job_name}.pbs"

        template = _load_template(_TEMPLATES / "advance_script_template.txt")
        template = template.format(
            job_name=job_name,
            queue=stage.config.queue,
            project=self.project,
            user=self.user,
            cime_job_id=cime_job_id,
            root=self.root,
            stage_name=stage.config.name,
        )
        job_file.write_text(template, encoding="utf-8")
        return job_file

    def _qsub(self, job_file: Path) -> str:
        """Submit the PBS input job_file

        Args:
            job_file (Path): input job file

        Returns:
            str: job_id printed from submission
        """
        result = subprocess.run(
            ["qsub", str(job_file)],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()


def _validate_config(config: dict) -> None:
    """Raise a descriptive ValueError for any missing or invalid config keys.

    Args:
        config: raw config dictionary (from YAML or passed directly)

    Raises:
        ValueError: if any required key is absent or malformed
    """
    missing = _REQUIRED_CONFIG_KEYS - config.keys()
    if missing:
        raise ValueError(
            f"Config is missing required key(s): {sorted(missing)}. "
            f"Required keys are: {sorted(_REQUIRED_CONFIG_KEYS)}"
        )
    if not isinstance(config["stages"], list):
        raise ValueError(
            f"Config key 'stages' must be a list, got {type(config['stages']).__name__!r}."
        )
    if len(config["stages"]) == 0:
        raise ValueError("Config key 'stages' must not be empty.")


def _load_config(config: Path | str | dict) -> dict:
    """Normalise *config* to a plain dict.

    Args:
        config: a dict, or a path to a YAML file.

    Returns:
        A plain dict with the config contents.

    Raises:
        TypeError: if *config* is not a dict, str, or Path.
    """
    if isinstance(config, dict):
        return config
    if isinstance(config, (str, Path)):
        with open(config, encoding="utf-8") as f:
            raw = os.path.expandvars(f.read())
            return yaml.safe_load(raw)
    raise TypeError(
        f"config must be a dict, str, or Path, got {type(config).__name__!r}."
    )


def _load_template(template_path: Path) -> str:
    """Load a template file

    Args:
        template_path (str): path to template

    Raises:
        FileNotFoundError: Template file not found

    Returns:
        Path: template path
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Template '{template_path}' not found.")
    return template_path.read_text(encoding="utf-8")
