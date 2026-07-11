## MODIFIED Requirements

### Requirement: Requested controlled source ref resolves to a commit
The system SHALL resolve the requested controlled source ref, tag, or commit before execution, admit the resolved commit identity, and SHALL use that admitted selected commit as the authoritative source of every declared controlled artifact identity and materialized byte even if the mutable ref or worktree changes later.

#### Scenario: Controlled source ref does not resolve
- **WHEN** `controlled_source_ref` cannot be resolved in the controlled source repository
- **THEN** preflight fails before any workflow stage executes

#### Scenario: Controlled source ref resolves successfully
- **WHEN** `controlled_source_ref` resolves in the controlled source repository
- **THEN** the resolved commit is available for artifact identity, materialization, execution, and manifest assembly

#### Scenario: Declared artifact is absent from selected commit
- **WHEN** a configured controlled input or executable path does not identify a regular tracked file in the selected commit
- **THEN** preflight fails before the run workspace is created
- **AND** the error identifies the offending repository-relative path and selected commit

### Requirement: Required scripts are tracked Git files
The system SHALL verify every configured workflow script and executable dependency exists as a regular tracked file in the selected commit of its declared repository.

#### Scenario: Required script is missing
- **WHEN** a configured required script path does not exist in the selected commit of its declared repository
- **THEN** preflight fails before workflow execution

#### Scenario: Required script is untracked
- **WHEN** a configured required script path exists in the worktree but is not present in the selected commit
- **THEN** preflight fails before workflow execution

#### Scenario: Required script identity is admitted
- **WHEN** a configured script is a regular file in the selected commit
- **THEN** admission records its repository-relative path, selected commit, Git blob ID, tracked mode, and SHA-256

### Requirement: Stage declarations are validated before execution
The system SHALL validate the complete run configuration before creating a run workspace, including unique non-empty stage names and display orders, approved Make targets, commands, lifecycle metadata, working directories, controlled scripts, inputs, outputs, and root containment.

#### Scenario: Stage declaration references unknown controlled script
- **WHEN** a stage declaration references a controlled script name that is not defined in the run configuration
- **THEN** preflight fails before workflow execution

#### Scenario: Stage declarations are ambiguous
- **WHEN** configured stages have duplicate names or duplicate display-order values
- **THEN** preflight fails before creating the run workspace

#### Scenario: Stage command references unapproved Make target
- **WHEN** a wrapper stage command names a Make target outside the configured workflow target allowlist
- **THEN** preflight fails before creating the run workspace

#### Scenario: Stage path escapes its designated root
- **WHEN** a stage working directory, input, output, or evidence path is absolute or resolves outside its designated root
- **THEN** preflight fails before creating the run workspace

### Requirement: Controlled run script is materialized from source
The system SHALL materialize `sim-run-root/procs/run-script.sh` from bytes in the selected controlled-source commit and SHALL verify that its destination SHA-256 matches the admitted source identity.

#### Scenario: Run script materialization succeeds
- **WHEN** preflight passes and the run workspace is prepared
- **THEN** `runs/{run_id}/sim-run-root/procs/run-script.sh` exists and its manifest record includes the controlled source path, selected commit, Git blob ID, tracked mode, materialization mode, and SHA-256 hash
- **AND** the materialized file hash matches the admitted selected-commit bytes

#### Scenario: Materialized run script differs from selected source
- **WHEN** the destination bytes or hash do not match the admitted selected-commit artifact
- **THEN** materialization fails before scheduler submission

## ADDED Requirements

### Requirement: Controlled inputs are tracked at the selected commit
The system SHALL require every configured consumed controlled input to be a regular tracked file in the selected controlled-source commit, materialize it read-only, and verify its SHA-256 against the admitted identity immediately before the scheduler launches the consuming payload.

#### Scenario: Ignored untracked input exists in clean worktree
- **WHEN** a configured fixture path exists only as an ignored or untracked worktree file
- **THEN** preflight fails before materialization
- **AND** the input is not attributed to the selected commit

#### Scenario: Controlled input identity is admitted
- **WHEN** a configured input exists as a regular file in the selected commit
- **THEN** admission records its repository-relative path, selected commit, Git blob ID, tracked mode, and SHA-256
- **AND** admission records the role, source and destination categories, logical group, simulation area, materialization mode, destination path, and destination mode used downstream
- **AND** pre-consumption verification rejects any mutable inventory disagreement with those admitted classifications

#### Scenario: Materialized input changes before consumption
- **WHEN** a materialized controlled input SHA-256 differs from its admitted identity immediately before payload launch
- **THEN** scheduler payload execution fails before the simulation consumes the changed input
- **AND** failure evidence identifies the input integrity mismatch

### Requirement: Controlled execution uses immutable per-run code
The system SHALL execute the runtime script, simulation engine, and extraction scripts from read-only per-run files materialized from the selected controlled-source commit rather than from the live controlled-source worktree, and SHALL verify each executable's SHA-256 against its admitted identity immediately before launch.

#### Scenario: Live worktree changes after admission
- **WHEN** the live controlled-source worktree changes or switches commits after controlled artifacts are materialized
- **THEN** simulation and extraction continue to use the admitted per-run code bytes
- **AND** manifest identities remain tied to the selected commit

#### Scenario: Executable dependency cannot be materialized
- **WHEN** a declared executable dependency cannot be materialized with its admitted bytes and executable mode
- **THEN** the workflow fails before that executable can run

#### Scenario: Run-local executable changes before launch
- **WHEN** a materialized engine or extractor SHA-256 differs from its admitted identity immediately before execution
- **THEN** the stage fails without executing the changed file
- **AND** failure evidence identifies the integrity mismatch

### Requirement: Run identifiers and configured paths are safe
The system SHALL reject run identifiers and configured paths that can escape their designated roots or produce ambiguous run locations.

#### Scenario: Run identifier contains traversal
- **WHEN** `run_id` contains a path separator, `..` traversal, or does not match `[A-Za-z0-9][A-Za-z0-9._-]*`
- **THEN** admission fails before writing run evidence

#### Scenario: Materialization path escapes root
- **WHEN** a configured source or destination path is absolute or resolves outside its controlled-source, simulation, or provenance root
- **THEN** admission fails before workspace creation or file copying
- **AND** each source is checked directly against the controlled-source root and each destination directly against its designated simulation or provenance root
