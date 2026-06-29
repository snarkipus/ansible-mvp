## Authority and Source-of-Truth Status

This design is the authoritative, comprehensive source of truth for the `scaffold-runnable-provenance-mvp` OpenSpec change. It incorporates the durable requirements from `docs/provenance_first_mvp_concept_spec.md`, the accepted OpenSpec proposal and tasks, and the implementation choices present in the runnable MVP scaffold.

The original concept spec remains useful background and history. It explains the broader production motivation, possible future RHEL/LSF deployment shape, and follow-on decision areas. When this OpenSpec change and the concept spec differ, this design takes precedence for the implemented local MVP because it reflects the final scaffold, current command names, evidence filenames, and scoped deviations.

This document is intentionally detailed enough for future agents and maintainers to reconcile the implementation without rereading the full concept spec. It should be kept in sync with the implemented scaffold whenever the change is revised.

## Context

The repository began with concept documentation and OpenCode/OpenSpec tooling, not an executable scaffold. The implemented MVP now demonstrates a provenance wrapper around an existing simulation-style workflow rather than replacing that workflow with a new orchestrator or data platform.

The synthetic implementation runs locally on Ubuntu/WSL and models two Git repositories: this provenance wrapper repo and a sibling `../controlled-source-demo` repo containing controlled synthetic scripts and fixture inputs. On Windows hosts, operators should run commands inside Ubuntu/WSL rather than native PowerShell or CMD because the MVP assumes Linux tooling, Unix-style paths, `bash`, `make`, and Ansible. Generated run artifacts remain outside Git under `runs/{run_id}/`.

Python helper code is provenance-critical: it decides what is controlled, what was run, what was produced, what passed validation, and what the manifest says. The scaffold therefore uses explicit Python project tooling from the start: `uv` for environment/dependency execution, `ruff` for linting/formatting, `mypy` for static type checking, and `pytest` for tests.

## Goals / Non-Goals

**Goals:**

- Provide a runnable local scaffold using Ansible as the outer harness, Make as the stage runner, and Python helpers for provenance operations.
- Provide Python tooling with repeatable `uv` commands, `ruff` lint/format checks, and `mypy` type checks for the helper package.
- Bootstrap a clean, tagged `../controlled-source-demo` repository for synthetic controlled scripts and inputs.
- Enforce a Git-controlled source gate before running workflow stages.
- Preserve the simulation contract under `runs/{run_id}/sim-run-root/` while writing evidence and derived products under `runs/{run_id}/provenance/`.
- Emit a `manifest.yaml` that connects repositories, controlled scripts, input materialization, stage execution, logs, raw outputs, derived products, validations, and hashes.
- Include smoke tests that prove the happy path and key provenance failure modes.
- Provide a practical handoff guide that teaches junior engineers how to run the MVP, inspect the manifest, understand extension points, and avoid violating provenance rules.

**Non-Goals:**

- Production HPC deployment or real LSF integration.
- DVC, artifact vaulting, data lake/lakehouse design, Parquet/DuckDB/Polars production paths, or enterprise cataloging.
- Full schema/type validation beyond simple shape checks and manifest smoke validation.
- Replacing legacy extraction/reporting logic with a new analytics architecture.
- Storing generated CSV/XLSX/PPT/report outputs in Git.
- Full Excel, Tableau, or manual-report governance.

## Final Implemented Architecture

The MVP implements the concept's wrapper pattern as a thin, testable local stack:

```text
Ansible playbook prepares and supervises the run
        ↓
Makefile exposes the local stage contract
        ↓
Python provenance CLI commands perform preflight, workspace, inventory,
hashing, validation, scheduler metadata, stage execution, reports, and manifest work
        ↓
Git-controlled scripts from ../controlled-source-demo emulate simulation and extraction
        ↓
runs/{run_id}/provenance/ stores evidence, products, validations, and manifest.yaml
```

Ansible is deliberately thin. `ansible/playbooks/run_synthetic_workflow.yml` validates required variables and the wrapper Makefile, then invokes the configured Make targets in `ansible/inventory/group_vars/all.yml`. It does not become a DAG engine or the provenance authority.

