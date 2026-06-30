## Purpose

Define the hard Git-controlled source entrance gate for the provenance MVP, including repository/ref checks, tracked script identity, clean controlled paths, approved stage commands, and materialized runtime scripts.

## Requirements

### Requirement: Required repositories are verified before execution
The system SHALL verify all configured required repositories before executing workflow stages.

#### Scenario: Controlled source repository is missing
- **WHEN** a run is started with a configured `controlled_source_repo` path that does not exist
- **THEN** preflight fails before creating or executing workflow stages

#### Scenario: Required repository is not a Git worktree
- **WHEN** a configured required repository path exists but is not a Git worktree
- **THEN** preflight fails and reports the offending repository path

#### Scenario: Provenance wrapper repository is not a Git worktree
- **WHEN** the provenance wrapper repository is not a Git worktree
- **THEN** preflight fails before creating or executing workflow stages

### Requirement: Requested controlled source ref resolves to a commit
The system SHALL resolve the requested controlled source ref, tag, or commit before execution and record the resolved commit when successful.

#### Scenario: Controlled source ref does not resolve
- **WHEN** `controlled_source_ref` cannot be resolved in the controlled source repository
- **THEN** preflight fails before any workflow stage executes

#### Scenario: Controlled source ref resolves successfully
- **WHEN** `controlled_source_ref` resolves in the controlled source repository
- **THEN** the resolved commit is available for manifest assembly

### Requirement: Required controlled worktrees are clean
The system SHALL fail preflight when the controlled source repository has any dirty tracked state or untracked files.

#### Scenario: Controlled source worktree is dirty
- **WHEN** the controlled source repository contains dirty tracked state or untracked files
- **THEN** preflight fails and reports the dirty repository

### Requirement: Wrapper executable and configuration paths are tracked and clean
The system SHALL verify configured provenance wrapper executable and configuration paths are tracked Git files with no uncommitted changes, while ignored generated outputs do not fail preflight.

#### Scenario: Wrapper controlled path is dirty
- **WHEN** a configured wrapper code, playbook, Makefile, script, template, or config path has uncommitted tracked changes
- **THEN** preflight fails and reports the dirty wrapper-controlled path

#### Scenario: Generated run output exists
- **WHEN** ignored generated files exist under `runs/`
- **THEN** preflight does not fail solely because those generated files exist

### Requirement: Required scripts are tracked Git files
The system SHALL verify every configured workflow script path exists as a tracked file in its declared repository.

#### Scenario: Required script is missing
- **WHEN** a configured required script path does not exist in its declared repository
- **THEN** preflight fails before workflow execution

#### Scenario: Required script is untracked
- **WHEN** a configured required script path exists but is not tracked by Git
- **THEN** preflight fails before workflow execution

### Requirement: Stage commands use approved controlled paths
The system SHALL reject stage command definitions that execute uncontrolled local script paths.

#### Scenario: Stage command references approved controlled script
- **WHEN** a stage command references a configured controlled script by repository-relative path
- **THEN** preflight accepts the command and records the controlled script identity for manifest assembly

#### Scenario: Stage command references arbitrary local script
- **WHEN** a configured stage command points to a script outside approved tracked repository-relative paths
- **THEN** preflight fails and identifies the uncontrolled command path

### Requirement: Stage declarations are validated before execution
The system SHALL validate configured stage declarations before execution, including stage name, command, working directory, expected controlled scripts, and expected inputs or outputs when configured.

#### Scenario: Stage declaration references unknown controlled script
- **WHEN** a stage declaration references a controlled script name that is not defined in the run configuration
- **THEN** preflight fails before workflow execution

### Requirement: Controlled run script is materialized from source
The system SHALL materialize `sim-run-root/procs/run-script.sh` from the tracked controlled source repository for each run.

#### Scenario: Run script materialization succeeds
- **WHEN** preflight passes and the run workspace is prepared
- **THEN** `runs/{run_id}/sim-run-root/procs/run-script.sh` exists and its manifest record includes the controlled source path, resolved commit, materialization mode, and SHA-256 hash
