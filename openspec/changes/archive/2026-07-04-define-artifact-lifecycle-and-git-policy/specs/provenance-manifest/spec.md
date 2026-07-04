## MODIFIED Requirements

### Requirement: Manifest captures input materialization
The system SHALL record how every input artifact entered or participated in the run.

#### Scenario: Inputs are copied from controlled source
- **WHEN** synthetic fixture inputs are materialized into `sim-run-root/input/`
- **THEN** the manifest records their source path, run path, materialization mode, logical group, simulation area, size, mtime, and SHA-256 hash

#### Scenario: Rendered consumed inputs are generated input evidence
- **WHEN** a future stage renders a simulation input from a controlled template and controlled external references
- **THEN** the manifest records the rendered file as a materialized consumed input with template identity, reference identities, render context evidence, rendered destination path, SHA-256 hash, and stage evidence

### Requirement: Manifest distinguishes raw outputs from derived products
The system SHALL represent raw simulation outputs separately from generated analytical/reporting products.

#### Scenario: Raw and derived outputs are separated
- **WHEN** a clean run completes
- **THEN** `sim-run-root/lists/dirC/sim-out.dat` appears under raw simulation output inventory while CSV/XLSX/PPT/report artifacts appear under derived product inventory

#### Scenario: Report products are represented as derived products
- **WHEN** `summary.xlsx`, `chart.png`, and `briefing.pptx` are generated
- **THEN** the manifest records each report artifact under derived products with product area, relative path, role, producing stage, size, mtime, and SHA-256 hash

### Requirement: Manifest reserves artifact lifecycle metadata
The system SHALL reserve manifest vocabulary for artifact archive, retention, promotion, and external-reference policy so formal schema work can encode artifact lifecycle decisions consistently.

#### Scenario: Archive lifecycle fields are defined for future schema work
- **WHEN** a future manifest schema models artifact lifecycle metadata
- **THEN** it can represent lifecycle state, archive status, archive URI/reference, archive policy, retention class, promotion status, release labels, external references, and hash status

#### Scenario: External references preserve large-output lineage
- **WHEN** a production artifact is too large or policy-restricted to copy into a frozen archive
- **THEN** the manifest can represent it as an external reference with location, hash status, retention class, and provenance lineage
