## 1. Workflow Model

- [x] 1.1 Align Ansible/configured stage order and `display_order` with lifecycle flow while preserving existing target and stage names.
- [x] 1.2 Add `display_name` metadata to configured stages and manifest stage records.
- [x] 1.3 Add derived `workflow.operator_flow` to the manifest from operator-visible stages.

## 2. Documentation

- [x] 2.1 Update README and handoff docs to teach the concise operator flow first and detailed stage evidence second.

## 3. Tests and Validation

- [x] 3.1 Add/update tests for stage order, display names, manifest workflow summary, and stable Make target names.
- [x] 3.2 Run `make check`.
- [x] 3.3 Run `openspec validate clarify-operator-workflow-shape --type change --strict --json` and `openspec validate --specs --strict --json`.
- [x] 3.4 Run `bd lint --json`.
