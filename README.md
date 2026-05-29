# tethering

A Python library for managing multi-stage CLM runs on PBS clusters.

CLM cases are typically submitted as independent PBS jobs. Tethering chains them together into a pipeline. Each stage automatically submits the next when it completes, using PBS `afterok` dependencies to ensure correct ordering.

> **Status**: Early development. The API may change.

----

## How it works

Each "stage" will consist of three PBS jobs:

1. **Setup job**: runs the user's setup script, submits the CESM case, and then uses `clm-run` to run `submit-advance`, grabbing the PBS job ID from the case.
2. **CIME job**: actual model run, submitted with `./case.submit --resubmit-immediate`
3. **Advance job**: lightweight bookkeepting job that runs `afterok` the CIME job; this just marks the stage complete and then submits the next stage's setup script.

Thus, only the first stage needs to be manually submitted. The rest of the pipeline will run automatically.

----

## Installation

### Requirements

- Python >= 3.12
- A PBS cluster with `qsub` available
- CESM/CLM set up on the cluster

### With conda (recommended)

```bash
git clone https://github.com/<username>/tethering.git
cd tethering
conda env create -f environment.yml
conda activate tethering
```

## Quick start

### 1. Write a config YAML

```yaml
# run.yaml
root: /work/user/my_spinup  # working directory for the entire run
run_id: my_spinup           # short identifier (letters, digits, hyphens, underscores)
project: PXXXXXXX           # PBS project code
user: auser                 # PBS username

stages:
  - name: spinup_ad
    script: /path/to/setup_ad.sh  # path to your setup script for this stage
    walltime: "01:00:00"          # walltime for JUST the setup script
    queue: develop
    ncpus: 1                      # ncpus for setup only (not the CIME run)
    select: 1                     # select for setup only (not the CIME run)
    memory: 10GB                  # memory for setup only (not the CIME run)
    kind: ad                      # kind (see below)

  - name: spinup_sasu
    script: /path/to/setup_sasu.sh
    walltime: "1:00:00"
    queue: develop
    ncpus: 1
    select: 1
    memory: 10GB
    kind: sasu
```

### 2. Initialise the run

```bash
clm-run --create --config run.yaml
```
This creates the run directory and writes the initial state file.

### 3. Submit the pipeline

```bash
clm-run --root /scratch/user/my_spinup --submit
```

This submits the first stage. The rest of the pipeline runs automatically via PBS dependencies.

### 4. Check status

```bash
clm-run --root /scratch/user/my_spinup --print-status
```


Output:
```
Run: my_spinup (/work/user/my_spinup)
  ✓ spinup_ad             done
  ... spinup_sasu         submitted   [98765.pbs]
```

---

## CLI reference

```
clm-run --create --config run.yaml
  Initialise a new run from a YAML config file.

clm-run --root <path> --print-status
  Print the current status of all stages.

clm-run --root <path> --submit [--dry-run]
  Submit the first pending stage.

clm-run --root <path> --retry [--stage <name>] [--dry-run]
  Reset and resubmit a failed stage. If --stage is omitted,
  retries the current (first non-complete) stage.

clm-run --root <path> --submit-advance --stage <name> --cime-job-id <id>
  Submit the advance job for a stage. Called automatically
  from inside the setup job — not typically run manually.

clm-run --root <path> --advance --stage <name>
  Mark a stage complete and submit the next stage. Called
  automatically from inside the advance job.

clm-run --root <path> --fail --stage <name>
  Mark a stage as failed. Called automatically from the
  PBS ERR trap. Or can be done manually.
```

Add `--dry-run` to any submission command to generate job scripts without calling `qsub`.

---

## Setup scripts

Each stage requires a setup script that creates, configures, and builds the CLM case. The script is called as:

```bash
bash <script> <case_root> <optional_previous_case_root>
```

The script should not call `./case.submit` — tethering handles that.

---

## Stage kinds

These don't actually do anything right nowbut may be used in the future.

| Kind | Description |
|------|-------------|
| `ad` | Accelerated decomposition spinup |
| `sasu` | Satellite phenology spinup |
| `post-sasu` | Post-SASU stage |
| `historical` | Historical run |
| `custom` | Any other stage type |

---

## Contributing

This project is in early development. If you use CLM on PBS and want to contribute, please open an issue first to discuss what you'd like to change.
