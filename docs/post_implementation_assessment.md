# Post-Implementation Assessment

Date: 2026-07-10

## Executive assessment

The provenance-first simulation MVP is a credible and useful local reference
implementation. Its central design is sound: preserve the simulation runtime
contract, place evidence in a separate sidecar, admit Git-controlled source,
model a scheduler boundary, and assemble a readable run receipt. The result is
more valuable than a synthetic file-generation demo because it makes stage
boundaries, evidence ownership, artifact identity, and failure behavior
concrete.

The implementation should be retained as the basis for the next iteration,
but its trust claims should be narrowed. It is currently a strong local
**provenance-capture pattern**, not a tamper-evident provenance system and not
yet proof that every consumed byte and executed instruction came from the
recorded commit. The most consequential gaps are at that trust boundary:

1. Materialized input fixtures are not proved to be Git-tracked.
2. The engine and extractors execute from a mutable live worktree after
   admission.
3. Operator-controlled identifiers and configured paths are not consistently
   constrained to their intended roots.
4. A shallow, mutable scheduler state record can authorize extraction.
5. The manifest and validation model overstate completeness in several places.

These gaps do not invalidate the MVP's concept or its teaching value. They do
mean that phrases such as "every generated artifact traces back to controlled
source" and "scheduler truth gates products" currently describe intended
lineage more strongly than the implementation establishes it.

## Scope and method

This review assessed:

- the concept and intended value in `README.md`, current documentation, main
  OpenSpec requirements, and archived design decisions;
- the Ansible, Make, Python, configuration, and controlled-source template
  implementation;
- end-to-end sequencing, evidence synthesis, failure behavior, and manifest
  assembly;
- unit, integration, and smoke-test coverage;
- consistency between normative claims, implementation behavior, and operator
  guidance.

Findings are prioritized by impact on the MVP's stated provenance contract,
not by implementation effort. Production-only capabilities that the project
already excludes, such as real LSF integration and durable artifact archival,
are not treated as implementation defects.

## Concept integrity and value

### What is conceptually strong

**The simulation/provenance boundary is clear.** The implementation preserves
`sim-run-root/` as the runtime contract and rejects layouts that place the
provenance root inside it (`src/provenance/workspace.py:106-128`). Derived
products and evidence remain in the sibling provenance tree. This is a useful
adoption pattern because provenance can be added around a legacy simulation
without redefining its working directory.

**The tool boundaries are disciplined.** Ansible remains a thin operational
harness, Make supplies stable local stage names, and Python owns decisions and
evidence. The playbook derives stage targets from configuration rather than
maintaining a duplicate sequence (`ansible/playbooks/run_synthetic_workflow.yml:36-70`).
This keeps the orchestration legible without embedding provenance logic in the
harness.

**The scheduler seam demonstrates the right workflow shape.** Submit, wait,
collect, and scheduler-owned payload execution are distinct. Timeout and
nonzero-exit paths leave inspectable state. Although mock LSF is not an
authoritative scheduler, this is a useful prototype of the boundary a real
adapter must eventually satisfy.

**Artifact identity fits the domain.** Inventories use full relative path,
simulation area, and logical group rather than ambiguous repeated leaf names
(`src/provenance/inventory.py:27-62`). This directly addresses the repeated
`dirA`, `dirB`, and `dirC` structure instead of hiding it behind a generic
model.

**Fresh-run behavior is a good default.** Rejecting an existing run root avoids
silently mixing attempts in a system that has no resume or attempt-history
model. The explicit reuse option is appropriately described as a debugging
escape hatch rather than normal operation.

**The artifact walkthrough communicates practical value.**
`docs/trace_required_csv.md` makes the manifest useful to a reviewer by showing
the joins from source and materialization through scheduler, raw output,
extraction, and validation. This is one of the strongest project deliverables.

### Where the concept is overstated

The design conflates three levels of assurance:

1. **Capture:** record local state, paths, hashes, stages, and outcomes.
2. **Binding:** prove consumed inputs and executed code came from the admitted
   commit and remained unchanged during execution.
3. **Preservation:** make the resulting evidence tamper-evident or durably
   controlled after the run.

