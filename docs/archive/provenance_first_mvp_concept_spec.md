# Provenance-First Engineering Data Pipeline MVP
## Concept Specification and Codex Handoff Document

> **Status: implemented.** This concept has been realized as the runnable MVP
> scaffold in this repository. `README.md` and `docs/how_to_use_this_mvp.md`
> are now authoritative for current behavior; this document is retained as the
> original concept and design intent.

**Purpose:** This document captures the agreed concept for a provenance-first MVP around an existing engineering simulation/data workflow. It is intended as a handoff artifact for Codex or another implementation agent.

**MVP target:** Runnable synthetic reference implementation on Ubuntu/WSL.

**Future production target:** RHEL HPC login nodes for staging, data preparation, extraction, and orchestration; LSF compute nodes for simulation execution.

---

## 1. Executive Summary

The MVP should demonstrate a **provenance wrapper pattern** around an existing simulation-driven engineering data workflow.

The goal is not to replace the simulation engine, rewrite extractors, adopt a data lake, deploy DVC, introduce a full workflow orchestrator, or convert the organization to Parquet/DuckDB/Polars. The goal is to establish a **repeatable provenance spine** that records which inputs, scripts, execution context, raw outputs, extraction steps, generated artifacts, and validations contributed to a given analytical/reporting product.

Key decisions:

- Use **Ansible** as the outer operator harness.
- Use **Make** as the lightweight local stage/dependency definition.
- Use a small **Python provenance helper package** for inventory, hashing, validation, Git capture, and manifest generation.
- Use a **synthetic controlled-source Git repo** as a forcing function.
- Require controlled source/scripts to be **Git-controlled at a clean resolved commit** before the run can proceed.
- Preserve the canonical simulation runtime layout exactly under `sim-run-root/`.
- Place provenance evidence and downstream generated analytical/reporting products outside the simulation root under `provenance/`.
- Mock LSF behavior for the MVP, but document the future integration shape.

---

## 2. Problem Context

The current workflow processes analytical/parametric data generated from simulations or technical workflows.

Representative data characteristics:

- File sizes: roughly 100 MB to 10 GB.
- Row counts: up to roughly 1 million rows.
- Column counts: up to roughly 300 columns.
- Data shape: mostly static and reasonably clean.
- Data type: engineering/analytical/parametric data, not conventional business/BI data.
- Outputs include time-series or indexed data plus mixed string key/value parameters.
- Downstream analyses include summary statistics, reductions, correlations, plots, figures, and briefing artifacts.

Current environment:

- Windows workstation-class PCs.
- RHEL Linux HPC environment.
- LSF scheduler.
- Air-gapped/proprietary constraints.
- Restrictive tooling approval process.
- Git and Ansible are available or intended to be available.
- MATLAB and Tableau licenses exist.
- Excel, PowerPoint, and Word are heavily used for analysis/reporting outputs.

Current workflow problems:

- CSV and Excel are often treated as the de facto authority.
- Extraction scripts are mixed, ad hoc, and not consistently governed.
- Inputs may be copied, symlinked, or merely referenced without a clear policy.
- Runtime provenance is largely implicit in folder naming and analyst knowledge.
- Generated CSV/XLSX/PPT products cannot reliably be traced back to exact inputs, scripts, execution context, and raw outputs.
- There is no durable machine-readable manifest describing a run.

---

## 3. Scope Boundary

### 3.1 In Scope for MVP

The MVP must demonstrate:

- Synthetic end-to-end workflow execution on WSL/Ubuntu.
- Ansible-based run orchestration.
- Makefile-based stage definition.
- Canonical simulation run directory creation.
- Git-controlled source/script preflight gate.
- Mock LSF job submission.
- Synthetic simulation output generation.
- Opaque required extraction step, represented by Perl.
- Opaque ad hoc extraction step, represented by Python.
- Generated CSV intermediate products.
- Generated XLSX/PPTX/reporting artifacts.
- Provenance-controlled output area outside the sim root.
- Pre-run and post-run file inventories.
- Practical SHA-256 hashing policy.
- Basic row/column/header-count validation stubs.
- Logs for each major stage.
- A machine-readable `manifest.yaml`.
- Acceptance tests/smoke tests proving the pattern runs.

### 3.2 Explicitly Out of Scope for MVP

Do not expand the MVP into:

- DVC or a DVC replacement.
- Data lake/lakehouse architecture.
- Enterprise data cataloging.
- Long-term raw-output archival or vaulting.
- Parquet warehouse design.
- DuckDB/Polars production pipeline.
- Full schema/type validation.
- Full DAG/workflow platform such as Airflow, Dagster, Prefect, Snakemake, or Nextflow.
- Full Excel/Tableau replacement.
- Regex extraction refactor.
- Real LSF integration.
- Production deployment on target hardware.
- Git versioning of large generated artifacts.