Make is the stable local stage contract. Operators can run the full workflow through Ansible or debug individual targets, but they should keep the same `RUN_ID`, `CONTROLLED_SOURCE_REPO`, and `CONTROLLED_SOURCE_REF` values and must not bypass `make preflight`.

Python helpers under `src/provenance/` own the structured provenance behavior. The package includes focused modules for Git state, preflight, workspace creation, inventory, hashing, scheduler metadata, stage execution, report generation, validation, and manifest assembly. The `provenance` CLI exposed through `uv run provenance ...` is what Make calls.

Controlled synthetic workflow scripts and fixture inputs live in the sibling `../controlled-source-demo` repository, not in the run directory. `sim-run-root/procs/run-script.sh` is materialized from controlled source for each run.

## Repository Boundaries

The implemented repository model is:

```text
workspace/
├── ansible-mvp/              # this repo: OpenSpec, Ansible, Make, Python helpers, tests, docs
└── controlled-source-demo/   # bootstrapped Git repo with synthetic inputs/scripts
```

This wrapper repo contains the orchestration harness, configuration, helper package, tests, templates for bootstrapping the demo controlled source repo, and documentation. It also contains ignored `runs/` output roots with only `runs/.gitkeep` tracked.

The sibling controlled-source repo is part of the synthetic demo boundary. It is created or verified by `make bootstrap-controlled-source`; it is not vendored into this repo. The expected controlled source tag is `controlled-source-demo-v0.1.0`.

## Controlled Source and Bootstrap Contract

`make bootstrap-controlled-source` invokes `scripts/bootstrap_controlled_source.sh` and creates or verifies `../controlled-source-demo`.

The bootstrap contract is strict:

- The target path must be absent or be the root of a Git worktree.
- An existing controlled source worktree must be clean.
- The expected controlled files must exist, be tracked, match the bootstrap templates, and executable scripts must be tracked executable.
- The expected tag `controlled-source-demo-v0.1.0` must exist and point at the current commit.

The controlled source repo contains these fixture inputs and scripts:

```text
controlled-source-demo/
├── fixtures/controlled_inputs/
│   ├── dirA/ex1.dat, ex2.dat, ex3.dat
│   ├── dirB/ex1.dat, ex2.dat, ex3.dat
│   └── dirC/ex1.dat, ex2.dat, ex3.dat
├── procs/run-script.sh
└── scripts/
    ├── synthetic_sim_engine.sh
    ├── extract_required.pl
    └── ad_hoc_extract.py
```

The configured controlled scripts are declared in `configs/run.synthetic.yaml` as `run_script`, `synthetic_sim_engine`, `extract_required`, and `ad_hoc_extract`. Workflow stage commands must reference only approved repo-relative command paths from this configuration.

## Canonical Run Layout

Each run creates an outer workspace under `runs/{run_id}/` with the simulation runtime root and the provenance sidecar as siblings:

```text
runs/{run_id}/
├── sim-run-root/
│   ├── input/
│   │   ├── dirA/ex1.dat, ex2.dat, ex3.dat
│   │   ├── dirB/ex1.dat, ex2.dat, ex3.dat
│   │   └── dirC/ex1.dat, ex2.dat, ex3.dat
│   ├── lists/
│   │   └── dirC/sim-out.dat
│   ├── files/
│   │   ├── dirA/
│   │   ├── dirB/
│   │   └── dirC/
│   └── procs/run-script.sh
└── provenance/
    ├── manifest.yaml
    ├── preflight.json
    ├── logs/
    ├── inventories/
    ├── scheduler/submission.yaml
    ├── validations/
    │   ├── required_extract.json
    │   └── manifest_smoke.json
    └── products/
        ├── extracted/
        │   ├── required.csv
        │   └── ad_hoc.csv
        └── reports/
            ├── summary.xlsx
            ├── chart.png
            └── briefing.pptx
```

