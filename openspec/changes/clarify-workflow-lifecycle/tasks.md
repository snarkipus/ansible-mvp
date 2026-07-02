## 1. Configuration and Evidence Model

- [x] 1.1 Add lifecycle metadata to each configured stage in `configs/run.synthetic.yaml` without renaming Make targets.
- [x] 1.2 Propagate `lifecycle_class`, `display_order`, and `operator_visible` into stage-attempt evidence for support and executable stages.
- [x] 1.3 Include lifecycle metadata in manifest `stages` records while preserving all existing stage evidence.

## 2. Makefile and Documentation Clarity

- [x] 2.1 Reorder or comment the Makefile by lifecycle lane: bootstrap, admission, setup, factory, finalization, and developer quality.
- [x] 2.2 Update README and handoff guide to show a concise operator-facing factory flow separate from support/finalization flow.
- [ ] 2.3 Update the README diagram or nearby text to distinguish core workflow stages from support/evidence steps.
- [ ] 2.4 Document that `bootstrap-controlled-source` is demo bootstrap and not an ordinary production factory stage.

## 3. Tests and Validation

- [x] 3.1 Add tests that every configured stage declares lifecycle metadata.
- [x] 3.2 Add tests that manifest stage records include lifecycle metadata and preserve configured display order.
- [x] 3.3 Add tests or documentation checks that existing Make target names remain stable.
- [ ] 3.4 Run `make check`.
- [ ] 3.5 Run `openspec validate clarify-workflow-lifecycle --type change --strict --json` and `openspec validate --specs --strict --json`.
- [ ] 3.6 Run `bd lint --json`.
