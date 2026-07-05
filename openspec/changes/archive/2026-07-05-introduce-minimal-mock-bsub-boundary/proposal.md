## Why

The current mock scheduler stage records a submission-shaped receipt before `run_simulation`, but the workflow still directly executes the simulation as an operator-facing stage. That is too thin for a provenance-first data-factory MVP whose eventual target is an asynchronous LSF boundary: the MVP should contend with submit, wait/poll, terminal state, and accounting evidence now, without implementing a real cluster.

## What Changes

- Replace the current synchronous `submit_mock_lsf` placeholder shape with a minimal local async mock-`bsub` boundary for one monolithic simulation job per run.
- Add explicit scheduler stages for submission, wait/poll, and accounting collection: `submit_mock_lsf`, `wait_mock_lsf`, and `collect_mock_lsf`.
- Execute the existing controlled simulation payload through the mock scheduler boundary using local async subprocess execution, so submission returns before the payload reaches terminal state.
- Keep `run_simulation` payload execution evidence available, but remove direct simulation execution from the concise operator-facing flow.
- Record scheduler submission, mutable/terminal job state, and normalized accounting evidence under `runs/{run_id}/provenance/scheduler/`.
- Require downstream extraction to depend on terminal scheduler `DONE`, not merely on the presence of the raw output file.
- Keep real LSF integration, multi-job scheduling, daemonized services, queue/resource modeling, job arrays, and production resume semantics deferred.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `synthetic-provenance-run`: Replace the mock scheduler metadata placeholder with a local async mock LSF boundary and update the clean-run stage contract.
- `provenance-manifest`: Represent scheduler submission, job state, accounting evidence, and payload execution evidence as distinct linked manifest concepts.
- `controlled-source-gate`: Ensure the mock scheduler payload remains an approved controlled command path and that scheduler wrapper commands do not bypass the controlled-source gate.

## Impact

- Affected code: `src/provenance/scheduler.py`, `src/provenance/cli.py`, `src/provenance/manifest.py`, stage evidence helpers, validation helpers, and tests.
- Affected orchestration: `Makefile`, `ansible/playbooks/run_synthetic_workflow.yml`, and `configs/run.synthetic.yaml` stage order and scheduler configuration.
- Affected controlled source: synthetic simulation payload may need a controlled, configurable runtime delay so `local_async` behavior is observable without adding fake scheduler sleep.
- Affected docs: README, handoff guide, and operator workflow descriptions need to describe submit/wait/collect rather than direct operator simulation execution.
- No real `bsub`, `bjobs`, `bhist`, or `bacct` dependency is introduced.
