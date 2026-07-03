## Purpose

Define the run-level provenance manifest contract, including repository state, controlled source gate results, materialized inputs and scripts, stage evidence, raw outputs, derived products, validations, hashes, and quality gates.

## Requirements

### Requirement: Manifest captures run identity and repository state
The system SHALL emit `runs/{run_id}/provenance/manifest.yaml` with run identity and repository state for required repositories.

#### Scenario: Manifest includes repository commits
- **WHEN** a clean synthetic run completes
- **THEN** the manifest includes repository path, requested ref, resolved commit, branch/tag/describe output, worktree status, tracked script paths, and script hashes

### Requirement: Manifest captures controlled source gate result
The system SHALL record controlled source gate checks and their final status in the manifest for successful runs.

#### Scenario: Controlled source gate passes
- **WHEN** preflight succeeds and the run completes
- **THEN** the manifest includes a successful controlled source gate section with checked repositories, refs, and scripts

### Requirement: Manifest captures input materialization
The system SHALL record how every input artifact entered or participated in the run.

#### Scenario: Inputs are copied from controlled source
- **WHEN** synthetic fixture inputs are materialized into `sim-run-root/input/`
- **THEN** the manifest records their source path, run path, materialization mode, logical group, simulation area, size, mtime, and SHA-256 hash

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
- **WHEN** a clean synthetic run completes a support stage such as `preflight`, `prepare_workspace`, `materialize_inputs`, `materialize_procs`, `inventory_pre`, `submit_mock_lsf`, `inventory_post`, `manifest`, or `manifest_smoke`
- **THEN** the run writes stage-attempt evidence with stage name, display name, lifecycle class, display order, operator-visibility value, status, command, working directory or cwd, configured inputs, configured outputs, evidence path, timing, and return code where applicable

#### Scenario: Manifest includes configured stage order
- **WHEN** manifest assembly reads stage-attempt evidence for a clean synthetic run
- **THEN** the manifest `stages` section includes every configured stage in configured display order, including support stages and executable simulation/extraction/report stages

### Requirement: Manifest stage records include lifecycle metadata
The system SHALL include lifecycle classification metadata in manifest stage records so readers can distinguish operator-facing factory stages from demo bootstrap, admission, setup, evidence, and finalization steps.

#### Scenario: Factory and support stages are distinguishable
- **WHEN** a clean synthetic run completes and the manifest is assembled
- **THEN** each manifest stage record includes display name, lifecycle class, display order, and operator-visibility fields

#### Scenario: Documentation can filter operator-visible stages
- **WHEN** a user or report summarizes the run flow for handoff documentation
- **THEN** stages marked operator-visible can be presented as the concise factory flow while non-operator-visible stages remain available as detailed provenance evidence

### Requirement: Manifest includes a concise operator workflow summary
The system SHALL include a derived workflow summary that presents operator-visible stages in display order without omitting the complete stage evidence list.

#### Scenario: Operator flow is summarized
- **WHEN** manifest assembly reads stage-attempt evidence for a clean synthetic run
- **THEN** the manifest includes `workflow.operator_flow` entries for operator-visible stages with stage name, display name, lifecycle class, display order, status, and evidence path

#### Scenario: Detailed stage evidence remains complete
- **WHEN** the manifest includes `workflow.operator_flow`
- **THEN** the manifest still includes the complete flat `stages` evidence list for all configured stages

### Requirement: Manifest distinguishes raw outputs from derived products
The system SHALL represent raw simulation outputs separately from generated analytical/reporting products.

#### Scenario: Raw and derived outputs are separated
- **WHEN** a clean run completes
- **THEN** `sim-run-root/lists/dirC/sim-out.dat` appears under raw simulation output inventory while CSV/XLSX/PPT/report artifacts appear under derived product inventory

#### Scenario: Report products are represented as derived products
- **WHEN** `summary.xlsx`, `chart.png`, and `briefing.pptx` are generated
- **THEN** the manifest records each report artifact under derived products with product area, relative path, role, producing stage, size, mtime, and SHA-256 hash

### Requirement: Manifest captures validation results
The system SHALL perform simple shape validation for generated CSV products and record validation results.

#### Scenario: Required extract shape passes
- **WHEN** `provenance/products/extracted/required.csv` exists with configured headers and minimum row count
- **THEN** validation passes and the manifest records the validation result

### Requirement: Manifest smoke validation is available
The system SHALL provide a focused verification step that checks the generated manifest has required top-level sections and key non-empty values.

#### Scenario: Manifest smoke test passes
- **WHEN** a clean synthetic run completes
- **THEN** the smoke test verifies required manifest sections including `manifest_version`, `run`, `workflow`, `repositories`, `simulation_layout`, `controlled_source_gate`, `scheduler`, `inputs`, `runtime_scripts`, `stages`, `raw_simulation_outputs`, `derived_products`, `validations`, `logs`, `hash_policy`, and `notes`

### Requirement: SHA-256 hashes are recorded for MVP artifacts
The system SHALL use SHA-256 for scripts, configuration, small inputs, extracted CSVs, and report products in the synthetic MVP.

#### Scenario: Hashable artifact is inventoried
- **WHEN** a small controlled or generated artifact is inventoried
- **THEN** its manifest or inventory record includes a SHA-256 hash value

### Requirement: Python quality gates are available
The system SHALL provide repeatable Python quality checks using `uv`, `ruff`, `basedpyright`, and `pytest`.

#### Scenario: Python quality gate succeeds
- **WHEN** the repository is checked with the documented quality target
- **THEN** `ruff format --check`, `ruff check`, `basedpyright`, and `pytest` run through `uv` and complete successfully
