## Context

The MVP now has a runnable Ansible/Make/Python workflow and a manifest contract that aggregates stage evidence from `runs/{run_id}/provenance/`. Current workspace creation is permissive: `prepare_workspace` creates directories with `exist_ok=True`, and manifest assembly reads any matching evidence already present under the run. That is convenient during development but unsafe as the default full-run behavior because stale evidence can be silently included in a later manifest.

The manifest also records per-stage timestamps but not a run-level time range or host/user/tool context. For a provenance-first receipt, those details should be visible without requiring a reader to inspect individual stage records or external logs.

## Goals / Non-Goals

**Goals:**

- Fail fast by default when a full run attempts to reuse an existing `runs/{run_id}` workspace.
- Keep a deliberate reuse escape hatch for focused debugging of individual Make targets.
- Add manifest run-level timing derived from stage evidence.
- Add manifest execution context with user, host, platform, Python version, and Git version.
- Add an `evidence` lifecycle lane so inventory and similar collection stages are not mislabeled as factory transformations or finalization.

**Non-Goals:**

- No failed-run resume or merge semantics beyond explicit developer reuse.
- No archival, freezing, or artifact retention policy changes; those remain covered by artifact lifecycle policy work.
- No broad CLI flag rename churn for `--output` versus `--stage-output`.
- No attempt to make absolute host paths portable in this change.

## Decisions

### Freshness Guard Lives In Preflight

The freshness check will run at the start of `_cmd_preflight`, before any support-stage evidence is written. This keeps the entrance gate responsible for rejecting stale run roots and avoids creating `provenance/logs/` as a side effect of a failed admission check.

Alternative considered: make `prepare_workspace` reject existing run roots. That catches the common case but happens after preflight and can still leave admission evidence from a failed attempt. Preflight is the smaller and clearer hard gate.

### Reuse Is Explicit And Local

The Makefile will default `RUN_ROOT_POLICY ?= fresh` and pass it to preflight as `--run-root-policy`. The Ansible playbook keeps the default, so orchestrated runs require a new `run_id`. Developers can use `RUN_ROOT_POLICY=reuse` for targeted local debugging, where stale evidence risk is accepted by the operator.

Alternative considered: delete existing run roots automatically. That is destructive and conflicts with the provenance goal of preserving evidence unless an operator intentionally archives or removes it.

### Run Timing Is Derived From Stage Evidence

`run.started_at` and `run.finished_at` will be derived from the minimum `started_at` and maximum `finished_at` values found in stage evidence. This keeps run-level timing tied to recorded workflow facts instead of introducing a separate clock source at manifest assembly time.

Alternative considered: use manifest assembly time for run start and finish. That is easy but misleading because assembly is only the finalization stage, not the full workflow duration.

### Execution Context Is Captured During Manifest Assembly

Manifest assembly will add `run.execution_context` with `executed_by`, `hostname`, `platform`, `python_version`, and `git_version`. This captures the local environment responsible for assembling the final receipt without introducing a separate evidence file.

Alternative considered: write a standalone execution-context evidence file during preflight. That would add another artifact and ordering concern for limited MVP value.

### Evidence Lifecycle Lane Is Config Metadata

The `evidence` lifecycle lane will be accepted in config/tests/docs and used for pre-run inventory collection. No new execution behavior is required because lifecycle class is already manifest metadata.

Alternative considered: leave inventory under finalization. That keeps the enum smaller but obscures the difference between mid-run evidence collection and end-of-run final checks.

## Risks / Trade-offs

- Freshness guard may surprise users who rerun `demo_001` out of habit -> document the failure and the `RUN_ROOT_POLICY=reuse` escape hatch.
- Reuse mode can still produce mixed evidence -> keep it explicit, developer-oriented, and out of the default Ansible path.
- Deriving run timestamps depends on stage evidence timestamps being present -> keep smoke validation and tests covering non-empty run timing after clean runs.
- Execution context can include host-specific values -> record them as local-run evidence, while broader portability remains deferred.
