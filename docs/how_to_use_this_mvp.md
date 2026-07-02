# How to Use This Provenance MVP

This guide is for junior engineers running or extending the local provenance-first
MVP. The goal is to prove a safe pattern: workflow scripts and inputs come from
Git-controlled source, the simulation layout stays familiar, and every generated
output is connected to `runs/{run_id}/provenance/manifest.yaml`.

## Prerequisites

- Ubuntu or WSL shell
- Git
- Make
- Ansible
- Python 3.11+
- Perl
- `uv` for Python tool execution

On Windows workstations, run all MVP commands inside Ubuntu/WSL, not directly in
native PowerShell or CMD. The workflow assumes `make`, `bash`, Unix-style paths,
and Ansible are available in the Linux environment. A Windows user can either
open the WSL shell first or prefix commands with `wsl`, for example
`wsl make bootstrap-controlled-source`.

The MVP uses two sibling repositories:

```text
workspace/
├── ansible-mvp/              # this provenance wrapper repo
└── controlled-source-demo/   # bootstrapped Git repo with synthetic inputs/scripts
```

## IDE and Editor Setup

Use an IDE/editor from inside the same Ubuntu/WSL environment used to run the
workflow. Point the editor at the Python environment managed by `uv`; do not use a
random global interpreter if you expect imports, linting, and type checking to
match `make check`.

Recommended editor integrations:

- Ruff for formatting and lint diagnostics.
- basedpyright, Pyright, or Pylance-compatible type checking that reads the
  `[tool.basedpyright]` configuration in `pyproject.toml`.
- The repository root as the workspace folder so `src/provenance` package
  discovery and test paths match the command-line tools.

The command-line source of truth remains:

```bash
make check
```

If IDE diagnostics disagree with `make check`, trust `make check` first and then
adjust the editor interpreter/environment settings.

## Setup and Bootstrap

From this repository root inside Ubuntu/WSL, create or verify the sibling
controlled-source demo:

```bash
make bootstrap-controlled-source
```

This command is intentionally strict. It creates `../controlled-source-demo` when
missing, or verifies that an existing repo is clean, compatible, has the expected
tracked files, and has tag `controlled-source-demo-v0.1.0`.

## Run the Synthetic Workflow

Use the documented Ansible command shape:

```bash
ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
  -i ansible/inventory/localhost.ini \
  -e run_id=demo_001 \
  -e controlled_source_repo=../controlled-source-demo \
  -e controlled_source_ref=controlled-source-demo-v0.1.0
```

For focused debugging, individual Make targets can also be run, but keep the same
configuration values and do not bypass preflight.

Read the run as a small factory flow, not as a flat list of implementation
targets:

```text
preflight gate -> workspace setup -> submit/run simulation -> extract results
-> build reports -> validate products -> inventory and manifest finalization
```

The granular Make targets are still useful for debugging. The manifest keeps them
as stage evidence with lifecycle metadata so support/finalization steps do not get
confused with domain transformations.

Choose a fresh `run_id` for each new execution. If a stage fails, the partial
`runs/{run_id}/` tree and `provenance/logs/` evidence are useful for inspection,
but the MVP does not guarantee safe resume or attempt-history semantics. After
fixing the cause of the failure, start again with a new `run_id` unless resume
behavior is added in a future change.

## Expected Outputs

A successful run creates this high-level shape:

```text
runs/demo_001/
├── sim-run-root/
│   ├── input/
│   ├── lists/
│   │   └── dirC/sim-out.dat
│   ├── files/
│   └── procs/run-script.sh
└── provenance/
    ├── manifest.yaml
    ├── logs/
    ├── inventories/
    ├── scheduler/
    ├── validations/
    └── products/
        ├── extracted/
        │   ├── required.csv
        │   └── ad_hoc.csv
        └── reports/
            ├── summary.xlsx
            ├── chart.png
            └── briefing.pptx
```

`sim-run-root/` is the simulation contract. Keep raw simulation behavior there.
`provenance/` is the sidecar for evidence, logs, validations, manifests, extracted
CSVs, and reports. Generated run products are ignored and must not be committed.

## Inspect the Manifest

Start with:

```bash
less runs/demo_001/provenance/manifest.yaml
```

Important sections to check:

- `repositories`: wrapper and controlled-source Git state, requested refs, resolved
  commits, branch/tag/describe values, tracked script paths, and hashes.
- `controlled_source_gate`: preflight checks that passed before execution.
- `inputs` and `runtime_scripts`: where materialized inputs/scripts came from and
  how they were copied into the run.
- `stages`: first-class attempt evidence for every configured workflow stage,
  including support/orchestration steps; records commands, working directories,
  statuses, return codes, log paths, evidence paths, timings, controlled scripts,
  inputs, and outputs.
- `raw_simulation_outputs`: raw artifacts such as `sim-run-root/lists/dirC/sim-out.dat`.
- `derived_products`: extracted CSVs and report files, with product area, role,
  producing stage, size, mtime, and SHA-256 hash.
