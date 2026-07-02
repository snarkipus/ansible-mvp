## Why

The MVP is runnable, but its current flat stage list makes demo setup, admission gates, workspace plumbing, domain artifact production, evidence collection, and final verification look like the same kind of workflow activity. This makes it hard for a new reader to discern what supports the local demo versus what represents the core factory workflow that should carry forward to a production target system.

## What Changes

- Add lifecycle classification to configured stages and stage-attempt evidence so support/finalization machinery remains explicit without being confused with core factory transformations.
- Clarify the operator-facing factory flow in README/handoff documentation and diagrams while preserving detailed support evidence in the manifest.
- Organize or comment the Makefile by lifecycle lane without renaming existing targets or breaking established commands.
- Treat `bootstrap-controlled-source` as demo bootstrap outside ordinary run lineage.
- Treat `manifest-smoke`, inventories, and manifest assembly as evidence/finalization rather than core factory transformations.
- Reserve a clear future lifecycle slot for Jinja-rendered consumed simulation inputs without implementing that feature in this change.
- Do not add artifact archive/freeze behavior, formal schema validation, production LSF lifecycle, or target-system Jinja rendering in this change.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `synthetic-provenance-run`: Clarifies lifecycle lanes, operator-facing factory flow, demo bootstrap separation, and documentation expectations.
- `provenance-manifest`: Adds lifecycle metadata expectations for stage declarations and stage-attempt records.

## Impact

- Affects `configs/run.synthetic.yaml` stage declarations and stage evidence/manifest records.
- Affects README and handoff documentation/diagram narrative.
- Affects Makefile organization/comments only; target names and command contract should remain stable.
- Affects tests that assert stage evidence, manifest stage content, and documentation expectations.
