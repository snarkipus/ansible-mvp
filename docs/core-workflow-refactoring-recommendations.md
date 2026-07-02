# Ansible MVP Core Workflow Refactoring Recommendations

## Purpose

This page captures discussion guidance for a dedicated OpenSpec change in `snarkipus/ansible-mvp` to separate bootstrap/demo-validation/support machinery from the main factory workflow. It is meant as implementation-agent context for turning the current runnable MVP into a clearer teaching artifact.

The short version: **the current stage list is useful for debugging but overcooked as the conceptual workflow.** The Makefile can stay granular; the operator-facing factory model should be smaller, clearer, and lifecycle-classed.

## Current stage soup

The current repo exposes many targets/stages around a single synthetic run:

```text
bootstrap-controlled-source
preflight
prepare-workspace
materialize-inputs
materialize-procs
submit-mock-lsf
run-simulation
extract-required
extract-ad-hoc
build-reports
inventory-pre
inventory-post
validate
manifest
manifest-smoke
```

`configs/run.synthetic.yaml` also declares a flat `stages:` list containing both domain-relevant stages and support actions. That flat list is the source of the smell. It makes `preflight`, `prepare_workspace`, `run_simulation`, `inventory_post`, and `manifest_smoke` look like equally meaningful workflow stages when they are not.

The better distinction:

> A factory stage changes the scientific/data state. A support stage changes the execution environment or records evidence.

## Recommended lifecycle lanes

Separate the MVP into four or five lifecycle lanes:

| Lifecycle lane | Purpose | Examples |
|---|---|---|
| `bootstrap` | Demo setup outside ordinary production runs | `bootstrap-controlled-source` |
| `admission` | Decide whether the run is allowed to start | `preflight`, `resolve_references` |
| `setup` | Create run workspace and materialize runtime plumbing | `prepare_workspace`, `materialize_runtime_scripts` |
| `factory` | Produce or transform consumed/delivered domain artifacts | `render_simulation_inputs`, `run_simulation`, `extract_results`, `build_report_products`, `validate_products` |
| `finalization` | Assemble, verify, freeze, or archive evidence | `inventory_outputs`, `assemble_manifest`, `verify_manifest`, `freeze_run` |

This grouping should show up in documentation and manifest records. It does not require deleting granular Make targets.

## Core factory flow to teach

The operator-facing factory flow should be closer to:

```text
resolve external references
      ↓
render / prepare simulation inputs
      ↓
submit / run simulation
      ↓
extract results
      ↓
build report products
      ↓
validate products
      ↓
assemble / verify manifest
```

If the rendered Jinja simulation input is added to the demo, the core workflow becomes even cleaner:

```text
resolve references
      ↓
render simulation input from controlled template + external Git files
      ↓
run simulation
      ↓
extract/report/validate
```

The key point is that Jinja rendering is not mere setup if it creates the exact file consumed by the simulation. It is a core factory stage with attached evidence.

## Suggested classification of current stages

| Current target/stage | Recommended lifecycle class | Operator-facing? | Notes |
|---|---|---:|---|
| `bootstrap-controlled-source` | `bootstrap` | no | Demo convenience, outside ordinary run lineage. |
| `preflight` | `admission` | yes, as a gate | Important, but not a factory transformation. |
| `prepare-workspace` | `setup` | mostly no | Required plumbing. |
| `materialize-inputs` | `factory` or `setup` | yes if rendering consumed input | For static copied fixtures it is setup-ish; for Jinja-rendered consumed inputs it is core factory. |
| `materialize-procs` | `setup` | no | Runtime script materialization; important evidence, not domain flow. |
| `submit-mock-lsf` | `factory` / scheduler boundary | yes | In production this becomes scheduler submission evidence. |
| `run-simulation` | `factory` | yes | Core. |
| `extract-required` | `factory` | yes | Core contracted product. |
| `extract-ad-hoc` | `factory` or demo optional | maybe | Consider folding under `extract_results` as optional/demo product. |
| `build-reports` | `factory` | yes | Core if reports are delivered outputs. |
| `inventory-pre` | `evidence` / `finalization` | no | Evidence collection, not domain stage. |
| `inventory-post` | `evidence` / `finalization` | no | Evidence collection, not domain stage. |
| `validate` | `factory` or `finalization` | yes | If validation is a product quality gate, keep operator-visible. |
| `manifest` | `finalization` | no | Assemble evidence, not domain transformation. |
| `manifest-smoke` | `finalization` | no | QA on the receipt. |

## Naming recommendations

Prefer workflow-shaped names for the conceptual model, even if Make targets remain mechanical:

| Current | Better conceptual name |
|---|---|
| `materialize-inputs` | `prepare_simulation_inputs` or `render_simulation_inputs` |
| `submit-mock-lsf` | `submit_simulation` |
| `extract-required` + `extract-ad-hoc` | `extract_results` with multiple products |
| `build-reports` | `build_report_products` |
| `validate` | `validate_products` |
| `manifest` | `assemble_manifest` |
| `manifest-smoke` | `verify_manifest` |

Avoid making the human handoff read like an implementation trace. The implementation may need bolts; the reader needs the machine.

## Manifest model recommendation

The least disruptive first step is adding lifecycle metadata to each stage attempt:

```yaml
stages:
  - name: run_simulation
    lifecycle_class: factory
    display_order: 30
    operator_visible: true
    status: pass
    command: procs/run-script.sh
    working_directory: runs/demo_001/sim-run-root
```

A cleaner later shape could group attempts by lifecycle:

```yaml
lifecycle:
  admission:
    - name: preflight
    - name: resolve_references
  setup:
    - name: prepare_workspace
    - name: materialize_runtime_scripts
  factory:
    - name: render_simulation_inputs
    - name: submit_simulation
    - name: run_simulation
    - name: extract_results
    - name: build_report_products
    - name: validate_products
  finalization:
    - name: inventory_outputs
    - name: assemble_manifest
    - name: verify_manifest
```

For MVP compatibility, adding `lifecycle_class`, `display_order`, and `operator_visible` to stage records is probably the better first OpenSpec change. It preserves the current evidence model while letting docs and reports filter the meaningful flow.

## Bootstrap separation

`bootstrap-controlled-source` should be explicitly documented as **demo bootstrap**, not as a production factory stage. In the real system, external controlled repositories already exist and are governed independently.

Recommended policy:

- Bootstrap is allowed to create/tag the synthetic sibling repo for local demo convenience.
- Bootstrap is not part of the ordinary run manifest `stages` list.
- If recorded at all, bootstrap belongs under a separate `demo_setup` or `bootstrap` section.
- Production-shaped runs should begin at admission/preflight, not bootstrap.

This avoids teaching junior engineers that the factory owns upstream source creation. The factory should resolve and verify controlled sources, not pretend to be the source-control nursery.

## Demo validation separation

`manifest-smoke` and similar checks should be treated as finalization/verification, not core workflow stages. They validate the receipt; they do not produce the domain artifact.

Recommended policy:

- Keep `manifest-smoke` as a Make target and CI/operator check.
- Record its result under `validations` or `finalization`, not as a core factory stage.
- Documentation should describe it as "verify the manifest" rather than "run a workflow stage."

Likewise `inventory-pre` and `inventory-post` are evidence collection. They may be first-class evidence events, but they are not core factory transformations.

## Jinja-rendered consumed input placement

The proposed real-system feature — a simulation input rendered from a Jinja template using two externally Git-managed reference files — should influence the refactor. That rendered file is generated, but it is also the exact consumed input. It should be represented as a core factory artifact, not disposable workflow output.

Recommended classification:

| Operation | Lifecycle class |
|---|---|
| Resolve external Git references | `admission` |
| Verify templates/references are controlled | `admission` |
| Render Jinja input | `factory` |
| Copy/render final file under `sim-run-root/input/` | part of `factory` output |
| Hash and inventory rendered file | evidence attached to factory stage |
| Archive rendered input on freeze | `finalization` |

This provides a natural boundary for a future `render_simulation_inputs` or `prepare_simulation_inputs` stage.

## Proposed OpenSpec change scope

A dedicated change could be named `separate-run-lifecycle-from-factory-stages`.

Suggested requirements:

1. Add lifecycle classes for stage declarations and stage attempt evidence.
2. Separate demo bootstrap from ordinary run execution in docs and config semantics.
3. Identify the small operator-facing factory flow in README/handoff docs.
4. Keep granular Make targets for debugging but avoid presenting every target as a core stage.
5. Reclassify `inventory_*`, `manifest`, and `manifest_smoke` as evidence/finalization events.
6. Prepare naming/config structure for future Jinja-rendered simulation input stages.
7. Update tests to assert lifecycle classification appears in stage evidence or manifest output.
8. Update README diagram/text to distinguish factory flow from support/evidence flow.

## Acceptance criteria idea

A useful implementation-agent acceptance set:

- The README contains a concise conceptual factory flow with no more than roughly five to seven operator-visible stages.
- `configs/run.synthetic.yaml` or derived manifest records distinguish lifecycle classes.
- The manifest still preserves detailed evidence for support/finalization events.
- Bootstrap is not represented as an ordinary factory stage.
- Manifest verification is documented as finalization/QA, not as a domain stage.
- Existing `make check` remains green.
