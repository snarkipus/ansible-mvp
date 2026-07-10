## MODIFIED Requirements

### Requirement: Manifest captures input materialization
The system SHALL record how every input artifact entered or participated in the run and SHALL bind controlled inputs to their selected-commit identities.

#### Scenario: Inputs are copied from controlled source
- **WHEN** synthetic fixture inputs are materialized into `sim-run-root/input/`
- **THEN** the manifest records source repository-relative path, selected commit, Git blob ID, tracked mode, source SHA-256, run path, materialization mode, logical group, simulation area, size, mtime, and destination SHA-256
- **AND** source and destination SHA-256 values agree

#### Scenario: Rendered consumed inputs are generated input evidence
- **WHEN** a future stage renders a simulation input from a controlled template and controlled external references
- **THEN** the manifest records the rendered file as a materialized consumed input with template identity, reference identities, render context evidence, rendered destination path, SHA-256 hash, and stage evidence

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
- **THEN** sibling assembly-stage evidence records successful assembly and the final manifest SHA-256
- **AND** smoke validation requires that external receipt to agree with the manifest it checks

### Requirement: Manifest captures validation results
The system SHALL record configured validation results for every extracted product consumed by report generation.

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
The system SHALL provide a post-manifest verification step that checks required manifest structure and semantic consistency, then records a sibling receipt for the exact manifest bytes verified.

#### Scenario: Manifest smoke test passes
- **WHEN** a clean synthetic run completes manifest assembly
- **THEN** smoke validation verifies required sections, configured pre-assembly stage completeness and success, the external assembly receipt and manifest hash, artifact existence and hashes, controlled-source identity agreement, scheduler receipt coherence, successful product validations, and producer references
- **AND** `provenance/validations/manifest_smoke.json` records the SHA-256 of the final `provenance/manifest.yaml` artifact left on disk

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

### Requirement: Manifest captures async scheduler boundary evidence
The system SHALL represent mock scheduler submission, terminal state, normalized job state, accounting, payload execution evidence, and raw-output identity as distinct components of one validated scheduler receipt.

#### Scenario: Scheduler boundary evidence is coherent
- **WHEN** a clean synthetic run completes through the local async mock scheduler
- **THEN** the manifest scheduler section records a passed receipt status and links components that agree on unique receipt ID, scheduler mode, run ID, job ID, monotonic lifecycle timestamps, terminal `DONE`, zero exit status, successful payload evidence, accounting linkage, and raw-output identity

#### Scenario: Scheduler failure is represented
- **WHEN** the mock scheduler job exits unsuccessfully, times out, cannot be collected, or produces inconsistent component evidence
- **THEN** available scheduler evidence and receipt validation record the failed or inconsistent condition for failure diagnosis

## ADDED Requirements

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
