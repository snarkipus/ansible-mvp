## Context

The synthetic workflow currently records mock LSF submission metadata before executing `run_simulation`, but Make/Python still executes the simulation directly as an operator-facing stage. That is acceptable as a minimal placeholder, but it does not force the MVP to handle the production-shaped scheduler seam: submit returns early, job state changes independently, wait/poll observes terminal status, and accounting evidence is collected after completion.

The target team uses LSF in a minimal way: submit one monolithic job, wait/check for completion, and collect enough evidence to continue downstream analysis. This design intentionally models that contract rather than full LSF behavior.

## Goals / Non-Goals

**Goals:**

- Model a minimal local mock-`bsub` boundary for one simulation job per run.
- Make async semantics real in the MVP: submit starts a scheduler-owned local wrapper process and returns before terminal payload completion.
- Separate scheduler submission, wait/poll state, accounting evidence, and payload execution evidence.
- Keep the existing controlled simulation payload and its stage evidence traceable.
- Preserve Ansible as the outer harness and Make as the local stage contract.
- Keep the default operator demo production-shaped while allowing fast deterministic test delays.

**Non-Goals:**

- No real LSF command dependency.
- No daemon, queue service, networking, or multi-job scheduler.
- No job arrays, dependencies, fairshare, resource selection, backfill, or host allocation model.
- No production resume semantics for partially completed runs.
- No artifact archive/freeze implementation.
- No attempt to redesign the team's broader HPC usage.

## Decisions

### Use descriptive Make targets with mock-`bsub` evidence vocabulary

Expose `submit-mock-lsf`, `wait-mock-lsf`, and `collect-mock-lsf` as the stable Make targets. Inside scheduler evidence and documentation, map those targets to the familiar `bsub`, `bjobs`/wait, and `bacct`/`bhist` roles.

Alternatives considered:

- Rename targets to `mock-bsub`, `mock-bwait`, and `mock-bacct`. This is concise, but leaks emulator implementation vocabulary into the operator surface.
- Keep only `submit-mock-lsf` and `run-simulation`. This preserves current simplicity but does not teach the workflow the async boundary.

### Keep Ansible as the stage sequencer, not the evidence engine

Ansible should provide environment admission, per-stage task visibility, fail-fast sequencing, and future host targeting. It should not compute provenance, inspect scheduler state, create run evidence, or implement the wait/poll loop. Those provenance-bearing decisions stay in Python behind Make targets.

The playbook should invoke one Make target per Ansible task so operators can see the coarse failing stage at the harness level. The current single `make target1 target2 ...` shape preserves fail-fast inside Make but collapses the Ansible execution record into one large command.

The configured stage order in `configs/run.synthetic.yaml` should be the source of truth. To avoid drift, Ansible should obtain its stage target list from Python/config-derived output or a Python validation step, not maintain an independent hand-copied target list in inventory variables.

Alternatives considered:

- Put scheduler wait/poll in Ansible with `until`/retry. This would discard provenance-bearing poll observations and make future real-LSF replacement less direct.
- Keep a separate Ansible stage list in `group_vars`. This is simple but likely to drift when adding `wait-mock-lsf` and `collect-mock-lsf`.
- Let Make remain the only stage sequencer. This hides useful per-stage harness visibility from operators and weakens Ansible's role.

### Make `local_async` the production-shaped emulator mode

`submit_mock_lsf` starts a scheduler-owned local wrapper process with `subprocess.Popen(...)`, writes submission/job state evidence including PID and paths, and returns immediately. `wait_mock_lsf` polls scheduler-owned state files and process liveness until terminal status or timeout. `collect_mock_lsf` requires terminal state and writes normalized accounting evidence.

Alternatives considered:

- `sync_dispatch`, where wait runs the payload synchronously. This is easier to test but risks creating three synchronous stages wearing async names. It can remain a future fallback or narrow test helper, but it is not the conceptual target.
- A daemonized emulator. This is unnecessary for one job per run and increases cleanup/orphan risk.

### Put observable delay in the controlled payload path

The default operator demo should use configurable mock runtime delay settings so `submit` returns before completion and `wait` observes non-terminal state. The delay belongs to the controlled synthetic workload or its controlled invocation path, not to fake scheduler sleep.

The configured delay range should be deterministic for a given `run_id` when jitter is enabled, and tests should override delay to subsecond deterministic values so quality gates remain fast.

The controlled runtime delay SHALL live in the controlled-source demo payload, preferably `procs/run-script.sh` or `scripts/synthetic_sim_engine.sh`, rather than in a wrapper-owned scheduler invocation. This keeps provenance semantics honest: the job takes time because the controlled workload takes time, not because the wrapper repository pretends scheduler latency exists.

