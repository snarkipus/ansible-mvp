## Context

The repository currently contains concept documentation and OpenCode/OpenSpec tooling, but not the executable MVP scaffold described by the concept spec. The MVP must demonstrate a provenance wrapper around an existing simulation-style workflow, not replace that workflow with a new orchestrator or data platform.

The synthetic implementation must run locally on Ubuntu/WSL and model two Git repositories: this provenance wrapper repo and a sibling `../controlled-source-demo` repo containing controlled synthetic scripts and fixtures. Generated run artifacts must remain outside Git and under `runs/{run_id}/`.

Python helper code is provenance-critical: it decides what is controlled, what was run, what was produced, and what the manifest says. The scaffold should therefore use explicit Python project tooling from the start: `uv` for environment/dependency execution, `ruff` for linting/formatting, and `mypy` for static type checking.

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

## Decisions

1. Use Make as the stable local stage contract and Ansible as the operator harness.

   Make targets keep the stage flow executable outside Ansible for focused debugging. Ansible remains responsible for loading variables, checking prerequisites, setting up the run, invoking Make, and surfacing failures, but it does not become a custom DAG engine.

   Alternative considered: implement all orchestration directly in Ansible tasks. That would make local focused runs harder and blur orchestration with stage semantics.

2. Keep controlled workflow scripts in `../controlled-source-demo` and materialize run-local scripts from that repo.

   The sibling repo makes the controlled-source boundary visible and testable. `sim-run-root/procs/run-script.sh` is copied from controlled source for each run instead of being authored under `runs/`.

   Alternative considered: store all synthetic scripts in this repo. That would be simpler but would not prove the two-repo source-control entrance gate described by the concept.

3. Treat preflight as a hard gate, not a warning collector.

   The workflow fails when required repos are missing, refs do not resolve, the controlled source worktree is not clean, required scripts are missing or untracked, or stage command paths are uncontrolled. Hashes are supporting evidence, not a replacement for Git control.

   Alternative considered: allow non-Git script paths with hash-only identity. That conflicts with the MVP thesis and risks becoming a permanent bypass.

4. Keep provenance evidence outside `sim-run-root/`.

   The simulation runtime directory remains recognizable to the existing workflow. Logs, inventories, scheduler metadata, validations, manifests, extracted CSVs, and reports live under `runs/{run_id}/provenance/`.

   Alternative considered: write manifest/log files into `sim-run-root/`. That would pollute the runtime contract and make the wrapper harder to remove or adapt.

5. Implement Python helpers as small testable CLI operations.

   Helper modules handle Git state capture, file inventory, SHA-256 hashing, simple shape validation, and manifest assembly. They are callable from Make targets and tests.

   Alternative considered: implement provenance logic in shell. Shell is suitable for simple materialization and mock submission, but YAML assembly, hashing policy, validation, and testability are clearer in Python.

6. Use smoke-level validation for the MVP.

   The manifest must have required sections and generated CSVs must satisfy simple row/column/header expectations. Formal schemas are deferred until the provenance spine is proven.

   Alternative considered: adopt JSON Schema or Pydantic immediately. That adds tooling and modeling cost before the run story is stable.

7. Use `uv`, `ruff`, and `mypy` as first-class project tooling.

   The scaffold should include `pyproject.toml` and `uv.lock` once dependencies are resolved. Make targets should call Python tools through `uv run`, and the quality gate order should be `ruff format --check`, `ruff check`, `mypy`, then `pytest`.

   Alternative considered: use bare `pip` and untyped Python. That would reduce setup files but make provenance helpers easier to drift and harder to verify as the manifest contract grows.

8. Enforce controlled source cleanliness strictly and wrapper repo cleanliness selectively.

   The sibling controlled source repository must be fully clean before a run. This provenance wrapper repo must be a Git worktree, and configured tracked executable/config paths in the wrapper must be clean and tracked. Generated outputs under ignored paths such as `runs/` must not make a run fail.

   Alternative considered: require the entire wrapper repo to be clean. That is conceptually simple, but local runs intentionally create ignored output and developer workflows may have unrelated planning edits. The MVP should still ensure all code/config participating in execution is tracked and clean.

