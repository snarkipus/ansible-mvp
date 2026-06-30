## MODIFIED Requirements

### Requirement: Manifest captures stage execution
The system SHALL record each major stage with command, working directory, timestamps, status, return code, logs, controlled scripts, inputs, and outputs.

#### Scenario: Simulation stage is recorded
- **WHEN** the synthetic simulation stage completes successfully
- **THEN** the manifest stage record includes the materialized run script command, `sim-run-root` working directory, logs, consumed inputs, and produced raw output `sim-run-root/lists/dirC/sim-out.dat`

#### Scenario: Extraction stage is recorded
- **WHEN** a controlled extraction script creates an extracted CSV
- **THEN** the manifest stage record links the extraction command, controlled script identity, source raw outputs, log paths, and derived CSV product

### Requirement: Manifest captures every configured stage attempt
The system SHALL emit first-class stage-attempt evidence for every configured workflow stage, including support and orchestration stages that do not execute controlled simulation or extraction scripts directly.

#### Scenario: Support stage attempt is recorded
- **WHEN** a clean synthetic run completes a support stage such as `preflight`, `prepare_workspace`, `materialize_inputs`, `materialize_procs`, `submit_mock_lsf`, `inventory_pre`, `inventory_post`, `validate`, `manifest`, or `manifest_smoke`
- **THEN** the run writes stage-attempt evidence with stage name, status, command, working directory or cwd, configured inputs, configured outputs, evidence path, timing, and return code where applicable

#### Scenario: Manifest includes configured stage order
- **WHEN** manifest assembly reads stage-attempt evidence for a clean synthetic run
- **THEN** the manifest `stages` section includes every configured stage in the configured order, including support stages and executable simulation/extraction/report stages
