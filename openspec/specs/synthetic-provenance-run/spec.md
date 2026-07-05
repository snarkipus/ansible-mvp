## Purpose

Define the local synthetic provenance workflow contract, including controlled source bootstrap, canonical simulation workspace layout, provenance sidecar separation, mock scheduler metadata, clean run execution, and handoff guidance.
## Requirements
### Requirement: Controlled source demo can be bootstrapped
The system SHALL provide a bootstrap command that creates or verifies a sibling `../controlled-source-demo` Git repository for the synthetic workflow.

#### Scenario: Bootstrap creates demo repository
- **WHEN** `make bootstrap-controlled-source` is run in a workspace without `../controlled-source-demo`
- **THEN** the command creates a Git repository containing synthetic scripts, runtime procs, fixtures, an initial commit, and tag `controlled-source-demo-v0.1.0`

#### Scenario: Bootstrap verifies existing demo repository
- **WHEN** `make bootstrap-controlled-source` is run and a compatible clean `../controlled-source-demo` already exists
- **THEN** the command leaves the repository usable for the documented run command

#### Scenario: Bootstrap rejects incompatible demo repository
- **WHEN** `../controlled-source-demo` exists but is not a clean Git repository with expected tracked scripts, fixtures, and tag `controlled-source-demo-v0.1.0`
- **THEN** bootstrap fails with a clear compatibility error instead of overwriting the repository

### Requirement: Run workspace preserves canonical simulation layout
The system SHALL create `runs/{run_id}/sim-run-root/` with `input/`, `lists`, `files`, and `procs/` areas for each run.

#### Scenario: Run workspace is prepared
- **WHEN** a valid run starts with `run_id=demo_001`
- **THEN** the workspace contains `runs/demo_001/sim-run-root/input`, `lists`, `files`, and `procs`

### Requirement: Repeated logical groups are represented by full artifact identity
The system SHALL model repeated `dirA`, `dirB`, and `dirC` groups by full relative path plus simulation area and logical group.

#### Scenario: Inputs are materialized for repeated groups
- **WHEN** synthetic inputs are materialized
- **THEN** `ex1.dat`, `ex2.dat`, and `ex3.dat` exist under each of `sim-run-root/input/dirA`, `dirB`, and `dirC`

#### Scenario: Synthetic raw output is produced under dirC lists
- **WHEN** the synthetic simulation stage completes
- **THEN** the raw output artifact exists at `sim-run-root/lists/dirC/sim-out.dat` and is identifiable by full relative path, `sim_area: lists`, and `logical_group: dirC`

### Requirement: Provenance sidecar is separate from simulation root
The system SHALL write provenance evidence and derived products under `runs/{run_id}/provenance/`, not directly under `sim-run-root/`.

#### Scenario: Provenance directories are created
- **WHEN** a valid run workspace is prepared
- **THEN** `runs/{run_id}/provenance/` contains directories for logs, inventories, scheduler metadata, validations, and products

#### Scenario: Derived products are outside simulation root
- **WHEN** extraction and report stages complete
- **THEN** extracted CSVs and generated reports are under `runs/{run_id}/provenance/products/` and not under `runs/{run_id}/sim-run-root/`

#### Scenario: Expected report products are generated
- **WHEN** report generation completes in a clean synthetic run
- **THEN** `summary.xlsx`, `chart.png`, and `briefing.pptx` exist under `runs/{run_id}/provenance/products/reports/`

#### Scenario: Generated run evidence is not committed to Git
- **WHEN** ordinary run outputs, manifests, logs, scheduler evidence, inventories, validations, extracted products, or report products are generated under `runs/{run_id}/`
- **THEN** they remain generated run evidence and are not committed to the wrapper repository

### Requirement: Source repository stores factory definition
The system SHALL use Git for factory definition artifacts and not for ordinary run evidence.

#### Scenario: Factory definition is versioned
- **WHEN** the wrapper repository is committed
- **THEN** Git tracks source code, Makefile, Ansible playbooks, configuration, specs, tests, docs, lockfiles, and intentionally curated small fixtures or examples

#### Scenario: Archive/freeze is separate from Git commits
- **WHEN** a run is selected for future archive or promotion
- **THEN** the archived evidence is controlled by archive/freeze policy rather than by committing ordinary `runs/{run_id}/` outputs to Git

### Requirement: Archive policy preserves simulation boundary
The system SHALL preserve the boundary between `sim-run-root/` runtime contract and `provenance/` evidence sidecar when defining future archive/freeze behavior.

#### Scenario: Frozen runs preserve consumed inputs and evidence
- **WHEN** a future archive/freeze operation packages a successful run
- **THEN** it preserves the manifest, checksums, validations, logs, inventories, selected products, and exact consumed inputs without moving provenance evidence into `sim-run-root/`

