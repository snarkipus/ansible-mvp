## Purpose

Define the run-level provenance manifest contract, including repository state, controlled source gate results, materialized inputs and scripts, stage evidence, raw outputs, derived products, validations, hashes, and quality gates.
## Requirements
### Requirement: Manifest captures run identity and repository state
The system SHALL emit `runs/{run_id}/provenance/manifest.yaml` with run identity and repository state for required repositories.

#### Scenario: Manifest includes repository commits
- **WHEN** a clean synthetic run completes
- **THEN** the manifest includes repository path, requested ref, resolved commit, branch/tag/describe output, worktree status, tracked script paths, and script hashes

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

### Requirement: Manifest captures controlled source gate result
The system SHALL record controlled source gate checks and their final status in the manifest for successful runs.

#### Scenario: Controlled source gate passes
- **WHEN** preflight succeeds and the run completes
- **THEN** the manifest includes a successful controlled source gate section with checked repositories, refs, and scripts

### Requirement: Manifest captures input materialization
The system SHALL record how every input artifact entered or participated in the run and SHALL bind controlled inputs to their selected-commit identities.

#### Scenario: Inputs are copied from controlled source
- **WHEN** synthetic fixture inputs are materialized into `sim-run-root/input/`
- **THEN** the manifest records source repository-relative path, selected commit, Git blob ID, tracked mode, source SHA-256, run path, materialization mode, logical group, simulation area, size, mtime, and destination SHA-256
- **AND** source and destination SHA-256 values agree

#### Scenario: Rendered consumed inputs are generated input evidence
- **WHEN** a future stage renders a simulation input from a controlled template and controlled external references
- **THEN** the manifest records the rendered file as a materialized consumed input with template identity, reference identities, render context evidence, rendered destination path, SHA-256 hash, and stage evidence

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
The system SHALL include first-class stage-attempt evidence for every configured stage completed before manifest assembly and SHALL emit sibling finalization receipts for manifest assembly and post-manifest verification, including failed support and orchestration attempts when a safe evidence root exists.

#### Scenario: Successful support stage attempt is recorded
- **WHEN** a support stage such as `prepare_workspace`, `materialize_inputs`, `materialize_procs`, `inventory_pre`, `submit_mock_lsf`, `wait_mock_lsf`, `collect_mock_lsf`, `inventory_post`, or `manifest` completes
- **THEN** the run writes stage-attempt evidence with stage name, display name, lifecycle class, display order, operator-visibility value, status, command, working directory or cwd, configured inputs, configured outputs, evidence path, timing, and return code where applicable

#### Scenario: Failed support stage attempt is recorded
- **WHEN** a configured support stage fails after a safe evidence path is available
- **THEN** its stage-attempt evidence records failed status, timing, normalized error, and return code without masking the original failure

#### Scenario: Manifest includes configured pre-assembly stage order
- **WHEN** manifest assembly reads stage-attempt evidence for a clean synthetic run
- **THEN** the manifest `stages` section includes every configured stage completed before manifest assembly in configured display order
- **AND** manifest assembly and post-manifest smoke evidence are not represented as content inside the manifest they finalize and verify

#### Scenario: Manifest assembly receipt is written externally
- **WHEN** manifest assembly successfully writes the final manifest bytes
- **THEN** sibling assembly-stage evidence is a mapping that records stage name `manifest`, status `pass`, return code `0`, its own evidence path, the finalized manifest path, and the final manifest SHA-256
- **AND** smoke validation requires every identity, outcome, path, and hash field in that external receipt to agree with the receipt and manifest it checks
- **AND** any disagreement is a semantic failure recorded in sibling failed smoke evidence without rewriting the manifest

### Requirement: Manifest stage records include lifecycle metadata
The system SHALL include lifecycle classification metadata in manifest stage records so readers can distinguish operator-facing factory stages from demo bootstrap, admission, setup, evidence, and finalization steps.

#### Scenario: Factory and support stages are distinguishable
- **WHEN** a clean synthetic run completes and the manifest is assembled
- **THEN** each manifest stage record includes display name, lifecycle class, display order, and operator-visibility fields

#### Scenario: Documentation can filter operator-visible stages
- **WHEN** a user or report summarizes the run flow for handoff documentation
- **THEN** stages marked operator-visible can be presented as the concise factory flow while non-operator-visible stages remain available as detailed provenance evidence

### Requirement: Manifest includes a concise operator workflow summary
The system SHALL include a derived workflow summary that presents operator-visible stages in display order without omitting the complete pre-assembly stage evidence list.

