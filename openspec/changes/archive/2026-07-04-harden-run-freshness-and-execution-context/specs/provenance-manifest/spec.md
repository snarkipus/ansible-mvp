## ADDED Requirements

### Requirement: Manifest captures run-level timing
The system SHALL record run-level start and finish timestamps in `runs/{run_id}/provenance/manifest.yaml` for successful synthetic runs.

#### Scenario: Run timing is derived from stages
- **WHEN** manifest assembly reads stage evidence with `started_at` and `finished_at` timestamps
- **THEN** the manifest `run` section includes `started_at` equal to the earliest stage start timestamp
- **AND** the manifest `run` section includes `finished_at` equal to the latest stage finish timestamp

### Requirement: Manifest captures execution context
The system SHALL record local execution context in `runs/{run_id}/provenance/manifest.yaml` for successful synthetic runs.

#### Scenario: Execution context is recorded
- **WHEN** a clean synthetic run completes and the manifest is assembled
- **THEN** the manifest `run.execution_context` section includes non-empty `executed_by`, `hostname`, `platform`, `python_version`, and `git_version` values

#### Scenario: Manifest smoke requires execution context
- **WHEN** manifest smoke validation checks a clean synthetic run manifest
- **THEN** it fails if `run.execution_context` is absent or empty