The MVP performs capture well. It only partially performs binding and
explicitly defers preservation. The public language should maintain these
distinctions. In particular, the manifest is a structured local receipt, not
an immutable proof, and mock scheduler evidence is wrapper-generated state,
not independent scheduler authority.

## Synthesized implementation quality

The successful path is well synthesized across layers. Configuration defines
the sequence, Ansible exposes one task boundary per stage, Make provides stable
entry points, Python emits evidence, and the manifest gathers the resulting
records. The smoke test exercises the documented Ansible entry point and checks
scheduler completion, output placement, product generation, validation, and
manifest structure (`tests/test_synthetic_workflow_smoke.py:17-136`).

Implementation strengths include:

- command argument vectors are executed without `shell=True`, while preflight
  rejects shell interpreters and metacharacter constructs
  (`src/provenance/preflight.py:300-349`);
- scheduler state uses PID plus Linux process-start identity, reducing PID
  reuse errors, and timeout handling attempts bounded process-group cleanup
  (`src/provenance/scheduler.py:338-427`);
- simulation and extraction stages capture timestamps, return codes, streams,
  controlled scripts, inputs, and outputs (`src/provenance/stages.py:241-287`,
  `393-441`);
- the manifest separates repositories, scheduler evidence, inputs, runtime
  scripts, raw outputs, derived products, validations, and logs
  (`src/provenance/manifest.py:226-264`);
- test coverage is broad for scheduler success and failure modes, command
  admission, workspace boundaries, and the clean end-to-end run.

The main synthesis weakness is that records are assembled into parallel lists
and joined mostly by stage names and paths. This is usable by a human but is
not a formal provenance graph with stable artifact IDs and explicit consumed
and produced edges. That is acceptable for this MVP if described as a
structured receipt rather than complete machine-queryable lineage.

## Critical and high-priority findings

### 1. Controlled inputs are not proved to belong to the selected commit

**Severity: Critical**

Preflight applies tracked-file checks to controlled scripts
(`src/provenance/preflight.py:135-181`) but does not validate configured
`expected_inputs`. Materialization then copies fixture files from the worktree
after checking only repository cleanliness and `HEAD`/ref agreement
(`src/provenance/workspace.py:255-324`). An ignored, untracked fixture can
therefore be consumed while the evidence associates it with a commit that does
not contain it.

This directly conflicts with the controlled-source commitment in
`README.md:42-46` and weakens the beginning of every downstream lineage chain.

**Required response:** require every consumed source path to be contained,
tracked, and present in the selected tree. Record its Git blob identity and
SHA-256. Prefer materializing bytes from the resolved tree or an immutable
checkout rather than from the live worktree.

### 2. Executed code is not pinned after admission

**Severity: Critical**

Only the runtime `run-script.sh` is copied into the run. It delegates to an
engine in the live controlled-source worktree, and extraction likewise runs
live-worktree scripts (`src/provenance/stages.py:210-240`, `370-406`). A clean
commit switch or modification after materialization can change executed code.
Manifest assembly later reads the live repository again
(`src/provenance/manifest.py:304-334`), so recorded hashes can also describe a
different state from execution.

**Required response:** execute the engine and extractors from a detached
worktree or a per-run code materialization pinned to the resolved commit. As a
minimum interim control, recheck repository commit, cleanliness, blob identity,
and file hash immediately before each execution and fail manifest assembly on
identity disagreement.

### 3. Run and configuration paths can escape intended roots

**Severity: Critical**

`run_id` is interpolated into configured paths without a conservative identity
check, and layout paths are joined to the workspace without universal resolved
containment checks (`src/provenance/workspace.py:102-128`, `248-252`). Values
such as `../../outside` can move writes outside `runs/`; malformed configured
source and destination paths have the same class of risk.

**Required response:** validate `run_id` against a conservative identifier
grammar and centralize resolved-path containment for every layout, source,
destination, evidence, and product path before creating the run workspace.

### 4. Scheduler success is too weakly authenticated before extraction

**Severity: High**

Extraction checks only that `job-state.json` is a mapping with
`state == "DONE"` (`src/provenance/stages.py:465-489`). It does not require the
expected run ID or job ID, zero exit status, matching terminal/accounting
records, successful payload stage evidence, or a raw-output hash agreement.
Tests intentionally use a minimal fabricated `DONE` record to unlock
extraction (`tests/test_workspace.py:148-166`). In reuse mode, stale or copied
state can therefore authorize plausible products.