9. Require concrete generated report artifacts for the synthetic acceptance path.

   The first MVP should generate `summary.xlsx`, `chart.png`, and `briefing.pptx` under `provenance/products/reports/` if dependencies are available through the Python environment. These artifacts can be minimal, but they prove that downstream report products are represented as derived products outside the simulation root.

   Alternative considered: defer report generation or use placeholder text files. That would weaken the acceptance path described in the concept and leave CSV-to-report provenance unproven.

10. Declare stage commands in configuration and validate them against controlled script identities.

   Stage configuration should list each stage name, command, working directory, expected controlled scripts, and whether the command uses a wrapper repo tool or controlled source tool. Preflight should validate these declarations before execution.

   Alternative considered: infer commands only from Make recipes. That is harder to validate before execution and makes uncontrolled script detection less deterministic.

11. Treat the handoff guide as an MVP output, not an afterthought.

   The implementation should include `docs/how_to_use_this_mvp.md` covering setup, bootstrap, running the workflow, reading outputs, reading the manifest, extending stages, adding controlled scripts, adding validations, and common failure modes. The guide should be concise and practical for junior engineers using the MVP as a template.

   Alternative considered: rely on README and inline comments only. That would be less useful for handoff because README describes project intent, while the guide needs to teach safe operation and extension.

12. Use one canonical synthetic raw output for the first MVP.

   The synthetic simulation should write a single raw output at `runs/{run_id}/sim-run-root/lists/dirC/sim-out.dat`. This keeps the first implementation focused while still exercising the repeated directory-name problem because the artifact must be identified by full relative path, `sim_area: lists`, and `logical_group: dirC`.

   Alternative considered: generate raw and supplementary outputs under every `dirA`/`dirB`/`dirC` area. That better mirrors the broader concept but adds unnecessary surface area for the first runnable proof.

## Risks / Trade-offs

- First slice may become too broad -> Keep XLSX/PPT generation minimal and prioritize the manifest spine, controlled-source gate, and smoke tests.
- Development runs may make the wrapper repo dirty -> Ignore generated `runs/` artifacts, require controlled source to be fully clean, and enforce tracked/clean status for wrapper code/config that participates in execution.
- Ansible and Make responsibilities may overlap -> Keep Ansible orchestration thin and Make targets explicit; provenance facts come from helper outputs and manifest assembly.
- Two-repo bootstrap may be brittle -> Make `bootstrap-controlled-source` idempotent for an existing clean demo repo and fail clearly when an incompatible repo exists.
- Hashing everything can become expensive in production -> The MVP uses SHA-256 on small synthetic files and records large-file policy as deferred production behavior.
- Generated report dependencies can distract from provenance -> Keep report contents minimal but generate the expected `summary.xlsx`, `chart.png`, and `briefing.pptx`; the success criteria remain traceability and manifest completeness.
- Static typing can slow early scripting -> Type the Python helper package because it owns provenance facts, but keep shell/Ansible glue simple and avoid over-modeling with a full schema framework.
- Handoff documentation can become stale -> Keep the guide focused on stable commands, output contracts, extension points, and provenance rules, and verify it during README/documentation review before handoff.
- A single raw output may under-represent production complexity -> Keep the canonical directory layout and full-path artifact identity now, then extend additional raw outputs later without changing the manifest model.

## Migration Plan

This change introduces a new scaffold rather than migrating existing executable code.

1. Add ignored generated-output paths before creating run artifacts.
2. Add `pyproject.toml`, `uv` dependency metadata, `ruff`, `mypy`, configuration, scripts, Python helpers, Ansible playbook, Makefile, tests, and handoff guide.
3. Bootstrap `../controlled-source-demo` with a tag used by the documented run command.
4. Verify the clean run path and failure tests locally.
5. Leave generated run output untracked.

Rollback is ordinary Git revert of scaffold files plus removal of generated local `runs/` and `../controlled-source-demo` if no longer needed.

## Open Questions

- None for the first implementation slice.
