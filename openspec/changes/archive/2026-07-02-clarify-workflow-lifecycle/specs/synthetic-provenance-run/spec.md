## MODIFIED Requirements

### Requirement: Workflow can be run through documented command shape
The system SHALL support the documented Ansible command shape for a clean synthetic run.

#### Scenario: Clean synthetic run succeeds
- **WHEN** the controlled source demo is bootstrapped and the documented `ansible-playbook` command is run with `run_id`, `controlled_source_repo`, and `controlled_source_ref`
- **THEN** the workflow completes successfully and writes the expected run and provenance outputs

### Requirement: Workflow stages are classified by lifecycle lane
The system SHALL distinguish demo bootstrap, admission, setup, factory, and finalization lifecycle lanes in stage declarations and operator documentation.

#### Scenario: Stage declaration includes lifecycle metadata
- **WHEN** a configured run stage is declared
- **THEN** the declaration includes a lifecycle class, display order, and operator-visibility value

#### Scenario: Demo bootstrap is outside ordinary run lineage
- **WHEN** `make bootstrap-controlled-source` creates or verifies the synthetic controlled-source repository
- **THEN** documentation describes it as demo bootstrap rather than an ordinary factory stage in the run manifest

#### Scenario: Operator-facing flow is simplified
- **WHEN** a user reads the README or handoff guide
- **THEN** the documentation distinguishes the core factory flow from admission, setup, evidence collection, and finalization support steps

#### Scenario: Make targets remain stable
- **WHEN** lifecycle lanes are documented or added to configuration
- **THEN** existing Make target names remain available for focused debugging

### Requirement: Handoff guide explains how to use and extend the MVP
The system SHALL include a concise handoff guide for junior engineers using the MVP as a template.

#### Scenario: Engineer follows the guide
- **WHEN** a junior engineer opens `docs/how_to_use_this_mvp.md`
- **THEN** the guide explains prerequisites, setup, bootstrap, run commands, expected outputs, manifest inspection, extension points, and provenance guardrails

#### Scenario: Engineer extends the workflow safely
- **WHEN** the guide describes adding a new stage or controlled script
- **THEN** it instructs the engineer to add the script to a controlled Git repository, declare it in configuration, include it in preflight validation, write outputs to the correct run area, connect it to the manifest, and choose the appropriate lifecycle class