---

## 4. Core Design Philosophy

The MVP is a **wrapper around the existing workflow**, not a replacement for it.

Conceptual flow:

```text
Ansible prepares and supervises the run
        ↓
Make defines the local stage flow
        ↓
Synthetic scripts emulate simulation/extraction/reporting
        ↓
Python provenance helpers inventory/hash/validate
        ↓
manifest.yaml tells the complete run story
```

The most important deliverable is the **manifest and supporting provenance evidence**, not the synthetic data itself.

The MVP should answer this question for every generated artifact:

> What Git-controlled source/scripts, inputs, materialization choices, commands, execution context, raw outputs, extraction steps, validations, and intermediate products contributed to this artifact?

---

## 5. Canonical Simulation Run Shape

The real simulation engine expects a canonical shape similar to:

```text
sim-run-root/
├── files
│   ├── dirA
│   ├── dirB
│   └── dirC
├── input
│   ├── dirA
│   │   ├── ex1.dat
│   │   ├── ex2.dat
│   │   └── ex3.dat
│   ├── dirB
│   │   ├── ex1.dat
│   │   ├── ex2.dat
│   │   └── ex3.dat
│   └── dirC
│       ├── ex1.dat
│       ├── ex2.dat
│       └── ex3.dat
├── lists
│   ├── dirA
│   ├── dirB
│   └── dirC
└── procs
    └── run-script.sh
```

Directory semantics:

- `input/`: controlled inputs and simulation inputs.
- `lists/`: primary simulation outputs, including delimited and flat output.
- `files/`: supplementary output.
- `procs/`: runtime invocation scripts; convention rather than hard requirement.
- `dirA`, `dirB`, and `dirC` intentionally repeat under nested directories and reflect the real runtime pattern.

The synthetic MVP must honor this shape inside `sim-run-root/`.

---

## 6. Provenance Sidecar Layout

The MVP should not place provenance files or generated analytical/reporting products directly into the simulation runtime root.

Use a sibling `provenance/` directory under each run:

```text
runs/{run_id}/
├── sim-run-root/
│   ├── files/
│   ├── input/
│   ├── lists/
│   └── procs/
└── provenance/
    ├── manifest.yaml
    ├── run_config.yaml
    ├── logs/
    ├── inventories/
    ├── scheduler/
    ├── validations/
    └── products/
        ├── extracted/
        └── reports/
```

Rationale:

- `sim-run-root/` remains the simulation runtime contract.
- `provenance/` becomes the wrapper-owned evidence and derived-products contract.
- The simulation engine can remain unaware of the provenance system.
- Generated CSV/XLSX/PPT products are post-simulation analytical/reporting products, not native simulation outputs.

Recommended full synthetic layout:

```text
runs/demo_001/
├── sim-run-root/
│   ├── files/
│   │   ├── dirA/
│   │   ├── dirB/
│   │   └── dirC/
│   ├── input/
│   │   ├── dirA/
│   │   │   ├── ex1.dat
│   │   │   ├── ex2.dat
│   │   │   └── ex3.dat
│   │   ├── dirB/
│   │   │   ├── ex1.dat
│   │   │   ├── ex2.dat
│   │   │   └── ex3.dat
│   │   └── dirC/
│   │       ├── ex1.dat
│   │       ├── ex2.dat
│   │       └── ex3.dat
│   ├── lists/
│   │   ├── dirA/
│   │   ├── dirB/
│   │   └── dirC/
│   └── procs/
│       └── run-script.sh
└── provenance/
    ├── manifest.yaml
    ├── run_config.yaml
    ├── logs/
    │   ├── ansible.log
    │   ├── make.log
    │   ├── mock_lsf_submit.log
    │   ├── simulation.log
    │   ├── extract_required.log
    │   ├── extract_ad_hoc.log
    │   └── report_generation.log
    ├── inventories/
    │   ├── pre_run_input_inventory.yaml
    │   ├── post_run_output_inventory.yaml
    │   └── controlled_script_inventory.yaml
    ├── scheduler/
    │   ├── job_submit.sh
    │   └── mock_lsf_submission.yaml
    ├── validations/
    │   └── required_extract_shape.yaml
    └── products/
        ├── extracted/
        │   ├── required.csv
        │   └── ad_hoc.csv
        └── reports/
            ├── summary.xlsx
            ├── chart.png
            └── briefing.pptx
```

---

## 7. Directory Identity and Repeated Names

Because `dirA`, `dirB`, and `dirC` intentionally repeat under `input/`, `lists/`, and `files/`, the manifest must never identify artifacts by leaf directory alone.

Bad representation:

```yaml
case: dirA
path: dirA/ex1.dat
```

