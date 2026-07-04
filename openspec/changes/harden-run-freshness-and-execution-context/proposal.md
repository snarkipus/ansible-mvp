## Why

The current MVP can rerun a workflow with an existing `run_id`, which risks merging stale evidence from a previous attempt into a manifest that appears clean. The manifest also lacks run-level execution context and timestamps, making handoff evidence weaker than the documented provenance goals.

## What Changes

- Enforce a fresh `runs/{run_id}` entrance policy by default before preflight writes any run evidence.
- Add an explicit `RUN_ROOT_POLICY=reuse` / `--run-root-policy reuse` escape hatch for focused developer debugging of existing run workspaces.
- Record run-level `started_at`, `finished_at`, and `execution_context` metadata in `manifest.yaml`.
- Treat evidence collection as a first-class lifecycle lane and reclassify pre-run inventory evidence accordingly.
- Update operator documentation and tests for fresh-run behavior, context metadata, and lifecycle vocabulary.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `synthetic-provenance-run`: add fresh run workspace requirements, explicit reuse policy behavior, and evidence lifecycle lane vocabulary.
- `provenance-manifest`: add run-level execution context and run-level timestamp requirements.

## Impact

- Affected code: `Makefile`, `src/provenance/cli.py`, `src/provenance/manifest.py`, `src/provenance/workspace.py` or shared helpers as needed, `configs/run.synthetic.yaml`, and tests.
- Affected docs: `README.md`, `docs/how_to_use_this_mvp.md`, and relevant OpenSpec specs.
- Operator behavior: full Ansible runs require a fresh `run_id` by default; focused reuse remains available only when explicitly requested.
