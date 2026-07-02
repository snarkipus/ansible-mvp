## MODIFIED Requirements

### Requirement: Manifest captures every configured stage attempt
The system SHALL emit first-class stage-attempt evidence for every configured workflow stage, including support and orchestration stages that do not execute controlled simulation or extraction scripts directly.

#### Scenario: Support stage attempt is recorded
- **WHEN** a clean synthetic run completes a support stage such as `preflight`, `prepare_workspace`, `materialize_inputs`, `materialize_procs`, `submit_mock_lsf`, `inventory_pre`, `inventory_post`, `validate`, `manifest`, or `manifest_smoke`
- **THEN** the run writes stage-attempt evidence with stage name, status, command, working directory or cwd, configured inputs, configured outputs, evidence path, timing, and return code where applicable

#### Scenario: Manifest includes configured stage order
- **WHEN** manifest assembly reads stage-attempt evidence for a clean synthetic run
- **THEN** the manifest `stages` section includes every configured stage in the configured order, including support stages and executable simulation/extraction/report stages

### Requirement: Manifest stage records include lifecycle metadata
The system SHALL include lifecycle classification metadata in manifest stage records so readers can distinguish operator-facing factory stages from demo bootstrap, admission, setup, evidence, and finalization steps.

#### Scenario: Factory and support stages are distinguishable
- **WHEN** a clean synthetic run completes and the manifest is assembled
- **THEN** each manifest stage record includes lifecycle class, display order, and operator-visibility fields

#### Scenario: Documentation can filter operator-visible stages
- **WHEN** a user or report summarizes the run flow for handoff documentation
- **THEN** stages marked operator-visible can be presented as the concise factory flow while non-operator-visible stages remain available as detailed provenance evidence
