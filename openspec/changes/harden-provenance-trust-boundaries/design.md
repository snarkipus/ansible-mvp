## Context

The local synthetic workflow has a coherent provenance-capture architecture, but the post-implementation assessment found gaps between admission-time observations and execution-time guarantees. Inputs are copied from a live worktree without proving they are tracked at the selected commit; the runtime engine and extractors execute from that mutable worktree; configured identifiers and paths are not universally contained; extraction trusts a minimal scheduler state file; and final evidence is checked primarily for presence rather than agreement.

The change crosses admission, workspace construction, execution, scheduler evidence, validation, reports, manifest assembly, tests, controlled-source templates, and operator documentation. It must preserve the two-repository model, the documented Ansible command, the `sim-run-root/` simulation contract, the provenance sidecar boundary, fresh-run defaults, and mock-LSF-only MVP scope.

The intended assurance model has three distinct levels:

1. **Capture:** record local inputs, code, stages, outputs, and outcomes.
2. **Binding:** establish that consumed bytes and executed code correspond to the admitted commit and that linked evidence agrees.
3. **Preservation:** protect evidence against later alteration or loss.

This change strengthens capture and binding. Preservation remains future archive/signing work.

## Goals / Non-Goals

**Goals:**

- Reject unsafe run identifiers, repository-relative paths, layout paths, and stage input/output paths before they can cause writes outside designated roots.
- Bind every controlled input and executable dependency to a path and blob in the selected Git commit.
- Execute controlled code from immutable per-run materialization rather than from the live controlled-source worktree.
- Require a coherent scheduler receipt before extraction and represent that coherence in the manifest.
- Preserve failed support-stage attempts where a safe evidence root exists.
- Validate all report inputs before report generation and avoid publishing partial CSV/report products.
- Make manifest validation check cross-record semantics, not only non-empty fields.
- Align specifications and documentation with the implemented assurance level.

**Non-Goals:**

- Real LSF commands or production scheduler integration.
- Cryptographic signing, trusted timestamps, append-only storage, archive/freeze implementation, or custody policy.
- A general workflow engine, retry/resume model, or multi-job scheduler.
- A complete W3C PROV-style graph or stable global artifact identifier scheme.
- A production large-output hashing policy.
- Byte-for-byte deterministic XLSX or PPTX generation beyond atomic publication and structural validation.

## Decisions

### 1. Validate identifiers and paths through one root-aware policy

Introduce shared validation that accepts a candidate path and its designated root, resolves both without requiring the destination to exist, and rejects absolute paths, `..` traversal, and resolved escape. Apply it to run layout paths, materialization source/destination paths, stage working directories, expected inputs/outputs, evidence paths, and product paths before workspace creation.

Constrain `run_id` to `[A-Za-z0-9][A-Za-z0-9._-]*`. This keeps existing examples valid while making path interpolation safe and predictable. Validation belongs in Python so CLI, Make, and Ansible entry paths receive the same policy; Ansible may add an early assertion for operator feedback but is not the authority.

**Alternatives considered:** sanitizing unsafe values would make operator intent ambiguous; checking only final workspace roots would leave source and stage paths exposed; relying on trusted configuration would not satisfy the reference pattern's safety claim.

### 2. Resolve controlled artifacts from the selected Git tree

Build a controlled-artifact identity for every fixture, runtime script, engine, and extractor. Each identity contains repository-relative path, selected commit, Git blob object ID, tracked mode, size, and SHA-256 of bytes read from the selected tree. Admission fails if a declared artifact is absent from that tree, is not a regular file or supported executable mode, or escapes the repository namespace.

Materialize selected-tree bytes into a per-run code/input bundle. Inputs and `run-script.sh` continue to land at their simulation-contract destinations. Engine and extractor dependencies land under `provenance/controlled-source/` and execute from there. All controlled materializations are made read-only after preserving required executable mode. Immediately before payload launch, the scheduler-owned wrapper rehashes the declared runtime script, delegated engine, and complete controlled-input closure against admitted identities; extraction performs the same check for each extractor immediately before execution. Evidence records both source identity and destination hash; materialization or pre-consumption verification fails if they disagree.

The live controlled-source worktree must still be a clean Git worktree for the MVP entrance gate, but execution correctness no longer depends on it remaining at the selected ref after admission.

**Alternatives considered:** repeated worktree/hash checks before each stage still leave time-of-check/time-of-use windows; a detached Git worktree introduces cleanup and worktree-administration complexity; direct `git show` on every execution does not provide stable executable paths. A per-run materialization is simple, inspectable, and naturally belongs with run evidence.

### 3. Version controlled-source template behavior explicitly

Atomic extractor output changes alter controlled payload bytes. Bootstrap creates/verifies a new immutable demo tag `controlled-source-demo-v0.1.2`; it does not mutate prior tags. Defaults, tests, and docs move together. Existing sibling repositories are accepted only when they contain the exact required tag and compatible tracked content.

### 4. Validate one coherent scheduler receipt

Create a scheduler-receipt validator shared by extraction, manifest assembly, and tests. It loads submission, terminal state, normalized job state, accounting, and payload stage evidence, then requires:

- one unique submission receipt ID plus the expected `run_id`, scheduler mode, and `job_id` across records;
- monotonic submission, payload start/finish, terminal-state, and accounting timestamps;
- terminal `DONE` with zero exit status;
- successful payload stage identity and return code;
- accounting that links to the same payload evidence;
- the declared raw output to exist with a hash matching payload output evidence.

