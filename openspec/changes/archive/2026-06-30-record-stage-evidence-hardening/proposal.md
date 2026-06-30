## Why

After the runnable MVP was archived, an independent data-factory-pattern review identified a provenance gap: executable stages were first-class manifest stages, while support/orchestration stages were represented indirectly through their products. That shape was acceptable for the first MVP, but it leaves room for drift as the workflow grows.

The same follow-up review of OpenSpec artifacts also identified that the implemented command hardening should be captured in the main controlled-source gate specification without expanding the MVP into a full shell parser.

## What Changes

- Require every configured workflow stage, including support/orchestration stages, to emit first-class stage-attempt evidence for successful runs.
- Require the manifest `stages` section to include every configured stage in configured order.
- Record the implemented low-complexity command hardening: configured stage commands must remain simple executable-plus-arguments forms and reject shell interpreter or shell metacharacter constructs.
- Keep these as hardening refinements to the existing MVP, not a production scheduler/resume redesign.

## Capabilities

### Modified Capabilities

- `provenance-manifest`: expands stage evidence expectations to every configured stage.
- `controlled-source-gate`: documents simple command-structure restrictions for stage commands.

## Impact

- Updates main OpenSpec specs only; implementation was already completed in prior commits.
- Adds no new production LSF, retry/resume, or shell parsing framework.
- Preserves the existing Ansible -> Make -> Python helper architecture.