**Required response:** define and validate one coherent scheduler receipt across
submission, terminal state, accounting, payload evidence, and raw output.
Require matching run/job identity, terminal `DONE`, zero exit status, successful
payload evidence, and matching output identity before extraction.

### 5. Failed support stages often leave no stage-attempt evidence

**Severity: High**

Most support-stage evidence is written only after the underlying operation
returns successfully. General CLI exception handling exits without recording a
failed attempt, and failed required validation deliberately omits its stage
attempt (`src/provenance/cli.py:53-67`, `868-873`). This is weakest precisely
when provenance evidence is most useful.

**Required response:** introduce a common attempt recorder that captures start,
finish, normalized failure, status, and return code without masking the
original error. Write it in a `finally` path whenever a safe run evidence root
exists.

### 6. The hashing contract is broader than the implementation

**Severity: High**

The main specification requires SHA-256 for configuration, scripts, small
inputs, extracted CSVs, and reports
(`openspec/specs/provenance-manifest/spec.md:131-136`). The manifest hashes
controlled scripts and inventoried artifacts, but wrapper configuration,
playbooks, and Makefile are identified primarily through repository state and
path rather than per-file hashes (`src/provenance/manifest.py:205-219`,
`304-334`).

**Required response:** either add a wrapper factory-definition inventory with
commit, blob, mode, and SHA-256 or narrow the normative hashing claim. The
inventory is preferable if audit-oriented use is anticipated.

## Important completeness gaps

### Manifest finality has a self-reference boundary

The manifest is assembled before `manifest_smoke`. The smoke step writes its
own stage evidence and a receipt hashing the manifest, but there is no later
reassembly. Consequently, the manifest cannot include its final smoke attempt
or smoke validation, despite the requirement that every configured stage be
included (`openspec/specs/provenance-manifest/spec.md:61-70`). This should be
modeled explicitly as a post-manifest verification receipt rather than claimed
as an included stage.

### Reports precede required-product validation

Configured ordering builds XLSX, PNG, and PPTX reports before validating
`required.csv` (`configs/run.synthetic.yaml:277-340`). Invalid but parseable
data can therefore produce plausible reports that remain after validation
fails. Validation should gate report generation, or products should be marked
unvalidated and withheld from successful finalization.

### Validation coverage is too narrow for the product chain

Only `required.csv` receives basic shape validation. `ad_hoc.csv`, cross-file
row correspondence, report structure, and report content are unchecked. The
required shape permits one row although the synthetic contract expects three
`dirC` rows. Report conversion also maps malformed numeric values to zero
(`src/provenance/reports.py:112-142`). This is structural smoke validation, not
scientific or cross-product validation, and should be labeled accordingly.

### Manifest smoke checks presence rather than consistency

The smoke validator checks required sections and non-empty values but does not
establish that all configured stages occur exactly once and passed, scheduler
records agree, hashes are valid, products exist, validations passed, or commit
and script identities are coherent (`src/provenance/manifest.py:267-285`,
`500-507`). A structurally populated but contradictory manifest can pass.

### Output publication is not uniformly atomic

The synthetic engine uses a temporary file and move, but the Perl extractor
and report builders write directly to final paths. Failure can leave partial
CSV or document artifacts, especially during explicit run reuse. Derived
products should be written to temporary paths, validated or reopened, and
atomically moved into place.

### Preflight validates only part of the stage declaration contract

Preflight validates command kinds and expected controlled scripts but does not
fully validate unique stage names and display orders, working directories,
lifecycle metadata, expected inputs/outputs, or all path containment before the
run starts (`src/provenance/preflight.py:185-245`). It also accepts any
two-token `make <target>` declaration instead of enforcing the intended target
allowlist. Configuration defects can therefore pass admission and fail later.

## Specification and documentation drift

- The current synthetic-run specification still requires controlled-source
  tag `v0.1.0` in its bootstrap scenarios while implementation and operator
  guidance use `v0.1.1`
  (`openspec/specs/synthetic-provenance-run/spec.md:5-18`).
