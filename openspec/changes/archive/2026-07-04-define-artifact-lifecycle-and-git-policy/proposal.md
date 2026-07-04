## Why

The MVP now has a clearer operator workflow and a complete provenance manifest, but it still lacks an explicit policy for what belongs in Git, what remains generated run evidence, what may be archived externally, and how future archive/promotion metadata should appear in provenance.

Without that boundary, follow-on schema work risks encoding accidental habits instead of an intentional artifact lifecycle. The guiding principle is: Git controls the factory machinery; run archives control factory evidence.

## What Changes

- Define the Git boundary for source/control artifacts, configuration, specs, tests, docs, and tiny curated fixtures.
- Classify runtime raw outputs, derived analytical products, evidence artifacts, rendered consumed inputs, and promoted/released outputs.
- Reserve manifest vocabulary for artifact lifecycle state, archive status, archive URI/reference, retention class, promotion status, release labels, and external references.
- Document how future Jinja-rendered simulation inputs should be treated as generated but consumed materialized inputs, not ordinary derived products.
- Define archive/freeze design expectations without implementing `freeze-run` or `archive-run` in this change.

## Non-Goals

- Do not implement archive/freeze commands.
- Do not introduce DVC, MLflow, catalog services, object storage integrations, or production retention automation.
- Do not commit ordinary generated run outputs or generated manifests.
- Do not implement Jinja rendering.
- Do not add formal manifest schema validation; that remains blocked until this policy is accepted.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `synthetic-provenance-run`: Documents the Git/source boundary and generated run artifact policy.
- `provenance-manifest`: Reserves artifact lifecycle/archive/promotion metadata expectations for future schema work.

## Impact

- Affects documentation and OpenSpec requirements.
- Informs blocked manifest schema validation work.
- May later drive archive/freeze implementation, rendered-input manifest fields, and retention policy.
