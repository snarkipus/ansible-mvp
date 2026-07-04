## MODIFIED Requirements

### Requirement: Provenance sidecar is separate from simulation root
The system SHALL write provenance evidence and derived products under `runs/{run_id}/provenance/`, not directly under `sim-run-root/`.

#### Scenario: Provenance directories are created
- **WHEN** a valid run workspace is prepared
- **THEN** `runs/{run_id}/provenance/` contains directories for logs, inventories, scheduler metadata, validations, and products

#### Scenario: Derived products are outside simulation root
- **WHEN** extraction and report stages complete
- **THEN** extracted CSVs and generated reports are under `runs/{run_id}/provenance/products/` and not under `runs/{run_id}/sim-run-root/`

#### Scenario: Generated run evidence is not committed to Git
- **WHEN** ordinary run outputs, manifests, logs, scheduler evidence, inventories, validations, extracted products, or report products are generated under `runs/{run_id}/`
- **THEN** they remain generated run evidence and are not committed to the wrapper repository

### Requirement: Source repository stores factory definition
The system SHALL use Git for factory definition artifacts and not for ordinary run evidence.

#### Scenario: Factory definition is versioned
- **WHEN** the wrapper repository is committed
- **THEN** Git tracks source code, Makefile, Ansible playbooks, configuration, specs, tests, docs, lockfiles, and intentionally curated small fixtures or examples

#### Scenario: Archive/freeze is separate from Git commits
- **WHEN** a run is selected for future archive or promotion
- **THEN** the archived evidence is controlled by archive/freeze policy rather than by committing ordinary `runs/{run_id}/` outputs to Git

### Requirement: Archive policy preserves simulation boundary
The system SHALL preserve the boundary between `sim-run-root/` runtime contract and `provenance/` evidence sidecar when defining future archive/freeze behavior.

#### Scenario: Frozen runs preserve consumed inputs and evidence
- **WHEN** a future archive/freeze operation packages a successful run
- **THEN** it preserves the manifest, checksums, validations, logs, inventories, selected products, and exact consumed inputs without moving provenance evidence into `sim-run-root/`
