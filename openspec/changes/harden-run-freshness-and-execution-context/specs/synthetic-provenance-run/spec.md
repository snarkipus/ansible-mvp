## ADDED Requirements

### Requirement: Run workspaces are fresh by default
The system SHALL reject full workflow runs that attempt to reuse an existing `runs/{run_id}` workspace unless reuse is explicitly requested for developer debugging.

#### Scenario: Existing run workspace is rejected by default
- **WHEN** preflight starts for a `run_id` whose `runs/{run_id}` workspace already exists
- **THEN** preflight fails before writing new run evidence
- **AND** the error explains that the run id must be fresh or explicitly reused

#### Scenario: Explicit reuse policy permits focused debugging
- **WHEN** preflight starts for an existing `runs/{run_id}` workspace with run-root policy `reuse`
- **THEN** preflight continues through the normal controlled-source gate checks
- **AND** the operator has explicitly accepted that existing evidence may remain in the workspace

### Requirement: Evidence collection has a lifecycle lane
The system SHALL distinguish evidence collection from admission, setup, factory, and finalization lifecycle lanes in stage declarations and operator documentation.

#### Scenario: Pre-run inventory is evidence collection
- **WHEN** the `inventory_pre` stage is declared in configuration and recorded in the manifest
- **THEN** its lifecycle class is `evidence`
- **AND** it remains outside the concise operator-facing factory flow

## MODIFIED Requirements

### Requirement: Workflow stages are classified by lifecycle lane
The system SHALL distinguish demo bootstrap, admission, setup, evidence, factory, and finalization lifecycle lanes in stage declarations and operator documentation.

#### Scenario: Stage declaration includes lifecycle metadata
- **WHEN** a configured run stage is declared
- **THEN** the declaration includes a display name, lifecycle class, display order, and operator-visibility value

#### Scenario: Demo bootstrap is outside ordinary run lineage
- **WHEN** `make bootstrap-controlled-source` creates or verifies the synthetic controlled-source repository
- **THEN** documentation describes it as demo bootstrap rather than an ordinary factory stage in the run manifest

#### Scenario: Operator-facing flow is simplified
- **WHEN** a user reads the README or handoff guide
- **THEN** the documentation distinguishes the concise operator workflow from admission/setup plumbing, evidence collection, and finalization support steps

#### Scenario: Make targets remain stable
- **WHEN** lifecycle lanes and display names are documented or added to configuration
- **THEN** existing Make target names remain available for focused debugging
