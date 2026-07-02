## Context

The current MVP intentionally exposes granular Make targets because they are useful for debugging and agent-driven implementation. The same granularity is less helpful as the conceptual workflow model. A flat list of stages makes `preflight`, `prepare_workspace`, `run_simulation`, `inventory_post`, and `manifest_smoke` appear equally central, even though only some of them produce or transform domain artifacts.

The largest objective of this change is clarity. A reader should quickly understand which steps are demo bootstrap or support machinery and which steps are the core workflow that would carry over to the actual target system.

## Goals / Non-Goals

**Goals:**

- Introduce lifecycle classes for configured stages and stage-attempt evidence.
- Preserve current Make target names and behavior for compatibility and focused debugging.
- Organize/comment the Makefile so target groups communicate lifecycle intent.
- Update documentation and diagrams to teach the core factory flow separately from support/evidence flow.
- Keep detailed stage-attempt evidence for support/finalization stages in the manifest.
- Reserve a clean conceptual place for future Jinja-rendered consumed simulation inputs.

**Non-Goals:**

- Rename Make targets in this first refactor.
- Remove support stage evidence from the manifest.
- Implement Jinja-rendered inputs.
- Implement artifact archive/freeze behavior.
- Implement formal manifest schema validation.
- Implement real asynchronous LSF lifecycle or run resume semantics.

## Decisions

1. Use lifecycle metadata rather than renaming targets first.

   Add `lifecycle_class`, `display_order`, and `operator_visible` to stage declarations and carry those values into stage-attempt evidence and manifest records. This clarifies semantics while preserving existing commands.

   Alternative considered: rename targets like `extract-required` to `extract-results` immediately. That may improve wording but creates churn before the lifecycle model is proven.

2. Use five lifecycle lanes.

   The intended lanes are `bootstrap`, `admission`, `setup`, `factory`, and `finalization`. `bootstrap` is demo setup outside ordinary run lineage; `admission` decides whether a run may start; `setup` prepares workspace/runtime plumbing; `factory` produces or transforms consumed/delivered domain artifacts; `finalization` collects, verifies, assembles, or eventually freezes evidence.

   Alternative considered: use only `support` and `factory`. That is simpler but less useful for explaining preflight versus final manifest verification.

3. Keep every configured stage manifest-visible.

   The recent stage-attempt hardening is still valuable. Support and finalization stages should not disappear; they should be labeled so readers can filter or summarize the factory path without losing evidence.

   Alternative considered: exclude support stages from `manifest.stages`. That would simplify the displayed flow but reintroduce hidden orchestration evidence.

4. Treat current static input materialization as setup, but reserve future rendered consumed inputs as factory work.

   `materialize_inputs` currently copies static demo fixtures, so it is setup-ish. A future Jinja render stage that creates the exact consumed simulation input should be modeled as `factory` because it changes the scientific/data state consumed by the simulation.

5. Present a small operator-facing flow in docs.

   Documentation should emphasize a simplified factory path such as prepare simulation inputs, submit/run simulation, extract results, build report products, validate products, and assemble/verify manifest. Detailed Make targets can remain documented separately as debug/support entry points.

## Risks / Trade-offs

- Lifecycle labels could become another taxonomy to maintain -> Keep the allowed classes small and test that all configured stages carry one.
- Docs may diverge from granular Make targets -> Keep the Makefile grouped/commented by the same lifecycle classes and link docs to the stable target list.
- `operator_visible` could hide too much -> It only controls documentation/reporting emphasis; manifest evidence remains complete.
- Future Jinja input behavior may change classification -> Reserve the slot now but do not implement the feature until its own change.

## Migration Plan

1. Add lifecycle metadata to the existing stage declarations.
2. Carry lifecycle metadata into support and executable stage-attempt evidence.
3. Include lifecycle metadata in manifest `stages` records.
4. Reorder/comment Makefile targets by lifecycle lane without renaming targets.
5. Update README/handoff guide and diagram to distinguish operator-facing factory flow from support/finalization flow.
6. Add tests that verify lifecycle metadata appears and that the current command contract remains stable.
