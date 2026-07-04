## MODIFIED Requirements

### Requirement: Manifest captures stage execution
The system SHALL record each major stage with command, working directory, timestamps, status, return code, logs, controlled scripts, inputs, and outputs, including scheduler-mediated payload execution.

#### Scenario: Simulation payload stage is recorded
- **WHEN** the synthetic simulation payload completes through the mock scheduler boundary
- **THEN** the manifest stage record includes the materialized run script command, `sim-run-root` working directory, logs, consumed inputs, and produced raw output `sim-run-root/lists/dirC/sim-out.dat`
- **AND** the stage record is linkable from scheduler job state or accounting evidence

#### Scenario: Extraction stage is recorded
- **WHEN** a controlled extraction script creates an extracted CSV after terminal scheduler `DONE`
- **THEN** the manifest stage record links the extraction command, controlled script identity, source raw outputs, log paths, scheduler success prerequisite, and derived CSV product

### Requirement: Manifest captures every configured stage attempt
The system SHALL emit first-class stage-attempt evidence for every configured workflow stage, including support and orchestration stages that do not execute controlled simulation or extraction scripts directly.

#### Scenario: Support stage attempt is recorded
- **WHEN** a clean synthetic run completes a support stage such as `preflight`, `prepare_workspace`, `materialize_inputs`, `materialize_procs`, `inventory_pre`, `submit_mock_lsf`, `wait_mock_lsf`, `collect_mock_lsf`, `inventory_post`, `manifest`, or `manifest_smoke`
- **THEN** the run writes stage-attempt evidence with stage name, display name, lifecycle class, display order, operator-visibility value, status, command, working directory or cwd, configured inputs, configured outputs, evidence path, timing, and return code where applicable

#### Scenario: Manifest includes configured stage order
- **WHEN** manifest assembly reads stage-attempt evidence for a clean synthetic run
- **THEN** the manifest `stages` section includes every configured stage in configured display order, including support stages and executable simulation/extraction/report stages

## ADDED Requirements

### Requirement: Manifest captures async scheduler boundary evidence
The system SHALL represent mock scheduler submission, job state, accounting, and payload execution evidence as distinct linked manifest concepts.

#### Scenario: Scheduler boundary evidence is linked
- **WHEN** a clean synthetic run completes through the local async mock scheduler
- **THEN** the manifest scheduler section links to submission evidence, terminal job state evidence, accounting evidence, job id, final scheduler state, payload execution evidence, and future real-LSF evidence equivalents where recorded

#### Scenario: Scheduler failure is represented
- **WHEN** the mock scheduler job exits unsuccessfully, times out, or cannot be collected because it is non-terminal
- **THEN** available scheduler evidence records the failed or non-terminal condition for manifest assembly or failure diagnosis

### Requirement: Operator workflow summarizes async scheduler phases
The system SHALL summarize the operator-facing workflow as scheduler-mediated simulation execution while preserving the complete detailed stage list.

#### Scenario: Operator flow includes scheduler phases
- **WHEN** manifest assembly builds `workflow.operator_flow` for a clean synthetic run
- **THEN** the operator flow includes submit simulation, wait for simulation, collect scheduler evidence, and downstream extraction/report stages in display order
- **AND** it does not present direct payload execution as an operator action outside the scheduler boundary

#### Scenario: Detailed payload evidence remains complete
- **WHEN** the manifest includes `workflow.operator_flow`
- **THEN** the complete `stages` section still includes payload execution evidence and all support stages needed for auditability
