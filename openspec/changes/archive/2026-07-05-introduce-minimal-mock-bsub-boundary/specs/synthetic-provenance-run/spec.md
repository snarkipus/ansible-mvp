## MODIFIED Requirements

### Requirement: Mock scheduler metadata is captured
The system SHALL emulate the team's minimal LSF submission, wait, and accounting boundary for one monolithic simulation job per run without requiring real LSF commands.

#### Scenario: Mock submission is recorded
- **WHEN** the mock scheduler submission stage runs
- **THEN** scheduler submission evidence is written under `runs/{run_id}/provenance/scheduler/`
- **AND** the evidence records mock LSF mode, a job id, submitted timestamp, payload command, stdout/stderr paths, and initial non-terminal state

#### Scenario: Local async payload is submitted
- **WHEN** `submit_mock_lsf` runs in `local_async` mode for a delayed synthetic payload
- **THEN** it starts a scheduler-owned local wrapper process and returns before the payload reaches terminal `DONE` or `EXIT` state
- **AND** it records process identity, scheduler-owned terminal state paths, and scheduler state evidence under `runs/{run_id}/provenance/scheduler/`

#### Scenario: Wait observes terminal state
- **WHEN** `wait_mock_lsf` runs after a successful local async submission
- **THEN** it observes at least one non-terminal scheduler state such as `PEND` or `RUN` before the payload reaches terminal `DONE` or `EXIT` for a normal delayed run
- **AND** it records started timestamp, finished timestamp, elapsed time, return code, and final scheduler state

#### Scenario: Wrapper records terminal payload status
- **WHEN** the scheduler-owned local wrapper finishes executing the payload
- **THEN** it writes terminal scheduler evidence containing exit code and `DONE` or `EXIT` state under `runs/{run_id}/provenance/scheduler/`
- **AND** `wait_mock_lsf` uses that scheduler-owned terminal evidence rather than relying on inherited child-process handles

#### Scenario: Timeout records failed scheduler evidence
- **WHEN** `wait_mock_lsf` reaches its configured timeout before the scheduler-owned wrapper records terminal `DONE` or `EXIT`
- **THEN** it attempts bounded cleanup of the scheduler-owned process group
- **AND** it records timeout, cleanup, and any orphan or unknown state evidence under `runs/{run_id}/provenance/scheduler/`
- **AND** the job is not treated as terminal `DONE`

#### Scenario: Accounting is collected after terminal state
- **WHEN** `collect_mock_lsf` runs after the job reaches terminal scheduler state
- **THEN** final normalized accounting evidence is written under `runs/{run_id}/provenance/scheduler/`
- **AND** the accounting evidence links to the payload execution evidence

#### Scenario: Real LSF tools are absent
- **WHEN** `bsub`, `bjobs`, `bhist`, or `bacct` are not installed
- **THEN** the synthetic MVP can still complete using mock scheduler mode

## ADDED Requirements

### Requirement: Simulation payload executes through scheduler boundary
The system SHALL execute the synthetic simulation payload through the mock scheduler boundary rather than as the direct operator-facing workflow stage.

#### Scenario: Operator flow shows scheduler boundary
- **WHEN** a clean synthetic run completes
- **THEN** the concise operator-facing flow includes submission, wait, and scheduler evidence collection before extraction
- **AND** direct `run_simulation` payload execution is not presented as the operator-facing top-level simulation stage outside the scheduler boundary

#### Scenario: Payload evidence remains available
- **WHEN** the mock scheduler executes the simulation payload
- **THEN** payload execution evidence such as `run_simulation.stage.json` or equivalent remains available for detailed provenance

### Requirement: Ansible sequences configured stage targets
The system SHALL use Ansible for environment admission, per-stage Make target sequencing, fail-fast harness visibility, and future host targeting without moving provenance-bearing logic out of Python.

#### Scenario: Playbook runs one configured stage per task
- **WHEN** the documented Ansible playbook runs a clean synthetic workflow
- **THEN** Ansible invokes one configured Make stage target per task in configured order
- **AND** a stage failure is visible at the corresponding Ansible task boundary

#### Scenario: Stage order uses run configuration as source of truth
- **WHEN** the Ansible playbook determines which Make targets to run
- **THEN** it derives the target order from `configs/run.synthetic.yaml` through Python/config-derived output or validates that any harness list matches the configured stage order
- **AND** it does not rely on an independently maintained hand-copied stage list that can drift silently

#### Scenario: Ansible does not own scheduler polling
- **WHEN** the mock scheduler job is waiting for terminal state
- **THEN** scheduler polling, timeout handling, and scheduler evidence writing are performed by Python behind the `wait-mock-lsf` Make target rather than by Ansible retry logic

### Requirement: Downstream extraction waits for scheduler success
The system SHALL prevent downstream extraction from running unless the mock scheduler job reaches terminal `DONE` state.

#### Scenario: Extraction follows successful scheduler completion
- **WHEN** the mock scheduler job reaches terminal `DONE` and accounting evidence is collected
- **THEN** downstream extraction stages may run against the produced raw simulation output

#### Scenario: Extraction is blocked after scheduler failure
- **WHEN** the payload exits nonzero, the wait stage times out, the process vanishes, or the job state is not terminal `DONE`
- **THEN** downstream extraction does not run
- **AND** scheduler evidence records the failed or non-terminal condition clearly

### Requirement: Mock scheduler async timing is configurable
The system SHALL support configurable local async timing so operator demos exercise submit/wait/collect while tests can run quickly.

#### Scenario: Operator demo uses observable delay
- **WHEN** the default local async scheduler configuration is used
- **THEN** the simulation payload delay is long enough for `submit_mock_lsf` to return before terminal payload completion

#### Scenario: Tests use fast deterministic delay
- **WHEN** tests override mock runtime delay settings
- **THEN** the async scheduler flow remains deterministic and completes without long wall-clock delays

#### Scenario: Delay jitter is deterministic for a run
- **WHEN** mock runtime delay is configured as a range
- **THEN** the selected delay is deterministic for a given `run_id` when seeded run-id behavior is enabled

#### Scenario: Controlled source delay contract changes explicitly
- **WHEN** controlled-source templates change to support synthetic runtime delay
- **THEN** the delay is owned by the controlled-source demo payload rather than a wrapper-owned scheduler invocation
- **AND** bootstrap compatibility checks, default controlled-source refs, tests, and documentation are updated consistently rather than mutating the existing `controlled-source-demo-v0.1.0` tag contract silently
- **AND** a new controlled-source demo tag such as `controlled-source-demo-v0.1.1` identifies the updated payload contract