Extraction consumes the validated receipt result rather than checking one JSON field. The manifest includes receipt status and links to component evidence. Local mock files remain mutable and are described as local scheduler evidence, not independent authority.

**Alternatives considered:** strengthening only `job-state.json` would preserve multiple unverified sources of truth; cryptographic signing is outside MVP preservation scope.

### 5. Centralize stage-attempt recording around command execution

Wrap support-stage operations in a common attempt context that records start time before work and writes pass/fail evidence after work. Failure records include normalized exception type/message and return code without replacing the original CLI failure. A failure record is written only after path validation and only when creating or using that run evidence root does not violate freshness policy. Preflight failures that intentionally must not create a run root remain available in process/Ansible output and are not forced into an unsafe workspace.

### 6. Validate before reporting and publish products atomically

Reorder configured stages so required and ad hoc CSV validation completes before report generation. Define explicit shape/content checks for both CSVs, including expected headers, numeric fields, logical groups, and the synthetic minimum row/cardinality expectations used by reports.

Extractors and report generation write to sibling temporary paths, close and validate outputs, then use atomic replacement. Failed stages remove their temporary files and do not replace a previously published final path. Report validation reopens XLSX/PPTX and verifies the PNG signature after generation; it does not promise deterministic Office-document bytes.

### 7. Separate manifest contents from finalization receipts

The manifest includes all configured stages completed before manifest assembly. Manifest assembly writes the final manifest first, then writes sibling assembly-stage evidence that identifies the assembled manifest hash. `manifest_smoke` validates that exact manifest plus its assembly receipt and writes separate sibling smoke-stage and validation receipts. Neither finalization step is embedded in the immutable content it finalizes or verifies.

Manifest smoke evolves into semantic validation. It checks configured pre-assembly stage uniqueness/order/success, the external assembly receipt and manifest hash, commit and artifact identity agreement, scheduler receipt coherence, required artifact existence and SHA-256 syntax/value, successful product validations, and product producer references. This remains code-based validation; formal versioned schema work tracked separately is not absorbed.

### 8. Inventory wrapper factory-definition files explicitly

Add a wrapper-controlled-file inventory for configured source, Python, Ansible, Makefile, configuration, lockfile, and other enforced factory-definition paths. Records include repository-relative path, wrapper commit, Git blob ID, mode, and SHA-256. The manifest's hash policy accurately states which files are individually hashed.

### 9. Treat the OpenSpec task list as the epic decomposition contract

After proposal acceptance and before implementation, create one beads epic for this change and child beads aligned to coherent task groups: path safety, controlled-source binding, scheduler receipt, failed-attempt evidence, product integrity, manifest integrity, and contract/docs reconciliation. Existing future schema (`ansible-mvp-nkr`) and real-LSF (`ansible-mvp-bwn`) beads remain separate follow-ons.

## Risks / Trade-offs

- **[Run evidence grows by including executable code]** → Keep the bundle limited to declared runtime dependencies and record its inventory; the synthetic payload is intentionally small.
- **[Git tree materialization mishandles executable modes or symlinks]** → Permit only declared regular files for this MVP, preserve executable mode explicitly, and reject unsupported object types with tests.
- **[A stricter path policy rejects previously accepted debug values]** → Treat unsafe values as unsupported rather than preserving compatibility; document the run ID grammar and validation errors.
- **[Evidence formats change without a formal schema]** → Keep manifest versioning explicit, update all producers/consumers together, and add semantic compatibility tests; formal schema work remains in `ansible-mvp-nkr`.
- **[Failure recording can itself mask the original error]** → Make evidence-write failures secondary diagnostics and preserve the operation's original exit status and exception.
- **[Atomic replacement behaves differently across filesystems]** → Create temporary files in the final destination directory so replacement remains on one filesystem.
- **[The change is broad]** → Deliver through independently testable beads and require the final integration bead to reconcile all task/spec coverage before closure.

## Migration Plan

1. Accept the OpenSpec change and map task groups to one epic plus child beads.
2. Implement shared validation and controlled-artifact identity primitives first.
3. Move controlled-source template behavior to `v0.1.2` and update bootstrap/defaults/tests together.
4. Add scheduler receipt and failure-attempt evidence without changing the Ansible command shape.
5. Reorder validation/report stages and make outputs atomic.
6. Strengthen manifest inventory and post-manifest semantic validation.
7. Update operator documentation only after behavior and evidence formats stabilize.
8. Run `make check`, a clean documented Ansible run, strict OpenSpec validation, and `bd lint --json` before final closure.

Rollback is a normal Git revert before release. Generated runs created under the hardened evidence format are not migrated in place; the MVP has no resume or persisted compatibility requirement, so verification uses fresh run IDs.

## Open Questions

None required before implementation. If formal manifest schema work (`ansible-mvp-nkr`) starts concurrently, coordinate field names but do not make this hardening change depend on completing that future capability.

## Implementation Reconciliation

Final archive review found unresolved enforcement gaps in direct
materialization path containment, integrity checks anchored to admitted Git
identities, complete scheduler-component coherence, validation-receipt binding,
manifest finalization against the originally admitted commit, and independent
post-manifest scheduler verification. The change remains active until these
gaps and their regression tests are complete.

In this MVP, "immutable per-run code" means read-only materialization from an
identified selected commit with pre-execution mode and SHA-256 verification. It
does not mean tamper-proof preservation: signing, trusted timestamps, and
immutable archival remain unimplemented and are stated as assurance
limitations.