#### Scenario: Operator flow is summarized
- **WHEN** manifest assembly reads stage-attempt evidence for a clean synthetic run
- **THEN** the manifest includes `workflow.operator_flow` entries for operator-visible stages with stage name, display name, lifecycle class, display order, status, and evidence path

#### Scenario: Detailed stage evidence remains complete
- **WHEN** the manifest includes `workflow.operator_flow`
- **THEN** the manifest still includes the complete flat `stages` evidence list for all configured stages completed before assembly

### Requirement: Manifest distinguishes raw outputs from derived products
The system SHALL represent raw simulation outputs separately from generated analytical/reporting products.

#### Scenario: Raw and derived outputs are separated
- **WHEN** a clean run completes
- **THEN** `sim-run-root/lists/dirC/sim-out.dat` appears under raw simulation output inventory while CSV/XLSX/PPT/report artifacts appear under derived product inventory

#### Scenario: Report products are represented as derived products
- **WHEN** `summary.xlsx`, `chart.png`, and `briefing.pptx` are generated
- **THEN** the manifest records each report artifact under derived products with product area, relative path, role, producing stage, size, mtime, and SHA-256 hash

### Requirement: Manifest reserves artifact lifecycle metadata
The system SHALL reserve manifest vocabulary for artifact archive, retention, promotion, and external-reference policy so formal schema work can encode artifact lifecycle decisions consistently.

#### Scenario: Archive lifecycle fields are defined for future schema work
- **WHEN** a future manifest schema models artifact lifecycle metadata
- **THEN** it can represent lifecycle state, archive status, archive URI/reference, archive policy, retention class, promotion status, release labels, external references, and hash status

#### Scenario: External references preserve large-output lineage
- **WHEN** a production artifact is too large or policy-restricted to copy into a frozen archive
- **THEN** the manifest can represent it as an external reference with location, hash status, retention class, and provenance lineage

### Requirement: Manifest captures validation results
The system SHALL record configured validation results, including size and SHA-256 of the validated CSV bytes, for every extracted product consumed by report generation, and reports SHALL consume the CSV only after those receipt fields are rechecked against the exact bytes to be read.

#### Scenario: Required extract validation passes
- **WHEN** `provenance/products/extracted/required.csv` satisfies configured headers, field types, logical groups, and expected synthetic row/cardinality constraints
- **THEN** validation passes and the manifest records the validation result

#### Scenario: Ad hoc extract validation passes
- **WHEN** `provenance/products/extracted/ad_hoc.csv` satisfies configured headers, field types, logical groups, and expected synthetic row/cardinality constraints
- **THEN** validation passes and the manifest records the validation result

#### Scenario: Report inputs are validated first
- **WHEN** report generation is ready to run
- **THEN** successful required and ad hoc extract validation evidence already exists

### Requirement: Manifest smoke validation is available
The system SHALL provide a post-manifest verification step that requires explicit configuration, run, workspace, and stage/receipt context, checks required manifest structure and semantic consistency without a structural-only success path, then records a sibling receipt for the exact manifest bytes verified.

#### Scenario: Manifest smoke test passes
- **WHEN** a clean synthetic run completes manifest assembly
- **THEN** smoke validation verifies required sections, configured pre-assembly stage completeness and success, the external assembly receipt and unchanged manifest hash, artifact existence plus current byte size and SHA-256 against recorded identity, admitted selected-commit identity agreement without re-resolving mutable refs/worktrees/inventories, freshly recomputed complete scheduler-component coherence, exactly one receipt at each configured normalized `evidence_path` identifying the configured product path and exactly one current derived-product record and file before checking recorded product size and SHA-256, and producer references
- **AND** the run-local controlled-code inventory covers every selected runtime, engine, and extractor artifact exactly once regardless of mutable inventory role values
- **AND** `provenance/validations/manifest_smoke.json` records the SHA-256 of the final `provenance/manifest.yaml` artifact left on disk

#### Scenario: Smoke context is bound to one configured run
- **WHEN** post-manifest verification is requested for a run
- **THEN** the CLI run ID agrees with `manifest.run.run_id`, the manifest run and provenance roots agree with the configured resolved roots, and the supplied manifest and smoke stage-evidence paths equal the configured paths for that run
- **AND** the external assembly receipt is read only from the configured contained manifest stage-evidence path
- **AND** any cross-run path or symlink escape is rejected before smoke attempt evidence is written