Better representation:

```yaml
artifact:
  logical_group: dirA
  sim_area: input
  relative_path: sim-run-root/input/dirA/ex1.dat
  absolute_path: runs/demo_001/sim-run-root/input/dirA/ex1.dat
```

Recommended concept:

- Treat `dirA`, `dirB`, `dirC` as `logical_group`.
- Treat `input`, `lists`, `files`, `procs` as `sim_area`.
- Treat provenance product areas separately as `product_area`.

Example:

```yaml
simulation_layout:
  root: runs/demo_001/sim-run-root
  areas:
    input: input
    output_lists: lists
    supplementary_output: files
    runtime_procs: procs
  logical_groups:
    - dirA
    - dirB
    - dirC
```

---

## 8. Git-Controlled Source Entrance Criterion

The MVP should make Git-controlled source/scripts a **hard entrance criterion**.

Reason:

> If mixed Git adoption is provisioned as a fallback, it will likely become a permanent bypass.

Therefore:

> The MVP does not support non-Git controlled source or uncontrolled execution scripts. If a script participates in the workflow, it must resolve to a tracked file in an approved Git repo at a clean commit.

### 8.1 Must Be Git-Controlled

The following must be in Git:

- Simulation wrapper scripts.
- Runtime invocation scripts.
- Controlled Perl extractor.
- Ad hoc Python extraction scripts, even if opaque.
- Makefile.
- Ansible playbooks.
- Python provenance helpers.
- Validation stubs.
- Config templates.
- Schema/expected-shape files.
- Small controlled text inputs, if practical and appropriate.

### 8.2 Not Necessarily Git-Controlled

The following should remain outside Git:

- Large raw simulation outputs.
- Generated CSV/XLSX/PPT artifacts.
- Large external data files.
- Large raw input datasets, unless separately governed.
- Archival/vaulted artifacts, which are out of MVP scope.

### 8.3 Preflight Gate

The Ansible playbook must start with a **Controlled Source Gate**.

The gate verifies:

- Controlled source repo exists.
- Provenance MVP repo exists.
- Required repos are Git worktrees.
- Requested ref/tag/commit resolves.
- Worktrees are clean.
- Required scripts exist.
- Required scripts are tracked by Git.
- Stage commands reference only approved repo-relative script paths.
- No untracked or dirty controlled script participates in the run.

There must be no `git_present: false` fallback for workflow scripts.

File hashes can still be captured, but hashes are supporting evidence, not a substitute for Git control.

---

## 9. Repository Model

The synthetic MVP should use two repos:

```text
workspace/
├── provenance-mvp/              # Ansible, Make, Python provenance helpers
└── controlled-source-demo/       # synthetic sim engine + Perl/Python scripts
```

### 9.1 `provenance-mvp` Repo

Contains:

```text
provenance-mvp/
├── README.md
├── Makefile
├── justfile                         # optional convenience only
├── requirements.txt
├── ansible/
│   ├── inventory/
│   │   └── localhost.ini
│   ├── group_vars/
│   │   └── all.yml
│   └── playbooks/
│       └── run_synthetic_workflow.yml
├── configs/
│   ├── run.synthetic.yaml
│   └── expected_shape.required_extract.yaml
├── scripts/
│   ├── materialize_inputs.sh
│   ├── mock_lsf_submit.sh
│   ├── build_excel_report.py
│   └── build_ppt_report.py
├── src/
│   └── provenance/
│       ├── __init__.py
│       ├── cli.py
│       ├── git_state.py
│       ├── inventory.py
│       ├── hashing.py
│       ├── validation.py
│       ├── manifest.py
│       └── lsf_shape.py
├── templates/
│   ├── manifest_base.yaml.j2
│   └── lsf_job.sh.j2
├── runs/
│   └── .gitkeep
└── tests/
    ├── test_inventory.py
    ├── test_hashing.py
    └── test_manifest_smoke.py
```

### 9.2 `controlled-source-demo` Repo

Contains synthetic controlled source and scripts:

```text
controlled-source-demo/
├── README.md
├── scripts/
│   ├── synthetic_sim_engine.sh
│   ├── extract_required.pl
│   └── ad_hoc_extract.py
├── procs/
│   └── run-script.sh
└── fixtures/
    └── controlled_inputs/
        ├── dirA/
        ├── dirB/
        └── dirC/
```

The setup flow may create and tag this repo:

```text
make bootstrap-controlled-source
```

That command can create `controlled-source-demo`, commit the synthetic scripts, and tag:

```text
controlled-source-demo-v0.1.0
```

---

## 10. Configuration Shape

Recommended synthetic run configuration:

```yaml
run_id: demo_001

paths:
  run_root: runs/demo_001
  sim_run_root: runs/demo_001/sim-run-root
  provenance_root: runs/demo_001/provenance

repos:
  provenance_mvp:
    path: .
    required: true
    required_clean: true

  controlled_source:
    path: ../controlled-source-demo
    required: true
    required_clean: true
    ref: controlled-source-demo-v0.1.0

simulation_layout:
  areas:
    input: input
    lists: lists
    files: files
    procs: procs
  logical_groups:
    - dirA
    - dirB
    - dirC
  examples_per_group:
    - ex1.dat
    - ex2.dat
    - ex3.dat

controlled_scripts:
  run_script:
    repo: controlled_source
    path: procs/run-script.sh
    materialized_to: sim-run-root/procs/run-script.sh

  synthetic_sim_engine:
    repo: controlled_source
    path: scripts/synthetic_sim_engine.sh

  required_extractor:
    repo: controlled_source
    path: scripts/extract_required.pl

  ad_hoc_extractor:
    repo: controlled_source
    path: scripts/ad_hoc_extract.py

hash_policy:
  algorithm: sha256
  default_for_code_and_config: true
  default_for_small_data: true
  large_file_threshold_bytes: 1073741824
  large_file_default: metadata_only
  allow_large_file_hash_override: true
  hash_large_files: false

validation:
  required_extract:
    expected_columns: 6
    expected_min_rows: 1
    expected_headers:
      - logical_group
      - source_file
      - metric_a
      - metric_b
      - metric_c
      - status
```

---

## 11. Input Materialization Policy

The real workflow currently uses a mix of symlinks, copies, and path references. This should be explicitly modeled, not hidden.

Every input artifact should declare its materialization type:

- `copied`
- `symlinked`
- `referenced_only`
- `generated`
- `copied_from_git_controlled_source`

Example:

```yaml
inputs:
  - logical_name: dirA_ex1
    role: simulation_input
    sim_area: input
    logical_group: dirA
    source_path: examples/source_inputs/dirA/ex1.dat
    run_path: sim-run-root/input/dirA/ex1.dat
    materialization: copied
    sha256: sha256:...

  - logical_name: dirB_controlled_ref
    role: controlled_input
    sim_area: input
    logical_group: dirB
    source_path: ../controlled-source-demo/fixtures/controlled_inputs/dirB/ex2.dat
    run_path: sim-run-root/input/dirB/ex2.dat
    materialization: copied_from_git_controlled_source
    source_repo: controlled_source
    source_commit: abc123
    sha256: sha256:...

  - logical_name: external_reference
    role: external_reference
    sim_area: input
    logical_group: dirC
    source_path: /external/reference/location/ex3.dat
    run_path: null
    materialization: referenced_only
    sha256_status: not_materialized
```

Rule:

> Materialization must never be implied. The manifest must explicitly record how each file entered or participated in the run.

---

## 12. Runtime Script Materialization

The runtime invocation script under:

```text
sim-run-root/procs/run-script.sh
```

must not be hand-authored in the run directory.

It should be materialized from the controlled source Git repo:

```yaml
runtime_scripts:
  - logical_name: run_script
    role: runtime_invocation_script
    source_repo: controlled_source
    source_repo_path: procs/run-script.sh
    source_commit: abc123
    materialized_path: sim-run-root/procs/run-script.sh
    materialization: copied_from_git_controlled_source
    sha256: sha256:...
```

This prevents `procs/run-script.sh` from becoming an uncontrolled run-local snowflake.

---

## 13. Hashing Policy

Use SHA-256 for the MVP.

Rationale:

- SHA-256 is conservative, standard, and easy to justify in controlled engineering environments.
- BLAKE3 may be faster, but it is less “boring” from a process/approval standpoint.
- For 10 GB files, always hashing everything may be expensive; use a practical tiered policy.

Recommended behavior:

Always record:

- Path.
- Role.
- Size in bytes.
- Modified time in UTC.
- Materialization.
- Producing stage.
- Consuming stage.

Always hash:

- Scripts.
- Configs.
- Manifests.
- Makefile.
- Ansible playbooks.
- Small inputs.
- Small extracted outputs.

For large raw outputs:

- Record size, mtime, and path by default.
- Record `sha256_status: skipped_large_file`.
- Allow selected runs to enable `hash_large_files: true`.

Synthetic MVP files will be small, so the demo can hash everything while still supporting skip/override logic.

---

## 14. Ansible, Make, and Python Responsibilities

### 14.1 Ansible Responsibilities

Ansible is the outer harness.

It should:

- Load run configuration.
- Verify required tools are available.
- Create run workspace.
- Enforce Git-controlled source gate.
- Template job submission scripts.
- Materialize canonical simulation directory structure.
- Invoke Make targets.
- Capture high-level logs.
- Collect final artifacts.
- Fail fast on preflight violations.