- The architecture's "always hash" language is stronger than manifest
  behavior for wrapper-controlled files.
- "Every configured stage" is incompatible with the current post-manifest
  smoke receipt unless that receipt is explicitly outside manifest contents.
- "Scheduler truth" should be qualified as local mock scheduler evidence until
  coherent receipt validation exists.
- "Every generated artifact traces back to controlled source" should be
  qualified until input tracking and execution pinning are enforced.

These are not cosmetic discrepancies. OpenSpec, README, and operator guidance
form the human-facing contract and should not promise controls that the
implementation does not perform.

## Test assessment

The test suite is broad and well organized for an MVP. It covers the documented
end-to-end command, command-admission rules, async scheduler lifecycle and
failure cases, workspace separation, inventory semantics, manifest structure,
and freshness behavior.

Review-time verification on 2026-07-10 produced the following baseline:

- Ruff formatting and lint passed.
- Basedpyright passed with no errors or warnings.
- 86 pytest tests passed.
- All seven tests in `tests/test_synthetic_workflow_smoke.py` failed before
  workflow execution because their checkout-copy helper encountered the
  existing dangling `docs/hermes-wiki` symlink. This is an environment/repository
  copy-fixture failure, not a workflow assertion failure, but it means the
  end-to-end suite was not green during this review.
- Strict validation of all three main OpenSpec specifications passed.
- `bd lint --json` reported no bead issues.

The smoke-test copy helper currently follows symlinks while cloning the whole
working directory (`tests/test_synthetic_workflow_smoke.py:259`). It is
sensitive to unrelated or ignored workspace entries, so a local dangling
symlink can prevent every end-to-end test from reaching the implementation.
The fixture should copy a controlled tracked-file set, preserve/ignore symlinks
deliberately, or create its checkout through Git.

The highest-value missing tests are:

1. Reject ignored or untracked controlled input fixtures.
2. Prove materialized bytes came from the selected commit.
3. Reject traversal and absolute paths in run IDs and configuration.
4. Detect a controlled repository changing to another clean commit between
   materialization and execution.
5. Reject scheduler `DONE` evidence with wrong run/job identity, nonzero exit,
   absent terminal/accounting receipt, failed payload, or output hash mismatch.
6. Assert failed support stages leave failure-attempt evidence.
7. Reject semantically inconsistent manifests, not only missing fields.
8. Validate ad hoc CSV and generated report integrity.
9. Verify atomic output behavior on extractor and report failures.
10. Exercise controlled-source templates directly in more integration tests;
    several unit tests use simplified duplicate scripts that can drift from
    the bootstrapped payload.

## Recommended disposition and roadmap

### Immediate: align claims and close unsafe boundaries

1. Constrain run IDs and all configured paths before any write.
2. Require tracked, commit-present controlled inputs.
3. Pin all executed controlled code to the admitted commit.
4. Reconcile `v0.1.1`, hashing, manifest-smoke, and scheduler wording across
   current specs and docs.

### Next: strengthen evidence coherence

1. Validate one linked scheduler receipt before extraction.
2. Record failed support-stage attempts consistently.
3. Add semantic manifest consistency checks.
4. Move validations before reports and cover both extracted CSVs.
5. Publish extract and report outputs atomically.

### Later: advance from local receipt to durable provenance

1. Introduce stable artifact identities and explicit consumed/produced edges.
2. Define a formal manifest schema and versioned semantic validation.
3. Define archive, signing, custody, and external-reference policies.
4. Replace mock scheduler evidence with a real adapter that preserves the same
   submit/wait/collect and payload-linkage contract.

## Final conclusion

The MVP succeeds at demonstrating a provenance-first workflow architecture. It
has a coherent operational story, useful separation of concerns, realistic
failure seams, and enough end-to-end implementation to support design review
and further engineering. Its present value is highest as a local reference,
training artifact, and contract prototype.

The implementation does not yet justify audit-grade or reproducibility-grade
claims. Before reuse beyond the controlled demonstration, the project should
secure the commit-to-consumed-bytes and commit-to-executed-code links, enforce
path containment, and validate scheduler evidence as a coherent receipt. With
those changes and corrected contract language, the architecture is a strong
foundation for a production-oriented provenance system.
