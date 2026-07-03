## Design

Keep the manifest rigorous and complete, but add a concise reader-facing layer.

The existing flat `stages` list remains the audit trail. Every support, factory, validation, and finalization attempt stays there with command, logs, inputs, outputs, status, timing, and lifecycle metadata.

Add two presentation fields:

- `display_name` on each configured stage and manifest stage record.
- `workflow.operator_flow` as a derived list of operator-visible stages, ordered by `display_order`.

The derived flow is intentionally small and lossy: it is a teaching/navigation aid, not the provenance source of truth. It references underlying stage names so a reader can jump from the summary to detailed evidence.

## Ordering

The run should read in lifecycle order:

```text
preflight
prepare-workspace
materialize-inputs
materialize-procs
inventory-pre
submit-mock-lsf
run-simulation
extract-required
extract-ad-hoc
build-reports
validate
inventory-post
manifest
manifest-smoke
```

This keeps pre-run evidence near setup, validates products before post-run evidence/manifest assembly, and preserves all existing targets.

## Naming

Use display names for people, not as new command identifiers. Examples:

- `preflight` -> `Preflight gate`
- `materialize_inputs` -> `Prepare simulation inputs`
- `submit_mock_lsf` -> `Submit simulation`
- `run_simulation` -> `Run simulation`
- `extract_required` -> `Extract required results`
- `build_reports` -> `Build report products`
- `validate` -> `Validate products`

Do not rename Make targets in this change.

## Manifest Shape

Add a top-level `workflow` section:

```yaml
workflow:
  operator_flow:
    - stage: preflight
      display_name: Preflight gate
      lifecycle_class: admission
      display_order: 10
      status: pass
      evidence_path: runs/demo_001/provenance/logs/preflight.stage.json
```

The `stages` section remains complete and remains the detailed evidence spine.
