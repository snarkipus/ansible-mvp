## 1. Scheduler Configuration and Gate

- [x] 1.1 Add scheduler config fields for `emulator_execution_mode`, payload command identity, poll interval, wait timeout, and deterministic mock runtime delay.
- [x] 1.2 Update config validation tests to accept valid local async scheduler settings and reject malformed scheduler settings.
- [x] 1.3 Extend preflight/stage command validation so mock scheduler payload commands must resolve to approved controlled workflow code.
- [x] 1.4 Ensure `submit-mock-lsf`, `wait-mock-lsf`, and `collect-mock-lsf` remain approved wrapper Make targets.
- [x] 1.5 Add controlled runtime-delay support to the controlled-source demo payload, bump the controlled-source demo contract tag/ref from `controlled-source-demo-v0.1.0` to a new tag such as `controlled-source-demo-v0.1.1`, and update bootstrap compatibility, docs, and tests as one coherent contract change.

## 2. Local Async Emulator

- [ ] 2.1 Replace the current single mock scheduler helper with submit, wait, and collect helpers in scheduler code.
- [ ] 2.2 Implement `submit_mock_lsf` local async behavior using `subprocess.Popen` to launch a scheduler-owned wrapper with submission evidence, PID/process-group state recording, scheduler-owned terminal-state file paths, and stdout/stderr paths.
- [ ] 2.3 Implement the scheduler-owned wrapper so it executes the payload and writes started/finished timestamps, exit code, and terminal `DONE`/`EXIT` state under `provenance/scheduler/`.
- [ ] 2.4 Implement `wait_mock_lsf` polling with non-terminal state observation, terminal state file detection, timeout handling, missing PID handling, vanished-process evidence, and stale non-terminal state handling.
- [ ] 2.5 Implement `collect_mock_lsf` accounting output that requires terminal state and links scheduler state to payload execution evidence.
- [ ] 2.6 Add deterministic configured runtime-delay support in the controlled synthetic payload path, with fast test overrides and run-id-seeded jitter when a range is configured.
- [ ] 2.7 Ensure subprocess stdout/stderr are written to files without pipe-drain deadlocks and that timeout cleanup attempts process-group termination before recording timeout/orphan evidence.

## 3. Orchestration and Stage Evidence

- [ ] 3.1 Update Make targets to use `submit-mock-lsf`, `wait-mock-lsf`, and `collect-mock-lsf` before extraction.
- [ ] 3.2 Add Python/config-derived stage target listing or validation so `configs/run.synthetic.yaml` remains the source of truth for run stage order.
- [ ] 3.3 Update the Ansible playbook to invoke one configured Make target per task in configured order, preserving fail-fast behavior and readable harness-level failure boundaries.
- [ ] 3.4 Ensure Ansible does not implement scheduler polling or evidence decisions; those remain behind Python CLI commands invoked through Make.
- [ ] 3.5 Update `configs/run.synthetic.yaml` stage declarations, display order, lifecycle metadata, operator visibility, inputs, and outputs for the scheduler boundary.
- [ ] 3.6 Preserve payload execution evidence such as `run_simulation.stage.json` while removing direct payload execution from the concise operator-facing flow.
- [ ] 3.7 Gate extraction on terminal scheduler `DONE` rather than only raw-output presence.

## 4. Manifest, Docs, and Operator Flow

- [ ] 4.1 Update manifest assembly to link scheduler submission, terminal job state, accounting evidence, job id, final state, and payload execution evidence.
- [ ] 4.2 Update `workflow.operator_flow` so it presents submit, wait, collect, extract, and report phases without showing direct simulation execution outside the scheduler boundary.
- [ ] 4.3 Update README and handoff documentation to describe the local async mock-`bsub` boundary, evidence files, failure behavior, and real-LSF replacement seam.
- [ ] 4.4 Document that real LSF integration, daemonized scheduling, multi-job scheduling, and production resume semantics remain deferred.
- [ ] 4.5 Document any controlled-source ref/tag change and the expected bootstrap command behavior if the controlled payload contract changes.

## 5. Tests and Validation

- [ ] 5.1 Add scheduler unit tests for submit returning before terminal state, wrapper-recorded exit code, wait terminal success, wait timeout cleanup, payload nonzero exit, missing PID, stale non-terminal state, vanished process, and collect-before-terminal failure.
- [ ] 5.2 Add preflight tests for approved and rejected mock scheduler payload commands.
- [ ] 5.3 Update synthetic workflow smoke tests to cover the clean async scheduler flow with short deterministic delay settings and extraction refusal when scheduler state is not terminal `DONE`.
- [ ] 5.4 Update manifest tests to verify scheduler evidence links, operator flow, and payload stage evidence remain complete.
- [ ] 5.5 Run `make check`, strict OpenSpec validation, and `bd lint --json` before closing implementation work.