#### Scenario: Post-manifest evidence remains external
- **WHEN** manifest assembly and smoke write their stage-attempt and validation evidence
- **THEN** they do not rewrite the finalized manifest to include those sibling finalization files
- **AND** operator documentation identifies the sibling receipt as the verification result for the manifest hash

### Requirement: SHA-256 hashes are recorded for MVP artifacts
The system SHALL use SHA-256 for declared wrapper factory-definition files, controlled executable code, controlled inputs, raw outputs, extracted CSVs, validation receipts, and report products in the synthetic MVP.

#### Scenario: Controlled factory artifact is inventoried
- **WHEN** a declared wrapper or controlled-source file is admitted
- **THEN** its inventory record includes repository-relative path, selected repository commit, Git blob ID, tracked mode, and SHA-256

#### Scenario: Generated artifact is inventoried
- **WHEN** a small raw output, extracted product, validation receipt, or report product is successfully published
- **THEN** its manifest or inventory record includes a SHA-256 hash value

### Requirement: Python quality gates are available
The system SHALL provide repeatable Python quality checks using `uv`, `ruff`, `basedpyright`, and `pytest`.

#### Scenario: Python quality gate succeeds
- **WHEN** the repository is checked with the documented quality target
- **THEN** `ruff format --check`, `ruff check`, `basedpyright`, and `pytest` run through `uv` and complete successfully

### Requirement: Manifest captures async scheduler boundary evidence
The system SHALL represent mock scheduler submission, terminal state, normalized job state, accounting, payload execution evidence, and raw-output identity as distinct components of one validated scheduler receipt, with complete coherence freshly checked during post-manifest smoke rather than inferred from a stored pass status.

#### Scenario: Scheduler boundary evidence is coherent
- **WHEN** a clean synthetic run completes through the local async mock scheduler
- **THEN** the manifest scheduler section records a passed receipt status and links components that agree on unique receipt ID, scheduler mode, run ID, job ID, monotonic lifecycle timestamps, terminal `DONE`, zero exit status, successful payload evidence, accounting linkage, and raw-output identity
- **AND** the nested submission record repeats and agrees with the top-level run ID, scheduler identity, mode, job ID, receipt ID, and configured controlled payload command

#### Scenario: Scheduler failure is represented
- **WHEN** the mock scheduler job exits unsuccessfully, times out, cannot be collected, or produces inconsistent component evidence
- **THEN** available scheduler evidence and receipt validation record the failed or inconsistent condition for failure diagnosis

### Requirement: Operator workflow summarizes async scheduler phases
The system SHALL summarize the operator-facing workflow as scheduler-mediated simulation execution while preserving the complete detailed pre-assembly stage list.

#### Scenario: Operator flow includes scheduler phases
- **WHEN** manifest assembly builds `workflow.operator_flow` for a clean synthetic run
- **THEN** the operator flow includes submit simulation, wait for simulation, collect scheduler evidence, and downstream extraction/report stages in display order
- **AND** it does not present direct payload execution as an operator action outside the scheduler boundary

#### Scenario: Detailed payload evidence remains complete
- **WHEN** the manifest includes `workflow.operator_flow`
- **THEN** the complete `stages` section still includes payload execution evidence and all support stages completed before assembly

### Requirement: Manifest semantic consistency is enforced
The system SHALL fail post-manifest validation when structurally present records contradict required run invariants.

#### Scenario: Stage records are inconsistent
- **WHEN** configured pre-manifest stages are missing, duplicated, out of order, or not successful in a purported successful-run manifest
- **THEN** post-manifest validation fails and identifies the inconsistent stage records

#### Scenario: Artifact identity is inconsistent
- **WHEN** a referenced artifact is missing, its SHA-256 is malformed or differs from on-disk bytes, or its producer/source identity disagrees with linked evidence
- **THEN** post-manifest validation fails and identifies the artifact and mismatch

#### Scenario: Validation or scheduler status is inconsistent
- **WHEN** a required product validation is not successful or scheduler components do not form a coherent successful receipt
- **THEN** post-manifest validation fails

### Requirement: Manifest states the assurance boundary
The system SHALL distinguish locally captured evidence and selected-commit-bound artifacts from future preservation controls that are not implemented by the MVP.

#### Scenario: Successful local manifest describes assurance
- **WHEN** a clean run manifest is assembled
- **THEN** its hash policy or notes identify controlled inputs and executed code as selected-commit-bound
- **AND** it does not claim signing, immutable archival, trusted timestamping, or tamper-evident preservation
