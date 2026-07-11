## Why

The MVP captures useful local provenance, but its current contracts imply stronger assurance than the implementation enforces: consumed inputs and executed code are not immutably bound to the admitted commit, workspace paths can escape intended roots, scheduler success is weakly cross-checked, and final evidence can be structurally complete while semantically inconsistent. The post-implementation assessment identifies these as the minimum trust-boundary gaps to close before the reference pattern is reused beyond a controlled demonstration.

## What Changes

- Constrain run identifiers and all configured run paths to their designated repository, simulation, provenance, or controlled-source roots before any run workspace is written.
- Require every consumed controlled input and executable script to be tracked and present in the selected Git commit, and materialize or execute immutable bytes associated with that commit.
- Replace the extraction stage's shallow `DONE` check with validation of a coherent scheduler receipt linking submission, terminal state, accounting, payload evidence, run/job identity, exit status, and produced raw output.
- Record failed support and orchestration stage attempts whenever a safe provenance evidence root exists.
- Validate extracted data before report generation, cover every report input, and publish extractor/report outputs atomically.
- Strengthen manifest hashing and semantic consistency checks, and explicitly model manifest assembly and smoke validation as sibling finalization receipts rather than content embedded in the manifest they finalize and verify.
- Reconcile current specifications and operator documentation with the implemented assurance level, including the controlled-source demo tag and the distinction between local provenance capture, commit binding, and durable preservation.
- Add focused negative and end-to-end tests for each trust boundary.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `controlled-source-gate`: Extend admission from script checks to all consumed controlled inputs and executable dependencies, require selected-commit identity, validate complete stage declarations, and reject unsafe paths before run creation.
- `synthetic-provenance-run`: Constrain run layout paths, require immutable controlled-source execution, validate coherent scheduler success before downstream products, order validation before reports, publish products atomically, and clarify failed-attempt evidence.
- `provenance-manifest`: Strengthen artifact hashing and cross-record semantic validation, define post-manifest smoke receipt behavior, and accurately distinguish captured, commit-bound, and preserved evidence.

## Impact

- Affects `src/provenance/` admission, workspace, stage, scheduler, report, validation, manifest, and CLI behavior.
- Changes `configs/run.synthetic.yaml` stage ordering and may extend evidence records with Git blob identity and scheduler linkage fields.
- Changes controlled-source materialization/execution behavior while preserving the existing `sim-run-root/` contract and operator-facing Ansible command shape.
- Updates controlled-source templates where atomic output publication is required.
- Updates all three current OpenSpec capabilities plus README, architecture, operator, and artifact-trace documentation.
- Expands unit, integration, and smoke coverage. No real LSF, archive/signing, artifact catalog, or production large-output policy is introduced.