- `validations`: CSV shape validation evidence and pass/fail status.

Remember that `dirA`, `dirB`, and `dirC` repeat in multiple areas. Identify files
by full relative path plus `sim_area` and `logical_group`, never by the leaf folder
name alone.

## Controlled-Script Rules

Before any workflow stage runs, preflight must prove that scripts and configured
wrapper paths are controlled. Do not add shortcuts around this gate.

Safe rules:

1. Add or update workflow scripts in a Git repository, normally
   `../controlled-source-demo` for synthetic controlled scripts.
2. Commit the script and use a resolvable ref or tag.
3. Declare the script in `configs/run.synthetic.yaml`.
4. Declare stages so commands reference approved repository-relative controlled
   script paths.
5. Let preflight validate tracked state, worktree cleanliness, script existence,
   and stage command paths before execution.

Unsafe patterns:

- Running ad hoc scripts from `/tmp`, a home directory, or an untracked local path.
- Editing scripts inside `runs/{run_id}/sim-run-root/procs/` by hand.
- Using hashes as a substitute for Git control.
- Ignoring dirty controlled-source worktrees.

## Safe Extension Points

When adding a new stage or artifact:

1. Put the source script in controlled Git and commit it.
2. Add the script identity and stage declaration to configuration.
3. Add or update preflight coverage so missing, untracked, dirty, or unknown script
   references fail before execution.
4. Write raw simulation outputs under the correct `sim-run-root/` area.
5. Write extracted CSVs and report products under `provenance/products/`.
6. Inventory and hash new artifacts with SHA-256 for the MVP.
7. Link the new inputs, scripts, logs, outputs, validations, and products into the
   manifest.
8. Add focused tests for the new behavior and failure mode.

## Adding Validations and Reports

- Put validation expectations in configuration, such as required CSV headers,
  minimum row count, and minimum column count.
- Write validation evidence under `runs/{run_id}/provenance/validations/`.
- Add report files under `runs/{run_id}/provenance/products/reports/` only.
- Ensure each derived product records its product area, role, producing stage, size,
  mtime, and SHA-256 hash in the manifest.

## Troubleshooting

- **Missing `../controlled-source-demo`:** run `make bootstrap-controlled-source`.
- **Missing ref or tag:** verify `controlled_source_ref` exists in the controlled
  source repo.
- **Dirty controlled source:** commit or revert changes in `../controlled-source-demo`.
- **Untracked script failure:** add the script to Git and commit it, then declare it
  in configuration.
- **Uncontrolled command failure:** change the stage command to use an approved
  controlled repository-relative script path.
- **Missing outputs:** inspect `runs/{run_id}/provenance/logs/` and the related
  `stages` entry in `manifest.yaml`.
- **Partial or failed run:** inspect the existing `runs/{run_id}/` evidence, then
  rerun with a new `run_id` after fixing the problem. Do not assume the MVP can
  safely resume a partially completed run.
- **CSV validation failure:** compare the generated CSV with
  `configs/expected_shape.required_extract.yaml`.
- **Real LSF tools are absent:** this is expected for the MVP; mock scheduler mode
  is used instead of `bsub`, `bjobs`, `bhist`, or `bacct`.

## What Not to Change

- Do not place provenance evidence, extracted CSVs, reports, or manifests inside
  `sim-run-root/`.
- Do not commit generated files under `runs/{run_id}/`.
- Do not hand-author `sim-run-root/procs/run-script.sh`; it must be materialized
  from controlled source.
- Do not add non-Git fallbacks for workflow scripts.
- Do not require real LSF tools for the local MVP.
- Do not identify artifacts only by `dirA`, `dirB`, or `dirC`; include full relative
  path, `sim_area`, and `logical_group`.

## Quality Checks

For code changes, run the full quality gate before closing work:

```bash
make check
```

`openspec` and `bd` are maintainer workflow tools. They are not required to run
the MVP demo. Use them only when changing project specs or beads:

```bash
openspec validate --specs --strict --json
bd lint --json
```

## Final MVP Verification and Deferred Limitations

Final verification for the MVP scaffold was run on 2026-06-29 with:

```bash
make bootstrap-controlled-source
make check
ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
  -i ansible/inventory/localhost.ini \
  -e run_id=final_verification_001 \
  -e controlled_source_repo=../controlled-source-demo \
  -e controlled_source_ref=controlled-source-demo-v0.1.0
```

The bootstrap, quality gate, and clean synthetic workflow completed successfully.
Maintainer-only OpenSpec and bead hygiene checks were also run during development;
they are not required for ordinary demo execution.
Generated verification outputs are intentionally ignored under `runs/`.

Known deferred limitations are tracked as follow-up beads rather than implemented in
this MVP: production real-LSF integration, safe failed-run resume semantics,
long-term artifact archival/formal schema validation, and production-scale hash
policy for large outputs.