### Requirement: Mock scheduler metadata is captured
The system SHALL emulate the team's minimal LSF submission, wait, and accounting boundary for one monolithic simulation job per run without requiring real LSF commands.

#### Scenario: Mock submission is recorded
- **WHEN** the mock scheduler submission stage runs
- **THEN** scheduler submission evidence is written under `runs/{run_id}/provenance/scheduler/`
- **AND** the evidence records mock LSF mode, a job id, submitted timestamp, payload command, stdout/stderr paths, and initial non-terminal state

#### Scenario: Local async payload is submitted
- **WHEN** `submit_mock_lsf` runs in `local_async` mode for a delayed synthetic payload
- **THEN** it starts a scheduler-owned local wrapper process and returns before the payload reaches terminal `DONE` or `EXIT` state
- **AND** it records process identity, scheduler-owned terminal state paths, and scheduler state evidence under `runs/{run_id}/provenance/scheduler/`

#### Scenario: Wait observes terminal state
- **WHEN** `wait_mock_lsf` runs after a successful local async submission
- **THEN** it observes at least one non-terminal scheduler state such as `PEND` or `RUN` before the payload reaches terminal `DONE` or `EXIT` for a normal delayed run
- **AND** it records started timestamp, finished timestamp, elapsed time, return code, and final scheduler state

#### Scenario: Wrapper records terminal payload status
- **WHEN** the scheduler-owned local wrapper finishes executing the payload
- **THEN** it writes terminal scheduler evidence containing exit code and `DONE` or `EXIT` state under `runs/{run_id}/provenance/scheduler/`
- **AND** `wait_mock_lsf` uses that scheduler-owned terminal evidence rather than relying on inherited child-process handles

#### Scenario: Timeout records failed scheduler evidence
- **WHEN** `wait_mock_lsf` reaches its configured timeout before the scheduler-owned wrapper records terminal `DONE` or `EXIT`
- **THEN** it attempts bounded cleanup of the scheduler-owned process group
- **AND** it records timeout, cleanup, and any orphan or unknown state evidence under `runs/{run_id}/provenance/scheduler/`
- **AND** the job is not treated as terminal `DONE`

#### Scenario: Accounting is collected after terminal state
- **WHEN** `collect_mock_lsf` runs after the job reaches terminal scheduler state
- **THEN** final normalized accounting evidence is written under `runs/{run_id}/provenance/scheduler/`
- **AND** the accounting evidence links to the payload execution evidence

#### Scenario: Real LSF tools are absent
- **WHEN** `bsub`, `bjobs`, `bhist`, or `bacct` are not installed
- **THEN** the synthetic MVP can still complete using mock scheduler mode

### Requirement: Workflow can be run through documented command shape
The system SHALL support the documented Ansible command shape for a clean synthetic run.

#### Scenario: Clean synthetic run succeeds
- **WHEN** the controlled source demo is bootstrapped and the documented `ansible-playbook` command is run with `run_id`, `controlled_source_repo`, and `controlled_source_ref`
- **THEN** the workflow completes successfully and writes expected run outputs, detailed stage evidence, and a concise operator workflow summary

### Requirement: Run workspaces are fresh by default
The system SHALL reject full workflow runs that attempt to reuse an existing `runs/{run_id}` workspace unless reuse is explicitly requested for developer debugging.

#### Scenario: Existing run workspace is rejected by default
- **WHEN** preflight starts for a `run_id` whose `runs/{run_id}` workspace already exists
- **THEN** preflight fails before writing new run evidence
- **AND** the error explains that the run id must be fresh or explicitly reused

#### Scenario: Explicit reuse policy permits focused debugging
- **WHEN** preflight starts for an existing `runs/{run_id}` workspace with run-root policy `reuse`
- **THEN** preflight continues through the normal controlled-source gate checks
- **AND** the operator has explicitly accepted that existing evidence may remain in the workspace

### Requirement: Workflow stages are classified by lifecycle lane
The system SHALL distinguish demo bootstrap, admission, setup, evidence, factory, and finalization lifecycle lanes in stage declarations and operator documentation.

#### Scenario: Stage declaration includes lifecycle metadata
- **WHEN** a configured run stage is declared
- **THEN** the declaration includes a display name, lifecycle class, display order, and operator-visibility value

#### Scenario: Demo bootstrap is outside ordinary run lineage
- **WHEN** `make bootstrap-controlled-source` creates or verifies the synthetic controlled-source repository
- **THEN** documentation describes it as demo bootstrap rather than an ordinary factory stage in the run manifest

#### Scenario: Operator-facing flow is simplified
- **WHEN** a user reads the README or handoff guide
- **THEN** the documentation distinguishes the concise operator workflow from admission/setup plumbing, evidence collection, and finalization support steps

