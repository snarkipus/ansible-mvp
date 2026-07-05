# Post-Review Hardening Plan (Historical)

> **Status: historical, executed.** This plan was implemented in full on
> 2026-07-04 via the archived OpenSpec change
> `2026-07-04-harden-run-freshness-and-execution-context` plus maintenance
> commits (see `git log` around "Complete post-review maintenance cleanup" and
> "Implement run freshness and manifest context"). It is retained as design
> rationale only; the README and `docs/how_to_use_this_mvp.md` are authoritative
> for current behavior.

 Fix New Review Deficiencies (post-review hardening, new items only)

 Context

 A read-only review of the completed provenance MVP surfaced a second tier of deficiencies beyond the original findings. The user
 chose to fix only the new items, using the OpenSpec + beads workflow that AGENTS.md prescribes: behavior/contract changes go
 through an OpenSpec change proposal; docs/dependency cleanups are tracked as maintenance beads.

 The new deficiencies:

 1. AGENTS.md falsely states the repo is concept-only ("Do not assume Makefile, ansible/, src/provenance/ ... exist", commands are
 "design targets") — misleads every future agent/contributor.
 2. matplotlib>=3.9 in pyproject.toml:8 is never imported anywhere (reports.py hand-rolls the PNG via struct/zlib).
 3. Nothing enforces the documented "fresh run_id per run" contract: prepare_workspace uses exist_ok=True and manifest assembly
 globs logs/*.stage.json + validations/*.json (src/provenance/manifest.py:206-208), so rerunning a failed run_id in place silently
 merges stale evidence into a "clean" manifest.
 4. The manifest has no execution context (user, hostname, platform, tool versions) and no run-level start/finish timestamps — only
 per-stage ones — despite README's manifest expectations listing "timestamps".
 5. Small items: schema_version in configs is read by nobody; inventory_pre is lifecycle-classed finalization though it runs
  mid-flow (repo's own docs/archive/core-workflow-refactoring-recommendations.md suggests an evidence lane); CLI stage-evidence flag naming
 is inconsistent (--output vs --stage-output); basedpyright excludes tests/; absolute host paths are embedded in manifest evidence.

 Part A — Maintenance beads (no OpenSpec change)

 Create one bead each (bd create ... -t chore/task), fix, close.

 A1. Rewrite stale AGENTS.md sections

 - AGENTS.md:1-51: rewrite Current State to describe the implemented scaffold (Makefile, ansible/, configs/, src/provenance/,
 tests/, templates/, sibling ../controlled-source-demo bootstrap). Rewrite Commands (AGENTS.md:25-35) to state the bootstrap/run
 commands are implemented and verified, not "design targets". Keep Provenance Rules, OpenSpec/beads sections as-is (still accurate).

 A2. Remove unused matplotlib dependency

 - Delete "matplotlib>=3.9" from pyproject.toml dependencies; run uv lock to regenerate uv.lock; run make check to confirm nothing
 imported it transitively.

 A3. Validate schema_version on config load

 - In the YAML loaders that read configs/run.synthetic.yaml and configs/expected_shape.required_extract.yaml (shared
 _read_yaml_mapping call sites in src/provenance/preflight.py, stages.py, workspace.py, scheduler.py, manifest.py, cli.py), add a
 single shared check that schema_version == "0.1", raising ValueError otherwise. Prefer one helper (e.g. in a small shared module or
 on preflight._read_yaml_mapping's pattern) rather than six copies — note these modules currently each carry a private
 _read_yaml_mapping; consolidating them into one helper module is in-scope for this bead.
 - Add a focused test in tests/test_configs.py.

 A4. (Optional polish) Typecheck tests

 - pyproject.toml [tool.basedpyright] include: add "tests"; fix whatever surfaces. Skip if it explodes into large churn — record a
 follow-up bead instead.

 Part B — One OpenSpec change: run-lifecycle + execution-context hardening

 Follow the repo workflow: /opsx-propose-style change under openspec/changes/ (e.g. harden-run-freshness-and-execution-context),
 spec deltas for synthetic-provenance-run and provenance-manifest, tasks mapped to beads, archive when done. Validate with openspec
 validate --specs --strict --json and bd lint --json.

 B1. Enforce fresh run_id (rerun-in-place guard)

 - Design decision to encode in the proposal: the guard lives at the entrance of a run. Recommended mechanics:
   - preflight CLI gains a run-root freshness check: fail with a clear error when runs/{run_id} already exists, before any evidence
 is written (note: preflight currently creates provenance/logs/ via stage_attempt_evidence, so the check must run first in
 _cmd_preflight).
   - Provide an explicit escape hatch for the documented single-target debugging flow: Make variable RUN_ROOT_POLICY ?= fresh → CLI
 flag --run-root-policy {fresh,reuse}; only preflight consumes it. The Ansible playbook keeps the default (fresh), so full
 orchestrated runs always require a new run_id; a developer rerunning individual targets passes RUN_ROOT_POLICY=reuse.
 - Files: src/provenance/cli.py (_cmd_preflight), Makefile (preflight target + variable), configs/run.synthetic.yaml (no change
 expected), docs/how_to_use_this_mvp.md + README.md (troubleshooting/partial-run wording: rerunning the same run_id now fails fast
 by default).
 - Tests: new case in tests/test_synthetic_workflow_smoke.py (second run with same run_id fails; RUN_ROOT_POLICY=reuse allows
 targeted rerun) and/or tests/test_cli.py.
 - Spec delta: synthetic-provenance-run — new requirement "Run workspaces are fresh per run_id" with fail/override scenarios.

 B2. Record execution context in the manifest

 - In assemble_run_manifest (src/provenance/manifest.py:159), add an execution_context block under run:
   - executed_by (getpass.getuser()), hostname (socket.gethostname()), platform (platform.platform()), python_version, git_version
 (reuse the _git runner in src/provenance/git_state.py or git --version via subprocess).
   - Run-level started_at/finished_at derived at assembly time from min/max of the collected stage-evidence timestamps (already
 parsed in stages records).
 - Add run.execution_context (non-empty) to REQUIRED_NON_EMPTY_KEY_PATHS in src/provenance/manifest.py:45 so the smoke check covers
 it, and to the required-sections documentation in configs/run.synthetic.yaml only if key paths are listed there (they are not —
 only top-level sections; no config change needed).
 - Tests: extend tests/test_manifest.py and the e2e assertions in tests/test_synthetic_workflow_smoke.py.
 - Spec delta: provenance-manifest — new requirement "Manifest captures execution context".

 B3. Lifecycle lane for evidence collection (small, include in same change)

 - Add evidence as a recognized lifecycle lane; reclass inventory_pre (configs/run.synthetic.yaml:189-203) from finalization to
 evidence. inventory_post stays finalization (or also evidence — pick one in the proposal; the recommendations doc lists it as
 evidence/finalization).
 - Code impact: none required (lifecycle_class is a free string in stages.py); update spec wording in synthetic-provenance-run
 ("demo bootstrap, admission, setup, factory, and finalization" → include evidence), docs mentions in README/how-to, and the smoke
 test's expectations if any assert exact classes.

 Explicitly deferred (record as beads or fold into the open define-artifact-lifecycle-and-git-policy change; do not implement now)

 - Absolute-host-path portability of manifest/evidence → add as a task/requirement note to the already-open
 define-artifact-lifecycle-and-git-policy change.
 - CLI --output vs --stage-output naming unification → backlog bead (touching it churns the Makefile and tests for cosmetic gain).

 Verification

 1. make check (ruff format check, ruff check, basedpyright, pytest — includes the full ansible e2e smoke test).
 2. Manual end-to-end per docs: make bootstrap-controlled-source, then the documented ansible-playbook ... -e run_id=<fresh> run;
 inspect runs/<id>/provenance/manifest.yaml for run.execution_context and run-level timestamps.
 3. Negative check: rerun the same run_id → preflight fails fast; make preflight RUN_ROOT_POLICY=reuse ... succeeds.
 4. openspec validate --specs --strict --json and bd lint --json clean before archiving the change.
 5. Update the final-verification note in docs/how_to_use_this_mvp.md with the new verification date/run (this also retires the
 "stale verification" concern for the touched behavior).