`sim-run-root/` preserves the existing simulation runtime contract. The simulation engine can remain unaware of the provenance wrapper. `provenance/` is the wrapper-owned evidence and derived-products contract.

The concept spec described raw and supplementary outputs under multiple `dirA`/`dirB`/`dirC` areas. The implemented MVP intentionally narrows the first runnable proof to one canonical synthetic raw output: `sim-run-root/lists/dirC/sim-out.dat`. The repeated directory-name problem is still exercised because artifacts are identified by full relative path plus `sim_area` and `logical_group`, not by leaf directory alone.

## Directory and Artifact Identity

The repeated `dirA`, `dirB`, and `dirC` folder names are intentional. Tools, inventories, manifests, and future extensions must never identify artifacts only by leaf directory name.

Simulation artifacts should use:

- `relative_path`, such as `sim-run-root/input/dirA/ex1.dat`.
- `sim_area`, such as `input`, `lists`, `files`, or `procs`.
- `logical_group`, such as `dirA`, `dirB`, or `dirC` when applicable.
- `role`, such as `simulation_input`, `runtime_invocation_script`, or `raw_delimited_output`.

Derived products should use:

- `relative_path`, such as `provenance/products/extracted/required.csv`.
- `product_area`, such as `extracted` or `reports`.
- `role`, such as `extracted_csv`, `excel_report`, `figure`, or `ppt_report`.

Generated analytical and reporting artifacts must not be placed inside `sim-run-root/`.

## Implemented Stage Flow and Commands

The expected bootstrap command is:

```bash
make bootstrap-controlled-source
```

The expected full run command is:

```bash
ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
  -i ansible/inventory/localhost.ini \
  -e run_id=demo_001 \
  -e controlled_source_repo=../controlled-source-demo \
  -e controlled_source_ref=controlled-source-demo-v0.1.0
```