Because this changes the controlled-source payload contract, the bootstrap compatibility contract and default controlled-source ref must move forward together. Do not silently mutate the existing `controlled-source-demo-v0.1.0` contract; introduce a new controlled-source demo tag such as `controlled-source-demo-v0.1.1` and update defaults, tests, and documentation consistently.

### Manage local subprocesses as scheduler-owned jobs

The emulator should start the local payload with explicit stdout/stderr file paths and enough process identity to observe or diagnose the job later. Avoid pipe-based output capture that can deadlock if the waiter is not draining the process. Treat missing PIDs, vanished processes, stale non-terminal state, and timeout as scheduler evidence conditions rather than generic Python errors.

Because `submit_mock_lsf` and `wait_mock_lsf` run as separate short-lived processes, wait cannot rely on inheriting a child handle or calling `waitpid` to obtain the payload return code. `submit_mock_lsf` must launch a scheduler-owned wrapper that records terminal state to files under `provenance/scheduler/` after the payload exits. The wrapper is responsible for recording at least `started_at`, `finished_at`, `exit_code`, and terminal `DONE` or `EXIT` state. `wait_mock_lsf` polls those files plus process liveness; it does not infer successful completion merely from PID disappearance.

Use `start_new_session=True` or equivalent process-group isolation so timeout cleanup can target the scheduler-owned payload tree. PID reuse must be handled by recording process start identity where available and by preferring scheduler-owned terminal state files over liveness-only checks.

### Treat timeout as a mock `bkill` boundary

On wait timeout, `wait_mock_lsf` should attempt a bounded cleanup of the scheduler-owned process group and then write explicit timeout evidence. The final scheduler state for a timed-out job should be failed/non-successful, not `DONE`, and downstream extraction must not run. If the process cannot be killed or its state cannot be confirmed, evidence should record the orphan/unknown condition clearly and still block downstream extraction.

Fresh-run policy remains the primary protection against accidental reuse. For explicit debug reuse, scheduler submit/wait should detect existing live job state for the same run id and fail clearly rather than starting a second payload over the same run evidence.

### Keep payload execution evidence first-class but not operator-facing

`run_simulation.stage.json` or equivalent payload execution evidence remains available for manifest traceability. The concise `workflow.operator_flow` should show `Submit simulation -> Wait for simulation -> Collect scheduler evidence -> Extract results`, not direct operator execution of `run_simulation` outside the scheduler boundary.

### Gate downstream extraction on scheduler terminal `DONE`

Extraction stages must require terminal scheduler `DONE`, not just the raw output file. Payload `EXIT`, wait timeout, vanished process, missing PID, or collection before terminal state must stop downstream extraction with clear scheduler evidence.

## Risks / Trade-offs

- Local async subprocesses can outlive a failed orchestration command -> Mitigate with scheduler-owned wrapper state, process-group cleanup on timeout, explicit orphan/unknown evidence, and fresh-run default policy that prevents accidental reuse.
- Runtime delay jitter can make tests flaky -> Mitigate with configured delay ranges that are deterministic for a given `run_id` and short test overrides.
- PID state can become stale if a process vanishes -> Mitigate by treating vanished/missing process as explicit failed scheduler evidence rather than silently continuing.
- Exit codes can be lost across short-lived submit/wait processes -> Mitigate by having the scheduler-owned wrapper write exit code and terminal state to evidence files.
- Adding scheduler stages changes operator flow and tests -> Mitigate by preserving low-level payload evidence and updating manifest/docs in the same change.
- The emulator still is not real LSF -> Mitigate by recording future real-LSF evidence equivalents and keeping real LSF integration deferred to a separate change.

## Migration Plan

1. Add scheduler config fields for emulator execution mode, wait timeout, poll interval, and controlled runtime delay.
2. Replace the current mock scheduler helper with submit, wait, and collect functions while preserving generated evidence under `provenance/scheduler/`.
3. Update Make and Ansible stage order to call submit/wait/collect before extraction.
4. Update run configuration and manifest assembly so scheduler evidence and payload evidence are linked.
5. Update docs and tests for the async operator flow.
6. Update the controlled-source templates to own the runtime delay, create a new controlled-source demo contract tag such as `controlled-source-demo-v0.1.1`, and update bootstrap compatibility checks, default refs, tests, and docs consistently.
7. Keep no backward-compatibility fallback for old generated run directories; run evidence is generated and fresh by default.

## Open Questions

- Should `sync_dispatch` be implemented now as a narrow test mode, or deferred entirely until a concrete need appears?
