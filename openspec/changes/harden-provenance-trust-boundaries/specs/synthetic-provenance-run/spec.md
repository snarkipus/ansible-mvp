## MODIFIED Requirements

### Requirement: Controlled source demo can be bootstrapped
The system SHALL provide a bootstrap command that creates or verifies a sibling `../controlled-source-demo` Git repository at the immutable payload contract required by the synthetic workflow.

#### Scenario: Bootstrap creates demo repository
- **WHEN** `make bootstrap-controlled-source` is run in a workspace without `../controlled-source-demo`
- **THEN** the command creates a Git repository containing synthetic scripts, runtime procs, fixtures, an initial commit, and tag `controlled-source-demo-v0.1.2`

#### Scenario: Bootstrap verifies existing demo repository
- **WHEN** `make bootstrap-controlled-source` is run and a compatible clean `../controlled-source-demo` contains the expected tracked content and `controlled-source-demo-v0.1.2` tag
- **THEN** the command leaves the repository usable for the documented run command

#### Scenario: Bootstrap rejects incompatible demo repository
- **WHEN** `../controlled-source-demo` exists but is not a clean Git repository with expected tracked scripts, fixtures, and tag `controlled-source-demo-v0.1.2`
- **THEN** bootstrap fails with a clear compatibility error instead of overwriting the repository or mutating an older tag

### Requirement: Run workspace preserves canonical simulation layout
The system SHALL create `runs/{run_id}/sim-run-root/` with `input/`, `lists`, `files`, and `procs/` areas for each valid, safely contained run identifier.

#### Scenario: Run workspace is prepared
- **WHEN** a valid run starts with `run_id=demo_001`
- **THEN** the workspace contains `runs/demo_001/sim-run-root/input`, `lists`, `files`, and `procs`

#### Scenario: Unsafe run identifier is rejected
- **WHEN** a run identifier contains traversal, a path separator, or other characters outside the configured safe grammar
- **THEN** the workflow fails before creating any path for that run

### Requirement: Downstream extraction waits for scheduler success
The system SHALL prevent downstream extraction unless submission, terminal state, normalized job state, accounting, payload execution evidence, and produced raw output pass a fresh complete coherence check immediately before each extraction.

#### Scenario: Extraction follows coherent scheduler completion
- **WHEN** all scheduler records identify one submission receipt, the expected run and job, monotonic lifecycle timestamps, terminal state `DONE`, zero exit status, successful payload evidence, linked accounting, and matching raw-output identity
- **THEN** downstream extraction stages may run against the verified raw simulation output

#### Scenario: Extraction is blocked after scheduler failure
- **WHEN** the payload exits nonzero, the wait stage times out, the process vanishes, or the job state is not terminal `DONE`
- **THEN** downstream extraction does not run
- **AND** scheduler evidence records the failed or non-terminal condition clearly

#### Scenario: Extraction is blocked by inconsistent scheduler evidence
- **WHEN** scheduler records or the nested submission identity disagree on receipt ID, run ID, scheduler identity or mode, job ID, configured payload command, timestamp order, exit status, payload evidence, accounting linkage, or raw-output identity
- **THEN** downstream extraction does not run
- **AND** the failed receipt validation identifies each inconsistency

## ADDED Requirements

### Requirement: Product inputs are validated before report generation
The system SHALL validate every extracted CSV consumed by report generation before report products are created, bind successful validation to the CSV size and SHA-256, and recheck that binding against the exact bytes immediately before report consumption.

#### Scenario: Required and ad hoc extracts are valid
- **WHEN** required and ad hoc CSVs satisfy their configured headers, row/cardinality, logical-group, and field-type constraints
- **THEN** report generation may consume them

#### Scenario: Extract validation fails
- **WHEN** either report-input CSV fails configured validation
- **THEN** report generation does not run
- **AND** no successful report products are published for that attempt

### Requirement: Derived products are published atomically
The system SHALL write extracted CSVs and generated reports to temporary files in their destination directories, validate or reopen them as appropriate, and atomically replace final product paths only after successful completion.

#### Scenario: Product generation succeeds
- **WHEN** an extractor or report generator completes and its output passes the required structural check
- **THEN** the temporary output atomically replaces the final product path

#### Scenario: Product generation fails
- **WHEN** an extractor or report generator raises an error or produces an invalid output
- **THEN** no partial output is published at the final product path
- **AND** temporary output is removed or left clearly outside the delivered product inventory

### Requirement: Failed support stages leave attempt evidence safely
The system SHALL record a failed attempt for support and orchestration stages when a validated provenance evidence root can be used without violating fresh-run policy.

#### Scenario: Support operation fails after evidence root is safe
- **WHEN** a configured support stage starts and then fails after its evidence path has been validated
- **THEN** stage evidence records start and finish time, failed status, normalized error, and return code while preserving the original command failure

#### Scenario: Preflight must not create an unsafe or reused root
- **WHEN** admission fails because the run identifier/path is unsafe or a fresh run root already exists
- **THEN** the workflow reports the failure through the invoking process without creating or overwriting that run's provenance root solely to record an attempt

### Requirement: Controlled payload code is run-local and commit-bound
The system SHALL execute controlled simulation and extraction code from the run's selected-commit materialization while preserving `sim-run-root/` as the simulation runtime contract.

#### Scenario: Simulation payload executes
- **WHEN** the mock scheduler launches the controlled payload
- **THEN** `sim-run-root/procs/run-script.sh` and every delegated controlled executable resolve to admitted per-run materializations
- **AND** no controlled executable is loaded from the mutable live worktree