#### Scenario: Make targets remain stable
- **WHEN** lifecycle lanes and display names are documented or added to configuration
- **THEN** existing Make target names remain available for focused debugging

#### Scenario: Pre-run inventory is evidence collection
- **WHEN** the `inventory_pre` stage is declared in configuration and recorded in the manifest
- **THEN** its lifecycle class is `evidence`
- **AND** it remains outside the concise operator-facing factory flow

### Requirement: Handoff guide explains how to use and extend the MVP
The system SHALL include a concise handoff guide for junior engineers using the MVP as a template.

#### Scenario: Engineer follows the guide
- **WHEN** a junior engineer opens `docs/how_to_use_this_mvp.md`
- **THEN** the guide explains prerequisites, setup, bootstrap, run commands, expected outputs, manifest inspection, extension points, and provenance guardrails

#### Scenario: Engineer extends the workflow safely
- **WHEN** the guide describes adding a new stage or controlled script
- **THEN** it instructs the engineer to add the script to a controlled Git repository, declare it in configuration, include it in preflight validation, write outputs to the correct run area, connect it to the manifest, and choose the appropriate lifecycle class

### Requirement: Simulation payload executes through scheduler boundary
The system SHALL execute the synthetic simulation payload through the mock scheduler boundary rather than as the direct operator-facing workflow stage.

#### Scenario: Operator flow shows scheduler boundary
- **WHEN** a clean synthetic run completes
- **THEN** the concise operator-facing flow includes submission, wait, and scheduler evidence collection before extraction
- **AND** direct `run_simulation` payload execution is not presented as the operator-facing top-level simulation stage outside the scheduler boundary

#### Scenario: Payload evidence remains available
- **WHEN** the mock scheduler executes the simulation payload
- **THEN** payload execution evidence such as `run_simulation.stage.json` or equivalent remains available for detailed provenance

### Requirement: Ansible sequences configured stage targets
The system SHALL use Ansible for environment admission, per-stage Make target sequencing, fail-fast harness visibility, and future host targeting without moving provenance-bearing logic out of Python.

#### Scenario: Playbook runs one configured stage per task
- **WHEN** the documented Ansible playbook runs a clean synthetic workflow
- **THEN** Ansible invokes one configured Make stage target per task in configured order
- **AND** a stage failure is visible at the corresponding Ansible task boundary

#### Scenario: Stage order uses run configuration as source of truth
- **WHEN** the Ansible playbook determines which Make targets to run
- **THEN** it derives the target order from `configs/run.synthetic.yaml` through Python/config-derived output or validates that any harness list matches the configured stage order
- **AND** it does not rely on an independently maintained hand-copied stage list that can drift silently

#### Scenario: Ansible does not own scheduler polling
- **WHEN** the mock scheduler job is waiting for terminal state
- **THEN** scheduler polling, timeout handling, and scheduler evidence writing are performed by Python behind the `wait-mock-lsf` Make target rather than by Ansible retry logic

### Requirement: Downstream extraction waits for scheduler success
The system SHALL prevent downstream extraction from running unless the mock scheduler job reaches terminal `DONE` state.

#### Scenario: Extraction follows successful scheduler completion
- **WHEN** the mock scheduler job reaches terminal `DONE` and accounting evidence is collected
- **THEN** downstream extraction stages may run against the produced raw simulation output

#### Scenario: Extraction is blocked after scheduler failure
- **WHEN** the payload exits nonzero, the wait stage times out, the process vanishes, or the job state is not terminal `DONE`
- **THEN** downstream extraction does not run
- **AND** scheduler evidence records the failed or non-terminal condition clearly

### Requirement: Mock scheduler async timing is configurable
The system SHALL support configurable local async timing so operator demos exercise submit/wait/collect while tests can run quickly.

#### Scenario: Operator demo uses observable delay
- **WHEN** the default local async scheduler configuration is used
- **THEN** the simulation payload delay is long enough for `submit_mock_lsf` to return before terminal payload completion

#### Scenario: Tests use fast deterministic delay
- **WHEN** tests override mock runtime delay settings
- **THEN** the async scheduler flow remains deterministic and completes without long wall-clock delays

#### Scenario: Delay jitter is deterministic for a run
- **WHEN** mock runtime delay is configured as a range
- **THEN** the selected delay is deterministic for a given `run_id` when seeded run-id behavior is enabled

#### Scenario: Controlled source delay contract changes explicitly
- **WHEN** controlled-source templates change to support synthetic runtime delay
- **THEN** the delay is owned by the controlled-source demo payload rather than a wrapper-owned scheduler invocation
- **AND** bootstrap compatibility checks, default controlled-source refs, tests, and documentation are updated consistently rather than mutating the existing `controlled-source-demo-v0.1.0` tag contract silently
- **AND** a new controlled-source demo tag such as `controlled-source-demo-v0.1.1` identifies the updated payload contract

