## 1. Execution Tracking and Baseline

- [x] 1.1 Create one beads epic for this accepted change and child beads for path safety, controlled-source binding, scheduler receipt, failed-attempt evidence, product integrity, manifest integrity, and contract/documentation reconciliation, preserving task-to-bead coverage.
- [ ] 1.2 Capture a clean baseline with `make check` and the documented synthetic Ansible run using a fresh run ID.

## 2. Identifier, Path, and Configuration Safety

- [ ] 2.1 Implement one root-aware path validation utility and conservative run-ID grammar used by all CLI workspace/layout construction paths.
- [ ] 2.2 Validate stage names, display order, lifecycle fields, approved Make targets, working directories, inputs, outputs, materialization paths, and evidence paths before workspace creation.
- [ ] 2.3 Add CLI, configuration, and Ansible-entry regression tests for traversal, absolute paths, duplicate stage declarations, escaped destinations, and unapproved Make targets.

## 3. Selected-Commit Artifact Binding

- [ ] 3.1 Implement selected-tree artifact identity including repository-relative path, commit, Git blob ID, tracked mode, size, and SHA-256 for regular controlled files.
- [ ] 3.2 Extend preflight to admit every configured controlled input, runtime script, engine, and extractor from the selected commit and reject ignored, untracked, missing, escaping, or unsupported artifacts.
- [ ] 3.3 Materialize controlled inputs, runtime scripts, engine, and extractors from selected-commit bytes; make all controlled materializations read-only and execute only the run-local code.
- [ ] 3.4 Record source/destination identity and executable mode in materialization inventories, reverify the complete controlled input/executable closure immediately before scheduler payload launch, and reverify each extractor immediately before execution.
- [ ] 3.5 Add tests for ignored inputs, ref/worktree disagreement, post-admission worktree changes, unsupported Git objects, materialized input/code tampering, hash mismatch, and executable-mode preservation.

## 4. Controlled-Source Payload Version

- [ ] 4.1 Update controlled-source extractor templates to publish CSV outputs through destination-directory temporary files and atomic replacement.
- [ ] 4.2 Create the immutable `controlled-source-demo-v0.1.2` bootstrap contract and update defaults, compatibility checks, fixtures, and tests without mutating older tags.

## 5. Scheduler Receipt Coherence

- [ ] 5.1 Generate one unique submission receipt ID, propagate it through scheduler component evidence, and implement a shared validator for identity, monotonic timestamps, terminal status, accounting/payload linkage, and raw-output identity.
- [ ] 5.2 Gate extraction on a passed scheduler receipt and persist actionable receipt-validation evidence for mismatch failures.
- [ ] 5.3 Add negative tests for mismatched receipt/run/job identity, missing or stale receipt components, non-monotonic timestamps, nonzero exit with `DONE`, failed payload evidence, broken accounting linkage, and raw-output hash mismatch.

## 6. Reliable Failed-Attempt Evidence

- [ ] 6.1 Introduce a common support-stage attempt recorder that preserves start/finish timing, pass/fail status, normalized errors, and original return behavior.
- [ ] 6.2 Apply failed-attempt recording to safe post-admission support stages while preserving no-write behavior for unsafe identifiers and rejected fresh-run roots.
- [ ] 6.3 Add failure-path tests for validation, extraction, scheduler collection, report generation, and manifest assembly evidence.

## 7. Product Validation and Atomic Publication

- [ ] 7.1 Define and implement required and ad hoc CSV validation for headers, field types, logical groups, and expected synthetic cardinality.
- [ ] 7.2 Reorder configured stages so all report-input validation passes before report generation and update harness/order assertions.
- [ ] 7.3 Publish reports through destination-directory temporary files, reopen or structurally validate XLSX/PPTX/PNG outputs, and atomically replace final paths.
- [ ] 7.4 Add tests proving invalid CSVs block reports and failed extract/report attempts leave no partial final products.

## 8. Manifest Identity and Semantic Validation

- [ ] 8.1 Add wrapper factory-definition and run-local controlled-code inventories with commit, Git blob ID, mode, and SHA-256 fields.
- [ ] 8.2 Extend manifest assembly with selected-commit input/code identities, scheduler receipt status, complete product validation evidence, and accurate assurance-boundary notes.
- [ ] 8.3 Limit manifest stage completeness to stages finished before assembly, then write sibling assembly and smoke receipts that identify the unchanged final manifest hash.
- [ ] 8.4 Strengthen post-manifest validation for the external assembly receipt, stage uniqueness/order/success, file existence and SHA-256 agreement, source/producer links, scheduler coherence, and successful product validations.
- [ ] 8.5 Add semantic inconsistency and post-manifest self-reference regression tests.

## 9. Contract Reconciliation and Final Verification

- [ ] 9.1 Update README, architecture, operator guide, and artifact trace to document selected-commit binding, safe identifiers/paths, coherent local scheduler evidence, validation ordering, post-manifest receipt behavior, and preservation limitations.
- [ ] 9.2 Reconcile main OpenSpec requirements and controlled-source tag references with the implemented behavior and record any intentional deviations before checking off related tasks.
- [ ] 9.3 Run `make check`, bootstrap/verify `controlled-source-demo-v0.1.2`, and complete the documented Ansible workflow with a fresh run ID; inspect manifest and sibling receipt evidence.
- [ ] 9.4 Run strict OpenSpec validation and `bd lint --json`, verify every completed OpenSpec task maps to a closed bead or documented rationale, and close the implementation epic before archive review.
