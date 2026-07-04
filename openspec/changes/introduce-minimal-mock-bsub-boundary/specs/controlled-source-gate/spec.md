## ADDED Requirements

### Requirement: Mock scheduler payload remains controlled
The system SHALL require the payload command executed by the mock scheduler to resolve to approved controlled workflow code.

#### Scenario: Scheduler payload references approved controlled command
- **WHEN** the configured mock scheduler payload points at the materialized runtime script or an approved wrapper target that executes it
- **THEN** preflight accepts the payload command and records the controlled script identity used for scheduler-mediated execution

#### Scenario: Scheduler payload references uncontrolled command
- **WHEN** the configured mock scheduler payload points at an arbitrary local script or unapproved executable path
- **THEN** preflight fails before scheduler submission
- **AND** the error identifies the uncontrolled scheduler payload command

### Requirement: Mock scheduler commands remain wrapper-controlled
The system SHALL treat mock scheduler wrapper commands as controlled provenance wrapper behavior rather than uncontrolled local scripts.

#### Scenario: Scheduler wrapper target is approved
- **WHEN** a stage command invokes `submit-mock-lsf`, `wait-mock-lsf`, or `collect-mock-lsf` through the tracked Makefile
- **THEN** preflight accepts the command as an approved wrapper Make target

#### Scenario: Scheduler wrapper bypasses approved command path
- **WHEN** a scheduler stage command attempts to execute an unapproved local helper directly
- **THEN** preflight fails before workflow execution
