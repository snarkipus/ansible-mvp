## Why

The lifecycle metadata refactor made stage records classifiable, but the MVP still exposes a busy implementation trace before readers get a concise operator workflow. The configured order also places some evidence/finalization activity before product validation, which weakens the story the docs should teach.

The next improvement should shrink and clarify the operator surface area without reducing provenance completeness. The manifest should retain detailed stage evidence, but also provide a readable workflow summary with stable conceptual names.

## What Changes

- Align configured execution order and display order with lifecycle lanes: admission, setup, pre-run evidence, factory, validation, post-run evidence, manifest finalization.
- Add stable human-readable stage display names while preserving existing stage names and Make target names.
- Add a derived manifest workflow summary for the operator-visible flow so readers can understand the run without parsing every support stage first.
- Update README and handoff documentation to teach from the concise workflow summary while preserving links to detailed provenance evidence.
- Add tests that protect execution order, display names, workflow summary generation, and Make target stability.

## Non-Goals

- Do not rename Make targets or configured stage `name` values.
- Do not replace the flat manifest `stages` evidence list.
- Do not add a full DAG engine, grouped manifest-only evidence model, Jinja rendering, archive/freeze behavior, or `make explain-run` command.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `synthetic-provenance-run`: Aligns execution/display order and uses display names for a smaller operator-facing workflow surface.
- `provenance-manifest`: Adds a derived workflow summary while preserving complete stage evidence.

## Impact

- Affects `configs/run.synthetic.yaml` stage order and metadata.
- Affects Ansible stage target order.
- Affects manifest assembly and smoke validation.
- Affects README/handoff documentation and tests.
