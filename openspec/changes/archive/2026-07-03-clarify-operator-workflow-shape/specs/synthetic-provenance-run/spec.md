## MODIFIED Requirements

### Requirement: Workflow stages are classified by lifecycle lane
The system SHALL distinguish demo bootstrap, admission, setup, factory, and finalization lifecycle lanes in stage declarations and operator documentation.

#### Scenario: Stage declaration includes lifecycle metadata
- **WHEN** a configured run stage is declared
- **THEN** the declaration includes a display name, lifecycle class, display order, and operator-visibility value

#### Scenario: Operator-facing flow is simplified
- **WHEN** a user reads the README or handoff guide
- **THEN** the documentation distinguishes the concise operator workflow from admission/setup plumbing, evidence collection, and finalization support steps

#### Scenario: Make targets remain stable
- **WHEN** lifecycle lanes and display names are documented or added to configuration
- **THEN** existing Make target names remain available for focused debugging

### Requirement: Workflow can be run through documented command shape
The system SHALL support the documented Ansible command shape for a clean synthetic run.

#### Scenario: Clean synthetic run succeeds
- **WHEN** the controlled source demo is bootstrapped and the documented `ansible-playbook` command is run with `run_id`, `controlled_source_repo`, and `controlled_source_ref`
- **THEN** the workflow completes successfully and writes expected run outputs, detailed stage evidence, and a concise operator workflow summary
