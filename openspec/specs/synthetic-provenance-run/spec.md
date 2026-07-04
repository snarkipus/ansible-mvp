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