Ansible should not become a complex DAG engine.

### 14.2 Make Responsibilities

Make is the lightweight stage definition.

Suggested targets:

```make
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
clean
```

Make should operate with explicit environment variables:

```text
RUN_ID=demo_001
RUN_ROOT=runs/demo_001
SIM_RUN_ROOT=runs/demo_001/sim-run-root
PROVENANCE_ROOT=runs/demo_001/provenance
CONTROLLED_SOURCE_REPO=../controlled-source-demo
CONTROLLED_SOURCE_REF=controlled-source-demo-v0.1.0
```

### 14.3 Python Provenance Helper Responsibilities

The Python helper package should provide:

- Git state capture.
- File inventory.
- SHA-256 hashing.
- Large-file hash policy handling.
- Basic validation stubs.
- Manifest assembly.
- Optional CLI commands for each provenance operation.
- Smoke validation of the generated manifest.

Suggested CLI shape:

```text
python -m provenance.cli git-state --repo .
python -m provenance.cli inventory --root runs/demo_001/sim-run-root/input --output ...
python -m provenance.cli validate-shape --input required.csv --expected configs/expected_shape.required_extract.yaml
python -m provenance.cli manifest --run-config ... --output runs/demo_001/provenance/manifest.yaml
```

---

## 15. Mock LSF Now, Real LSF Later

The synthetic MVP should emulate LSF but not require `bsub`, `bjobs`, `bhist`, or a real scheduler.

Synthetic scheduler manifest shape:

```yaml
scheduler:
  type: lsf
  mode: mock
  submit_command: scripts/mock_lsf_submit.sh
  job_id: MOCK-demo_001
  submit_host: wsl-ubuntu
  execution_host: wsl-ubuntu
  status: DONE
```

Future production shape:

```yaml
scheduler:
  type: lsf
  mode: submit
  submit_command: bsub < runs/{run_id}/provenance/scheduler/job_submit.sh
  job_id: "123456"
  queue: normal
  project: optional
  requested_resources:
    cores: 16
    memory: 64GB
    walltime: "04:00"
  submit_host: login-node-01
  execution_hosts:
    - compute-node-042
  lsf_commands:
    bsub_stdout: provenance/logs/bsub.out
    bjobs_snapshot: provenance/logs/bjobs.final.txt
    bhist: provenance/logs/bhist.txt
    bacct: provenance/logs/bacct.txt
  status: DONE
```

Future integration modes to provision conceptually:

- `mock`: WSL/local synthetic demo.
- `submit`: login node submits with `bsub` and polls.
- `inside_job`: code runs inside an allocated LSF job and reads `LSB_*` environment variables.

The MVP only needs `mock`.

---

## 16. Stage Contract

Each stage should emit or be represented by a stage record.

Example:

```yaml
stages:
  - name: synthetic_simulation
    type: simulation
    command: sim-run-root/procs/run-script.sh
    cwd: runs/demo_001/sim-run-root
    start_time_utc: "2026-06-28T10:00:00Z"
    end_time_utc: "2026-06-28T10:00:05Z"
    status: success
    return_code: 0
    logs:
      stdout: provenance/logs/simulation.stdout.log
      stderr: provenance/logs/simulation.stderr.log
    controlled_scripts:
      - run_script
      - synthetic_sim_engine
    inputs:
      - sim-run-root/input/dirA/ex1.dat
      - sim-run-root/input/dirB/ex1.dat
    outputs:
      - sim-run-root/lists/dirA/output_delimited.dat
      - sim-run-root/files/dirA/supplemental.txt
```

Required fields:

- Stage name.
- Stage type.
- Command.
- Working directory.
- Start/end timestamps.
- Status.
- Return code.
- Logs.
- Inputs.
- Outputs.
- Controlled scripts used.

---

## 17. Artifact Contract

Each artifact should have enough metadata to distinguish its origin, role, path, and lifecycle.

Example:

```yaml
artifacts:
  - logical_name: dirA_ex1
    role: simulation_input
    sim_area: input
    logical_group: dirA
    relative_path: sim-run-root/input/dirA/ex1.dat
    materialization: copied
    size_bytes: 1234
    mtime_utc: "2026-06-28T10:00:00Z"
    sha256: sha256:...
    produced_by_stage: null
    consumed_by_stages:
      - synthetic_simulation

  - logical_name: required_extract
    role: extracted_csv
    product_area: extracted
    relative_path: provenance/products/extracted/required.csv
    size_bytes: 5678
    mtime_utc: "2026-06-28T10:01:00Z"
    sha256: sha256:...
    produced_by_stage: required_extraction
    consumed_by_stages:
      - report_generation
```

Recommended artifact role categories:

- `simulation_input`
- `controlled_input`
- `runtime_invocation_script`
- `raw_delimited_output`
- `raw_flat_output`
- `supplementary_simulation_output`
- `extracted_csv`
- `excel_report`
- `ppt_report`
- `figure`
- `log`
- `manifest`
- `validation_result`
- `scheduler_metadata`

---

## 18. Product Separation

The manifest must distinguish raw simulation outputs from derived products.

Example:

```yaml
raw_simulation_outputs:
  - logical_name: dirA_primary_output
    sim_area: lists
    logical_group: dirA
    relative_path: sim-run-root/lists/dirA/output_delimited.dat
    role: raw_delimited_output
    produced_by_stage: synthetic_simulation

  - logical_name: dirA_supplementary_output
    sim_area: files
    logical_group: dirA
    relative_path: sim-run-root/files/dirA/supplemental.txt
    role: supplementary_simulation_output
    produced_by_stage: synthetic_simulation

derived_products:
  - logical_name: required_extract
    product_area: extracted
    relative_path: provenance/products/extracted/required.csv
    role: extracted_csv
    produced_by_stage: required_extraction
    source_inputs:
      - sim-run-root/lists/dirA/output_delimited.dat
      - sim-run-root/lists/dirB/output_delimited.dat
      - sim-run-root/lists/dirC/output_delimited.dat

  - logical_name: summary_workbook
    product_area: reports
    relative_path: provenance/products/reports/summary.xlsx
    role: excel_report
    produced_by_stage: report_generation
    source_inputs:
      - provenance/products/extracted/required.csv
```

Rule:

> Generated analytical and reporting artifacts must not be placed inside `sim-run-root/`.

---

## 19. Manifest Requirements

The MVP manifest should be YAML.

JSON Schema or Pydantic validation is not required for MVP, but the manifest should include a version and a smoke validator.

Required top-level sections:

```yaml
manifest_version: "0.1"

run:
  run_id: demo_001
  status: success
  created_at_utc: "..."
  created_by: "..."
  host: "..."
  platform: "ubuntu-wsl"

repositories: {}

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

notes: {}
```

The smoke validator should verify that the manifest contains required top-level sections and non-empty values where appropriate.

Do not over-invest in full schema/type validation for MVP.

---

## 20. Validation Scope

Full schema/type validation is out of scope.

MVP validation should support simple shape checks:

- File exists.
- Non-empty.
- Expected number of columns, if configured.
- Expected minimum row count, if configured.
- Expected header names, if configured.

Example validation output:

```yaml
validations:
  - name: required_extract_shape
    target: provenance/products/extracted/required.csv
    status: passed
    checks:
      exists: true
      non_empty: true
      expected_columns: 6
      actual_columns: 6
      expected_min_rows: 1
      actual_rows: 9
      expected_headers:
        - logical_group
        - source_file
        - metric_a
        - metric_b
        - metric_c
        - status
      actual_headers:
        - logical_group
        - source_file
        - metric_a
        - metric_b
        - metric_c
        - status
```

---

## 21. Synthetic Workflow Behavior

The synthetic demo should perform the following:

1. Bootstrap or verify `controlled-source-demo` Git repo.
2. Verify the `provenance-mvp` repo is clean.
3. Verify the controlled source repo is clean.
4. Verify requested controlled source ref resolves.
5. Create `runs/{run_id}/`.
6. Create `runs/{run_id}/sim-run-root/` using the canonical shape.
7. Create `runs/{run_id}/provenance/`.
8. Materialize synthetic input files into `sim-run-root/input/{dirA,dirB,dirC}/`.
9. Materialize Git-controlled runtime script into `sim-run-root/procs/run-script.sh`.
10. Inventory pre-run inputs and controlled scripts.
11. Mock LSF submission.
12. Execute synthetic simulation via `sim-run-root/procs/run-script.sh`.
13. Write raw outputs to `sim-run-root/lists/{dirA,dirB,dirC}/`.
14. Write supplementary outputs to `sim-run-root/files/{dirA,dirB,dirC}/`.
15. Run required Perl extraction as opaque controlled script.
16. Run ad hoc Python extraction as opaque controlled script.
17. Write CSV products under `provenance/products/extracted/`.
18. Generate XLSX/PPTX/chart products under `provenance/products/reports/`.
19. Inventory post-run outputs.
20. Run shape validation stubs.
21. Generate `manifest.yaml`.
22. Run manifest smoke test.

---

## 22. Suggested Codex Prompt

Use or adapt this prompt for implementation:

```text
Build a runnable WSL-compatible reference implementation of a provenance-first engineering simulation workflow MVP.

The implementation must use:
- Ansible as the outer run harness
- Make as the lightweight local stage definition
- Python provenance helpers for Git state capture, file inventory, hashing, validation, and manifest generation

The implementation must create a synthetic end-to-end demo that preserves this canonical simulation run shape:

sim-run-root/
├── files/{dirA,dirB,dirC}
├── input/{dirA,dirB,dirC}/ex1.dat, ex2.dat, ex3.dat
├── lists/{dirA,dirB,dirC}
└── procs/run-script.sh

Do not place provenance files directly inside sim-run-root.

Create a sibling provenance directory under runs/{run_id}/provenance for manifest, logs, inventories, mock scheduler metadata, validations, extracted CSVs, and generated report products.

Generated analytical/reporting products must live under:
runs/{run_id}/provenance/products/
with:
- extracted/
- reports/

The implementation must include or bootstrap a separate controlled-source-demo Git repository containing:
- synthetic simulation engine script
- runtime run-script.sh
- required Perl extractor
- ad hoc Python extractor
- controlled fixture inputs as needed

The MVP must fail fast unless all controlled source and executable workflow scripts are sourced from Git at a clean resolved commit. Do not implement a non-Git fallback identity for workflow scripts.

The Ansible preflight must verify:
- provenance repo exists and is a Git worktree
- controlled source repo exists and is a Git worktree
- requested controlled source ref/tag/commit resolves
- required worktrees are clean
- required scripts exist
- required scripts are tracked files
- stage commands use only repo-relative controlled script paths

The manifest must record:
- run identity
- simulation layout
- Git state for available repos
- requested refs and resolved commits
- controlled source gate results
- copied/symlinked/referenced/generated input materialization
- synthetic scheduler metadata
- stage commands/status/timestamps/return codes
- script identities and hashes
- raw simulation output inventory from sim-run-root/lists and sim-run-root/files
- derived product inventory from provenance/products
- row/column/header-count validation stubs
- hash policy and hash status for each artifact

Mock LSF behavior for the MVP. Do not require bsub, bjobs, bhist, or real LSF tools.

Provide acceptance tests or smoke tests demonstrating:
- clean run succeeds
- dirty controlled source repo fails preflight
- untracked script fails preflight
- manifest is generated
- generated required.csv passes simple shape validation
```

---

## 23. Acceptance Criteria

A clean demo run should work with commands similar to:

```text
make bootstrap-controlled-source

ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
  -i ansible/inventory/localhost.ini \
  -e run_id=demo_001 \
  -e controlled_source_repo=../controlled-source-demo \
  -e controlled_source_ref=controlled-source-demo-v0.1.0
```

Expected outputs:

```text
runs/demo_001/sim-run-root/input/dirA/ex1.dat
runs/demo_001/sim-run-root/lists/dirA/<synthetic raw output>
runs/demo_001/sim-run-root/files/dirA/<synthetic supplementary output>
runs/demo_001/provenance/products/extracted/required.csv
runs/demo_001/provenance/products/extracted/ad_hoc.csv
runs/demo_001/provenance/products/reports/summary.xlsx
runs/demo_001/provenance/products/reports/chart.png
runs/demo_001/provenance/products/reports/briefing.pptx
runs/demo_001/provenance/manifest.yaml
runs/demo_001/provenance/logs/*.log
runs/demo_001/provenance/inventories/*.yaml
runs/demo_001/provenance/validations/*.yaml
```

Preflight failure cases:

- Controlled source repo missing.
- Controlled source ref does not resolve.
- Controlled source repo dirty.
- Required controlled script is untracked.
- Required controlled script missing.
- Stage command points to uncontrolled local script.
- Provenance MVP repo dirty if configured as `required_clean: true`.

Manifest checks:

- Includes `manifest_version`.
- Includes `run.run_id`.
- Includes repository state and resolved commits.
- Includes canonical simulation layout.
- Includes controlled source gate result.
- Includes scheduler mock metadata.
- Includes input materialization records.
- Includes stage records.
- Includes raw simulation output inventory.
- Includes derived product inventory.
- Includes validation result for `required.csv`.
- Includes hash policy.

---

## 24. Open Design Gaps and Follow-On Decisions

The MVP can proceed with the assumptions above, but these topics should be tracked as open design gaps.

### 24.1 Exact Production Simulation Layout

The canonical shape is known at a simplified level, but the full production layout may include additional conventions, hidden assumptions, generated files, or engine-specific restrictions.

Follow-on decisions:

- Confirm whether extra directories adjacent to `sim-run-root/` are always safe.
- Confirm whether `sim-run-root/` must remain pristine except for expected runtime contents.
- Confirm whether production run roots already have naming conventions the wrapper must preserve.

### 24.2 Production LSF Integration

MVP uses mock LSF only.

Follow-on decisions:

- Choose whether production will run in `submit` mode, `inside_job` mode, or both.
- Decide what LSF artifacts must be captured: `bsub` stdout, job ID, queue, project, requested resources, execution host(s), `bjobs`, `bhist`, `bacct`, resource usage, exit codes.
- Decide polling/timeout behavior.

### 24.3 Controlled Source Repo Strategy

MVP assumes a separate controlled source repo.

Follow-on decisions:

- Determine actual repo boundaries for simulation source, controlled library scripts, extraction scripts, and provenance wrapper.
- Determine whether tags or immutable commit hashes are required for production runs.
- Decide whether dirty provenance repo should fail or warn.

### 24.4 Input Materialization Policy

MVP explicitly supports copied, symlinked, referenced-only, generated, and copied-from-Git materialization.

Follow-on decisions:

- Decide which materialization types are allowed in production.
- Decide whether symlinks to controlled libraries are acceptable.
- Decide whether referenced-only inputs are allowed for controlled workflows.
- Decide whether copied arbitrary inputs require hashing.
- Decide whether inputs must be staged into run root or may remain external.

### 24.5 Hashing for Large Files

MVP uses SHA-256 and skips large raw outputs by default unless overridden.

Follow-on decisions:

- Confirm large-file threshold.
- Confirm whether large raw outputs must ever be hashed.
- Consider whether partial hashes, chunk manifests, or external checksum files are useful later.
- Decide whether hash computation should be parallelized or scheduled separately.

### 24.6 Generated Product Governance

MVP inventories generated CSV/XLSX/PPT products but does not version them in Git.

Follow-on decisions:

- Decide whether generated products are archived elsewhere.
- Decide whether CSV/XLSX/PPT artifacts should be promoted to a controlled evidence store.
- Decide whether final briefing artifacts require formal release state.

### 24.7 Excel and Manual Transformation

MVP assumes Excel is generated from CSV for charts/reports and does not contain manual analyst transformations.

Follow-on decisions:

- Determine whether real Excel workbooks contain manual transformations.
- If yes, define whether those transformations must move upstream into scripts or be captured through workbook-level controls.
- Decide how to identify manually modified downstream products.

### 24.8 Tableau

MVP treats Tableau as optional consumer and does not provide special handling.

Follow-on decisions:

- Decide whether Tableau workbooks/extracts need to be inventoried as first-class artifacts.
- Decide whether Tableau-generated outputs are derived products under `provenance/products/`.

### 24.9 Schema and Type Validation

MVP only performs simple shape checks.

Follow-on decisions:

- Define formal dataset contracts for required extracts.
- Decide when to add column type validation.
- Decide whether to use Pydantic, Pandera, Great Expectations, or a lightweight custom validator.

### 24.10 Parquet/DuckDB/Polars Benchmarking

MVP does not introduce these tools into the production path.

Follow-on decisions:

- Run local benchmarks later to test storage, memory, and performance hypotheses.
- Consider Parquet only after provenance is real.
- Treat modernization claims as hypotheses requiring representative data.

---

## 25. Implementation Guidance for Codex

Important implementation posture:

- Favor clarity over cleverness.
- Keep the demo runnable.
- Make paths explicit.
- Keep shell scripts small.
- Keep Ansible as orchestration, not business logic.
- Keep Make as stage coordination, not provenance authority.
- Keep Python helpers focused and testable.
- Fail fast on provenance violations.
- Do not silently skip missing scripts, dirty repos, or uncontrolled commands.
- Treat generated data as artifacts, not source-controlled truth.
- Ensure every generated product can be traced back to a stage, command, script commit, and input set.

Suggested first implementation slice:

1. Repo scaffold.
2. Bootstrap controlled-source-demo repo.
3. Ansible preflight Git gate.
4. Workspace creation.
5. Synthetic canonical sim layout.
6. Mock simulation writing raw outputs.
7. Required Perl extraction writing `required.csv`.
8. Python inventory/hash helper.
9. Simple validation.
10. Manifest generation.
11. Smoke tests.

Defer XLSX/PPTX generation if necessary, but ideally include real generated artifacts using common Python packages such as `openpyxl`, `python-pptx`, and `matplotlib` if acceptable in the WSL development environment.

---

## 26. Final Concept Statement

Build a WSL-runnable, Ansible-and-Make-driven synthetic reference implementation that demonstrates how to wrap an existing engineering simulation workflow with a provenance spine. The implementation must preserve the canonical simulation runtime layout under `sim-run-root/`, place all provenance evidence and downstream analytical/reporting products under a sibling `provenance/` directory, require Git-controlled source/scripts as a hard entrance criterion, mock LSF execution for now, inventory and hash artifacts according to a practical SHA-256 policy, perform basic shape validation, and emit a human-readable `manifest.yaml` that tells the full story from controlled inputs and scripts through raw simulation outputs and generated CSV/XLSX/PPT products.