The implemented Make targets are:

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
format
lint
typecheck
test
check
clean
```

The Ansible playbook invokes these workflow targets in order: `preflight`, `prepare-workspace`, `materialize-inputs`, `materialize-procs`, `submit-mock-lsf`, `run-simulation`, `extract-required`, `extract-ad-hoc`, `build-reports`, `inventory-pre`, `inventory-post`, `validate`, `manifest`, and `manifest-smoke`.

Important stage outputs include:

- `provenance/preflight.json` from the hard entrance gate.
- `provenance/inventories/materialized_inputs.json` and `materialized_runtime_scripts.json` from materialization.
- `provenance/scheduler/submission.yaml` from mock LSF submission.
- `provenance/logs/*.stage.json` and `provenance/logs/*.stdout.log` / `*.stderr.log` from executed stages.
- `provenance/products/extracted/required.csv` and `ad_hoc.csv` from controlled extractors.
- `provenance/products/reports/summary.xlsx`, `chart.png`, and `briefing.pptx` from report generation.
- `provenance/inventories/pre_run_inputs.json`, `pre_run_controlled_scripts.json`, `post_run_raw_outputs.json`, and `post_run_derived_products.json` from inventories.
- `provenance/validations/required_extract.json` and `manifest_smoke.json` from validation.
- `provenance/manifest.yaml` from manifest assembly.

Each attempted execution should use a fresh `run_id`. Failed or partial runs are intentionally inspectable through the existing `runs/{run_id}/` tree and provenance logs, but the MVP does not define safe resume behavior, retry attempt history, or manifest merge semantics. After correcting a failure, operators should start a new run with a new `run_id` unless future resume semantics are explicitly implemented.

## Preflight Hard-Gate Semantics

Preflight is a hard gate, not a warning collector. The workflow must fail before execution when provenance-critical source identity cannot be proven.

The controlled source repository is checked strictly:

- Path exists.
- Path is a Git worktree.
- Requested ref/tag/commit resolves.
- Worktree is fully clean.
- Required controlled scripts exist.
- Required controlled scripts are tracked by Git.
- Required executable scripts are executable.
- Required controlled scripts are not dirty.

The wrapper repository is checked selectively:

- Path is a Git worktree.
- Configured provenance-critical wrapper paths are tracked and clean.
- Generated ignored outputs under `runs/` do not make the wrapper fail.
- Unrelated planning or documentation edits do not make the run fail unless they are part of configured controlled execution paths.

This selective wrapper policy is implemented through `repositories.wrapper.clean_policy: configured_paths_only` and `repositories.wrapper.controlled_paths` in `configs/run.synthetic.yaml`. It preserves the concept's controlled-source gate while avoiding false failures from generated outputs and unrelated local edits.

Stage command validation is configuration-driven. Each stage declares a command kind, approved command path, working directory, expected controlled scripts where relevant, inputs, and outputs. Preflight validates that stage commands map to approved repo-relative paths and do not run arbitrary uncontrolled scripts.

Hashes are supporting evidence, not a substitute for Git control. The MVP deliberately does not support a `git_present: false` or hash-only fallback for workflow scripts.

## Input and Runtime Script Materialization

The synthetic MVP copies fixture inputs from the controlled source repo into `sim-run-root/input/{dirA,dirB,dirC}/`. The implemented materialization mode is `copy_from_controlled_source`.

The runtime invocation script at `sim-run-root/procs/run-script.sh` is never hand-authored inside a run directory. It is copied from `../controlled-source-demo/procs/run-script.sh` and recorded as a runtime script derived from controlled source.

The concept spec allows future production materialization modes such as copied, symlinked, referenced-only, generated, and copied-from-Git-controlled-source. The implemented MVP uses the controlled-copy path for synthetic inputs and runtime scripts; future modes should be added explicitly to configuration and manifest records rather than inferred.

## Inventory, Hashing, Validation, and Scheduler Metadata

Inventories capture pre-run inputs, pre-run controlled scripts, post-run raw outputs, and post-run derived products under `provenance/inventories/`. Inventory records include relative paths, size, mtime, role metadata, and simulation or product area metadata.

The MVP uses SHA-256. It hashes small synthetic artifacts including scripts, inputs, raw output, extracted CSVs, and generated reports. Production-scale large-output hashing is intentionally deferred; the configured hash policy records `large_artifact_policy: deferred_for_production`.

Validation is intentionally smoke-level. `configs/expected_shape.required_extract.yaml` defines the required CSV expectations, and `make validate` writes `provenance/validations/required_extract.json`. The checks cover existence, non-empty content, expected column count, expected minimum row count, and expected headers. Full schema/type validation is out of scope.

Scheduler behavior is mocked. `make submit-mock-lsf` writes `provenance/scheduler/submission.yaml` and no real `bsub`, `bjobs`, `bhist`, or `bacct` tools are required. Future real-LSF integration may add submit mode or inside-job mode, but the local MVP only implements mock LSF metadata.

## Products and Reports

The synthetic simulation produces one raw output at `sim-run-root/lists/dirC/sim-out.dat`.

The required extractor is an opaque controlled Perl script that writes `provenance/products/extracted/required.csv`. The ad hoc extractor is an opaque controlled Python script that writes `provenance/products/extracted/ad_hoc.csv`.

Report generation writes concrete derived products under `provenance/products/reports/`: `summary.xlsx`, `chart.png`, and `briefing.pptx`. These products are minimal, but they prove that downstream report products are represented as derived products outside the simulation root and linked back through the manifest.

Generated CSV/XLSX/PPTX/PNG/report artifacts are run outputs, not source. They remain ignored under `runs/` and must not be committed.

## Manifest Contract

`runs/{run_id}/provenance/manifest.yaml` is the main MVP deliverable. It must tell the complete synthetic run story from controlled source and inputs through raw outputs, extracted products, generated reports, validation, and hash status.

The implemented manifest version is `0.1`. Required top-level sections are:

```yaml
manifest_version: "0.1"
run: {}
repositories: []
simulation_layout: {}
controlled_source_gate: {}
scheduler: {}
inputs: []
runtime_scripts: []
stages: []
raw_simulation_outputs: []
derived_products: []
validations: []
logs: []
hash_policy: {}
notes: []
```

The manifest smoke validator checks for required sections and key values, including run ID, repository state, resolved commits, layout paths, gate status, scheduler mode, non-empty evidence lists, validation statuses, logs, hash algorithm, and notes. This is intentionally not a formal schema. Full JSON Schema, Pydantic, Pandera, or Great Expectations modeling is deferred until the provenance spine is proven.

The manifest should connect:

- Wrapper and controlled-source repository state, requested refs, resolved commits, branch/describe output, worktree status, tracked script paths, blob IDs, executable modes, and SHA-256 hashes.
- Controlled source gate results from `preflight.json`.
- Simulation layout and canonical raw output path.
- Input and runtime script materialization records.
- Mock scheduler metadata.
- Stage commands, working directories, status, return codes, logs, inputs, outputs, and controlled scripts.
- Raw simulation output inventory.
- Derived product inventory.
- Validation evidence and pass/fail status.
- Hash policy and hash status.
- Notes that clarify local synthetic scope and product separation.

## Tests and Quality Gates

The implemented quality gate is:

```bash
make check
```

It runs, in order:

```text
uv run ruff format --check src/provenance tests
uv run ruff check src/provenance tests
uv run mypy
uv run pytest
```

The test suite covers Git state capture, tracked script detection, wrapper controlled path detection, SHA-256 hashing, inventory metadata, CSV shape validation, manifest smoke validation, the clean synthetic run, dirty controlled source failure, dirty wrapper controlled path failure, untracked script failure, uncontrolled stage command failure, missing ref failure, absence of real LSF tools, manifest generation, exact report product generation, product separation from `sim-run-root/`, and required CSV validation.

Documentation-only changes to this design do not always require `make check`. They must run OpenSpec validation and bead lint; `make check` should be run when documentation changes make executable command claims that need fresh verification or when code/config changed.

OpenSpec and bead hygiene checks for this change are:

```bash
openspec validate scaffold-runnable-provenance-mvp --type change --strict --json
bd lint --json
```

## Decisions

1. Use Make as the stable local stage contract and Ansible as the operator harness.

   Make targets keep the stage flow executable outside Ansible for focused debugging. Ansible remains responsible for loading variables, checking prerequisites, invoking Make, and surfacing failures, but it does not become a custom DAG engine.

   Alternative considered: implement all orchestration directly in Ansible tasks. That would make local focused runs harder and blur orchestration with stage semantics.

2. Keep controlled workflow scripts in `../controlled-source-demo` and materialize run-local scripts from that repo.

   The sibling repo makes the controlled-source boundary visible and testable. `sim-run-root/procs/run-script.sh` is copied from controlled source for each run instead of being authored under `runs/`.

   Alternative considered: store all synthetic scripts in this repo. That would be simpler but would not prove the two-repo source-control entrance gate described by the concept.

3. Treat preflight as a hard gate, not a warning collector.

   The workflow fails when required repos are missing, refs do not resolve, controlled source is not clean, required scripts are missing/untracked/dirty/non-executable, configured wrapper execution paths are dirty or untracked, or stage command paths are uncontrolled. Hashes are supporting evidence, not a replacement for Git control.

   Alternative considered: allow non-Git script paths with hash-only identity. That conflicts with the MVP thesis and risks becoming a permanent bypass.

4. Keep provenance evidence outside `sim-run-root/`.

   The simulation runtime directory remains recognizable to the existing workflow. Logs, inventories, scheduler metadata, validations, manifests, extracted CSVs, and reports live under `runs/{run_id}/provenance/`.

   Alternative considered: write manifest/log files into `sim-run-root/`. That would pollute the runtime contract and make the wrapper harder to remove or adapt.

5. Implement Python helpers as small testable CLI operations.

   Helper modules handle Git state capture, file inventory, SHA-256 hashing, simple shape validation, scheduler metadata, stage execution, report generation, workspace operations, and manifest assembly. They are callable from Make targets and tests.

   Alternative considered: implement provenance logic in shell. Shell is suitable for bootstrap glue, but YAML/JSON assembly, hashing policy, validation, and testability are clearer in Python.

6. Use smoke-level validation for the MVP.

   The manifest must have required sections and generated CSVs must satisfy simple row/column/header expectations. Formal schemas are deferred until the provenance spine is proven.

   Alternative considered: adopt JSON Schema or Pydantic immediately. That adds tooling and modeling cost before the run story is stable.

7. Use `uv`, `ruff`, and `mypy` as first-class project tooling.

   The scaffold includes `pyproject.toml` and `uv.lock`. Make targets call Python tools through `uv run`, and the quality gate order is `ruff format --check`, `ruff check`, `mypy`, then `pytest`.

   Alternative considered: use bare `pip` and untyped Python. That would reduce setup files but make provenance helpers easier to drift and harder to verify as the manifest contract grows.

8. Enforce controlled source cleanliness strictly and wrapper repo cleanliness selectively.

   The sibling controlled source repository must be fully clean before a run. This provenance wrapper repo must be a Git worktree, and configured tracked executable/config paths in the wrapper must be clean and tracked. Generated outputs under ignored paths such as `runs/` must not make a run fail.

   Alternative considered: require the entire wrapper repo to be clean. That is conceptually simple, but local runs intentionally create ignored output and developer workflows may have unrelated planning edits. The MVP still ensures all code/config participating in execution is tracked and clean.

9. Require concrete generated report artifacts for the synthetic acceptance path.

   The first MVP generates `summary.xlsx`, `chart.png`, and `briefing.pptx` under `provenance/products/reports/`. These artifacts are minimal, but they prove downstream report products are represented as derived products outside the simulation root.

   Alternative considered: defer report generation or use placeholder text files. That would weaken the acceptance path described in the concept and leave CSV-to-report provenance unproven.

10. Declare stage commands in configuration and validate them against controlled script identities.

    Stage configuration lists each stage name, command, working directory, expected controlled scripts, command kind, approved command path, and expected inputs/outputs. Preflight validates these declarations before execution.

    Alternative considered: infer commands only from Make recipes. That is harder to validate before execution and makes uncontrolled script detection less deterministic.

11. Treat the handoff guide as an MVP output, not an afterthought.

    `docs/how_to_use_this_mvp.md` covers setup, bootstrap, running the workflow, reading outputs, reading the manifest, extending stages, adding controlled scripts, adding validations, troubleshooting, and common failure modes.

    Alternative considered: rely on README and inline comments only. That would be less useful for handoff because README describes project intent, while the guide teaches safe operation and extension.

12. Use one canonical synthetic raw output for the first MVP.

    The synthetic simulation writes a single raw output at `runs/{run_id}/sim-run-root/lists/dirC/sim-out.dat`. This keeps the first implementation focused while still exercising the repeated directory-name problem because the artifact is identified by full relative path, `sim_area: lists`, and `logical_group: dirC`.

    Alternative considered: generate raw and supplementary outputs under every `dirA`/`dirB`/`dirC` area. That better mirrors the broader concept but adds unnecessary surface area for the first runnable proof.

## Known Deviations from the Original Concept Spec

- The concept spec listed YAML evidence filenames in several examples; the implementation uses JSON for many evidence files: `preflight.json`, inventory JSON files, stage JSON files, `required_extract.json`, and `manifest_smoke.json`. The final manifest remains YAML.
- The concept spec showed possible `ansible.log` and `make.log` wrapper logs. The implementation captures per-stage evidence and stdout/stderr logs under `provenance/logs/`; Ansible itself invokes the Make contract without writing a separate wrapper log file.
- The concept spec described raw and supplementary outputs under multiple simulation areas. The first implemented MVP uses one canonical raw output at `sim-run-root/lists/dirC/sim-out.dat` and keeps empty canonical directories for the broader shape.
- The concept spec discussed multiple materialization modes. The implemented synthetic path uses copy-from-controlled-source for fixture inputs and runtime scripts; future modes are deferred.
- The concept spec allowed a simple `requirements.txt`-style project in examples. The implementation uses `pyproject.toml` and `uv.lock` as the authoritative Python environment contract.
- The concept spec discussed future large-file hash skip behavior. The synthetic implementation hashes small local artifacts and records production large-file policy as deferred.

## Deferred Production Scope and Follow-On Decisions

The MVP intentionally defers production concerns until the provenance spine is proven:

- Real LSF integration, including `bsub`, `bjobs`, `bhist`, `bacct`, polling, resource usage, and inside-job metadata.
- Failed-run resume semantics, including persisted attempt history, safe stage retry behavior, and manifest handling for partial or retried runs.
- Production simulation layout confirmation beyond the simplified canonical shape.
- Actual production repository boundaries and whether production runs require immutable commit hashes rather than tags.
- Production input materialization policy, including symlinks, referenced-only inputs, external large datasets, and allowed staging behavior.
- Large raw-output hash policy, partial hashes, chunk manifests, parallel hashing, or scheduled hash jobs.
- Long-term artifact archival, vaulting, cataloging, promotion, formal release state, and generated product governance.
- Excel/manual transformation controls and Tableau-specific inventory behavior.
- Formal schema/type validation and any future adoption of Pydantic, Pandera, Great Expectations, JSON Schema, or similar tools.
- Parquet/DuckDB/Polars benchmarking or production modernization.

## Risks / Trade-offs

- First slice may become too broad -> Keep report generation minimal and prioritize the manifest spine, controlled-source gate, and smoke tests.
- Development runs may make the wrapper repo dirty -> Ignore generated `runs/` artifacts, require controlled source to be fully clean, and enforce tracked/clean status for wrapper code/config that participates in execution.
- Ansible and Make responsibilities may overlap -> Keep Ansible orchestration thin and Make targets explicit; provenance facts come from helper outputs and manifest assembly.
- Two-repo bootstrap may be brittle -> Make `bootstrap-controlled-source` idempotent for an existing clean demo repo and fail clearly when an incompatible repo exists.
- Hashing everything can become expensive in production -> The MVP uses SHA-256 on small synthetic files and records large-file policy as deferred production behavior.
- Generated report dependencies can distract from provenance -> Keep report contents minimal but generate the expected `summary.xlsx`, `chart.png`, and `briefing.pptx`; the success criteria remain traceability and manifest completeness.
- Static typing can slow early scripting -> Type the Python helper package because it owns provenance facts, but keep shell/Ansible glue simple and avoid over-modeling with a full schema framework.
- Handoff documentation can become stale -> Keep the guide focused on stable commands, output contracts, extension points, and provenance rules, and verify it during README/documentation review before handoff.
- A single raw output may under-represent production complexity -> Keep the canonical directory layout and full-path artifact identity now, then extend additional raw outputs later without changing the manifest model.

## Migration Plan

This change introduced a new scaffold rather than migrating existing executable code.

1. Add ignored generated-output paths before creating run artifacts.
2. Add `pyproject.toml`, `uv` dependency metadata, `ruff`, `mypy`, configuration, scripts, Python helpers, Ansible playbook, Makefile, tests, and handoff guide.
3. Bootstrap `../controlled-source-demo` with tag `controlled-source-demo-v0.1.0`.
4. Verify the clean run path and failure tests locally.
5. Leave generated run output untracked.

Rollback is ordinary Git revert of scaffold files plus removal of generated local `runs/` and `../controlled-source-demo` if no longer needed.

## Final Verification Approach

The completed MVP scaffold should be verified with:

```bash
make bootstrap-controlled-source
make check
ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
  -i ansible/inventory/localhost.ini \
  -e run_id=final_verification_001 \
  -e controlled_source_repo=../controlled-source-demo \
  -e controlled_source_ref=controlled-source-demo-v0.1.0
openspec validate scaffold-runnable-provenance-mvp --type change --strict --json
bd lint --json
```

For documentation-only updates to this design, the required validation is OpenSpec strict validation and bead lint. `make check` may be skipped when no executable code/config changed and the documentation does not need fresh command verification.

## Open Questions

None for the first implementation slice. Production follow-on decisions are deferred scope, not blockers for this MVP.
