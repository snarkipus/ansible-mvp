## 1. Fresh Run Guard

- [x] 1.1 Add a preflight run-root policy check that rejects an existing `runs/{run_id}` before writing run evidence when policy is `fresh`.
- [x] 1.2 Add `--run-root-policy {fresh,reuse}` to the preflight CLI and wire `RUN_ROOT_POLICY ?= fresh` through the Makefile preflight target.
- [x] 1.3 Add tests for default duplicate `run_id` rejection and explicit `reuse` allowance.

## 2. Manifest Execution Context

- [x] 2.1 Add `run.started_at` and `run.finished_at` derived from collected stage evidence timestamps during manifest assembly.
- [x] 2.2 Add `run.execution_context` with user, hostname, platform, Python version, and Git version.
- [x] 2.3 Extend manifest smoke required key checks and tests to require non-empty run timing and execution context.

## 3. Lifecycle Lane And Documentation

- [x] 3.1 Add `evidence` as an accepted lifecycle lane in tests/docs and reclassify `inventory_pre` as evidence collection.
- [x] 3.2 Update README and handoff docs for fresh-run default behavior, explicit reuse debugging, run execution context, and evidence lifecycle vocabulary.

## 4. Verification And Closure

- [x] 4.1 Run `make check`.
- [x] 4.2 Run manual bootstrap and documented Ansible workflow with a fresh verification `run_id`.
- [x] 4.3 Run a duplicate `run_id` negative check and a `RUN_ROOT_POLICY=reuse` preflight check.
- [x] 4.4 Run `openspec validate harden-run-freshness-and-execution-context --type change --strict --json`, `openspec validate --specs --strict --json`, and `bd lint --json`.
- [x] 4.5 Update `docs/how_to_use_this_mvp.md` final verification note after implementation verification completes.
