# AGENTS.md

## Current State
- This repo currently contains concept/planning material, not the runnable MVP scaffold described in `README.md` and `docs/provenance_first_mvp_concept_spec.md`.
- Do not assume `Makefile`, `ansible/`, `src/provenance/`, `tests/`, `requirements.txt`, or `controlled-source-demo` exist until you create or verify them.
- Root `openspec/` exists but currently has empty `specs/` and no active changes under `openspec/changes/`.

## Intended MVP Shape
- Build a local Ubuntu/WSL synthetic reference implementation, not production HPC deployment.
- Use Ansible as the outer harness, Make as the local stage runner, and Python helpers for Git state, inventory, SHA-256 hashing, validation, and manifest assembly.
- The workflow model uses two sibling repos: this provenance wrapper repo and `../controlled-source-demo` for synthetic controlled scripts/fixtures.
- Preserve `runs/{run_id}/sim-run-root/` as the simulation contract: `input/`, `lists/`, `files/`, and `procs/run-script.sh`.
- Put all evidence and derived products under sibling `runs/{run_id}/provenance/`, including `manifest.yaml`, logs, inventories, scheduler metadata, validations, extracted CSVs, and reports.
- `dirA`, `dirB`, and `dirC` intentionally repeat under multiple simulation areas; identify artifacts by full relative path plus `sim_area`/`logical_group`, never by leaf directory name alone.

## Provenance Rules
- Git-controlled source/scripts are a hard entrance gate; do not add a non-Git fallback for workflow scripts.
- Preflight should fail if required repos are missing, refs do not resolve, worktrees are dirty, scripts are missing/untracked, or stage commands point at uncontrolled local scripts.
- `sim-run-root/procs/run-script.sh` must be materialized from controlled source, not hand-authored inside a run directory.
- Generated CSV/XLSX/PPT/report artifacts are derived products; do not store them in Git and do not place them inside `sim-run-root/`.
- Manifest output is the main deliverable; it must connect controlled inputs/scripts, materialization choices, stages, logs, raw outputs, derived products, validations, and hash status.
- Use SHA-256 for MVP hashes; large production-output hash policy is intentionally deferred.
- Mock LSF only for the MVP; do not require `bsub`, `bjobs`, `bhist`, `bacct`, or a real scheduler.

## Commands
- Planned bootstrap command from docs: `make bootstrap-controlled-source` creates/tags `../controlled-source-demo` as `controlled-source-demo-v0.1.0` once the Makefile exists.
- Planned run command from docs:
  ```bash
  ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
    -i ansible/inventory/localhost.ini \
    -e run_id=demo_001 \
    -e controlled_source_repo=../controlled-source-demo \
    -e controlled_source_ref=controlled-source-demo-v0.1.0
  ```
- These commands are currently design targets, not verified executable commands, until the scaffold is implemented.

## OpenCode/OpenSpec
- Repo-local OpenCode commands exist under `.opencode/commands/`: `/opsx-propose`, `/opsx-apply`, `/opsx-explore`, and `/opsx-archive`.
- For substantial implementation work, prefer the local OpenSpec workflow: propose the change, implement tasks, then archive when complete.
- If using OpenSpec CLI output, trust resolved paths from `openspec status --change <name> --json`; do not assume fixed change/artifact paths beyond what the CLI reports.
