## MODIFIED Requirements

### Requirement: Stage commands use approved controlled paths
The system SHALL reject stage command definitions that execute uncontrolled local script paths.

#### Scenario: Stage command references approved controlled script
- **WHEN** a stage command references a configured controlled script by repository-relative path
- **THEN** preflight accepts the command and records the controlled script identity for manifest assembly

#### Scenario: Stage command references arbitrary local script
- **WHEN** a configured stage command points to a script outside approved tracked repository-relative paths
- **THEN** preflight fails and identifies the uncontrolled command path

### Requirement: Stage commands use simple command structures
The system SHALL restrict configured stage commands to simple executable-plus-arguments forms and SHALL reject shell interpreter or shell metacharacter constructs instead of attempting to parse arbitrary shell programs.

#### Scenario: Stage command uses shell interpreter escape
- **WHEN** a configured stage command uses `sh`, `bash`, or another shell interpreter as the executable
- **THEN** preflight fails before workflow execution

#### Scenario: Stage command uses shell metacharacters
- **WHEN** a configured stage command includes shell constructs such as pipes, redirects, command chaining, subshell syntax, or backticks
- **THEN** preflight fails before workflow execution
