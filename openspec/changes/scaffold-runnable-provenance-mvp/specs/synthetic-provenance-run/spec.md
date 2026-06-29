## ADDED Requirements

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
The system SHALL create `runs/{run_id}/sim-run-root/` with `input/`, `lists/`, `files/`, and `procs/` areas for each run.

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

### Requirement: Mock scheduler metadata is captured
The system SHALL emulate LSF scheduling for the MVP without requiring real LSF commands.

#### Scenario: Mock submission is recorded
- **WHEN** the mock scheduler stage runs
- **THEN** scheduler metadata is written under `runs/{run_id}/provenance/scheduler/` and references mock LSF mode

#### Scenario: Real LSF tools are absent
- **WHEN** `bsub`, `bjobs`, `bhist`, or `bacct` are not installed
- **THEN** the synthetic MVP can still complete using mock scheduler mode

### Requirement: Workflow can be run through documented command shape
The system SHALL support the documented Ansible command shape for a clean synthetic run.

#### Scenario: Clean synthetic run succeeds
- **WHEN** the controlled source demo is bootstrapped and the documented `ansible-playbook` command is run with `run_id`, `controlled_source_repo`, and `controlled_source_ref`
- **THEN** the workflow completes successfully and writes the expected run and provenance outputs

### Requirement: Handoff guide explains how to use and extend the MVP
The system SHALL include a concise handoff guide for junior engineers using the MVP as a template.

#### Scenario: Engineer follows the guide
- **WHEN** a junior engineer opens `docs/how_to_use_this_mvp.md`
- **THEN** the guide explains prerequisites, setup, bootstrap, run commands, expected outputs, manifest inspection, extension points, and provenance guardrails

#### Scenario: Engineer extends the workflow safely
- **WHEN** the guide describes adding a new stage or controlled script
- **THEN** it instructs the engineer to add the script to a controlled Git repository, declare it in configuration, include it in preflight validation, write outputs to the correct run area, and connect it to the manifest
