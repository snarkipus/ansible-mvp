# Trace `required.csv` Through the Provenance Chain

This walkthrough follows one derived artifact — `required.csv` — backward and
forward through a real run, showing every file that connects it to controlled
source. Without this chain, the repo looks like a sophisticated folder
generator. With it, every number in the CSV is traceable to a Git commit.

The examples below come from an actual run with `run_id=demo_001`. Hashes,
timestamps, and PIDs are run-specific; the file names, paths, and linkage
structure are stable. To follow along with your own evidence:

```bash
ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
  -i ansible/inventory/localhost.ini \
  -e run_id=demo_001 \
  -e controlled_source_repo=../controlled-source-demo \
  -e controlled_source_ref=controlled-source-demo-v0.1.2
```

The full chain we are about to walk:

```text
controlled input/tag
  -> materialized sim-run-root
    -> mock scheduler submission
      -> run_simulation.stage.json
        -> raw sim output
          -> extract_required
            -> required.csv
              -> validation
                -> immutable manifest
                  -> sibling assembly/smoke hash receipts
```

## Start with the run id

Everything for one run lives under `runs/demo_001/`:

```text
runs/demo_001/
├── sim-run-root/       # the simulation contract (inputs, scripts, raw outputs)
└── provenance/         # wrapper-owned evidence sidecar
```

The artifact we are tracing is:

```text
runs/demo_001/provenance/products/extracted/required.csv
```

Its content:

```csv
logical_group,example,bytes,sha256_prefix
dirC,ex1.dat,67,e9f4ce672451
dirC,ex2.dat,67,47ad55091256
dirC,ex3.dat,69,e2ef2db9cb49
```

Three rows, one per controlled input file in `dirC`. Where did each value come
from, and how do we know?

## Controlled source and input materialization

The run starts from the controlled-source repo at a resolved tag. The manifest
(`runs/demo_001/provenance/manifest.yaml`) records the exact state under
`repositories`:

```yaml
- name: controlled-source-demo
  requested_ref: controlled-source-demo-v0.1.2
  resolved_commit: de04ae34ea8706868bcab1b130ad1dac28bc1eee
  describe: controlled-source-demo-v0.1.2
  worktree_status: clean
```

Preflight (`provenance/preflight.json`) proved this before any stage ran: repo
present, ref resolved, worktree clean, required scripts tracked.

The `materialize_inputs` stage then copied controlled inputs into the run. The
manifest's `inputs` section records the full lineage for each file:

```yaml
- relative_path: input/dirC/ex1.dat
  sim_area: input
  logical_group: dirC
  sha256: e9f4ce672451e0dfe5aa0033fb903d4205f365f1ad53a50ac2ca4a586f2642a1
  materialization:
    materialization_mode: copy_from_controlled_source
    source_path: fixtures/controlled_inputs/dirC/ex1.dat
    source_ref: controlled-source-demo-v0.1.2
    source_resolved_commit: de04ae34ea8706868bcab1b130ad1dac28bc1eee
    source_blob_oid: 0123456789abcdef...
    source_file_mode: '100644'
    source_sha256: e9f4ce672451e0dfe5aa0033fb903d4205f365f1ad53a50ac2ca4a586f2642a1
```

Note the hash: `e9f4ce672451...`. Hold that thought — it reappears in the CSV.

The runtime script got the same treatment. `sim-run-root/procs/run-script.sh`
was not hand-authored; the manifest's `runtime_scripts` section records that it
was copied from `procs/run-script.sh` at the same resolved commit, with its
SHA-256 matching the Git-tracked blob recorded under `repositories`.

Those identities come from the selected Git tree, not a later worktree read.
Inputs and executable code are copied into read-only run-local destinations and
their modes and hashes are verified immediately before use.

Note that `dirA`, `dirB`, and `dirC` deliberately repeat across `input/`,
`lists/`, and `files/`. Every evidence record therefore carries the full
relative path plus `sim_area` and `logical_group` — the leaf directory name
alone is never an identity.

## Scheduler submission and terminal evidence

The payload did not run directly. It crossed the mock LSF boundary as one
monolithic job. Submission evidence
(`provenance/scheduler/submission.yaml`):

```yaml
submission:
  job_id: mock-demo_001
  queue: mock-local
  state: RUN
  payload_command: procs/run-script.sh
  submitted_at_utc: '2026-07-05T18:57:00.799996Z'
  pid: 3028849
  process_group_id: 3028849
  process_start_time_ticks: 73583648
receipt_id: 4a0f...
run_id: demo_001
```

Submit returned while the job was still running (`state: RUN`). The wait stage
polled scheduler state and recorded each observation in
`provenance/scheduler/job-state.json`:

```json
"wait_observations": [
  {"observed_at": "2026-07-05T18:57:01.590634Z", "pid_alive": true,  "state": "RUN"},
  {"observed_at": "2026-07-05T18:57:02.842340Z", "pid_alive": true,  "state": "RUN"},
  {"observed_at": "2026-07-05T18:57:03.092685Z", "pid_alive": false, "state": "DONE"}
]
```

The terminal verdict was written by the scheduler-owned wrapper process —
not inferred by the waiter — into
`provenance/scheduler/terminal-state.json`:

```json
{
  "job_id": "mock-demo_001",
  "state": "DONE",
  "exit_code": 0,
  "started_at": "2026-07-05T18:57:00.881697Z",
  "finished_at": "2026-07-05T18:57:02.935083Z",
  "payload_stage_evidence": "runs/demo_001/provenance/logs/run_simulation.stage.json"
}
```

Finally, collect wrote the accounting summary
(`provenance/scheduler/accounting.yaml`):

```yaml
job_id: mock-demo_001
state: DONE
exit_code: 0
elapsed_seconds: 2.053386
future_real_lsf_equivalent: [bjobs, bhist, bacct]
```

Terminal states are `DONE`, `EXIT`, or `TIMEOUT`. Only `DONE` allows the
workflow to proceed to extraction.

`provenance/validations/scheduler_receipt.json` checks that submission, job
state, terminal state, accounting, and payload evidence share the same receipt,
run, and job identities; timestamps are monotonic; terminal and accounting
status are `DONE`/zero; and the raw-output identity agrees. The manifest embeds
that coherence verdict under `scheduler.receipt_validation`.

## Payload execution evidence

The job's payload was the materialized controlled script. Its stage evidence
(`provenance/logs/run_simulation.stage.json`) records what actually executed:

```json
{
  "name": "run_simulation",
  "command": "procs/run-script.sh",
  "cwd": "runs/demo_001/sim-run-root",
  "controlled_scripts": ["run_script", "synthetic_sim_engine"],
  "status": "pass",
  "return_code": 0,
  "started_at": "2026-07-05T18:57:00.881697Z",
  "finished_at": "2026-07-05T18:57:02.935083Z"
}
```

The timestamps match the scheduler's terminal state exactly — the scheduler
evidence and the payload evidence describe the same process. Stdout/stderr
streams live alongside as `run_simulation.stdout.log` / `.stderr.log`.

## Raw output location

The simulation wrote its primary raw output inside the simulation contract:

```text
runs/demo_001/sim-run-root/lists/dirC/sim-out.dat
```

```csv
logical_group,example,bytes,sha256_prefix
dirA,ex1.dat,67,fde107e3d50d
dirA,ex2.dat,67,51864bdcac97
...
dirC,ex1.dat,67,e9f4ce672451
```

The manifest's `raw_simulation_outputs` section inventories it with full
identity:

```yaml
- relative_path: lists/dirC/sim-out.dat
  sim_area: lists
  logical_group: dirC
  role: raw_output
  sha256: 85382a6a356f0cf357afae3bc742a33d439b01ae2b33a39ed8762cff55d8d447
  size_bytes: 303
```

## Extraction into required.csv

The `extract_required` stage ran the controlled Perl extractor against the raw
output. Its stage evidence
(`provenance/logs/extract_required.stage.json`, mirrored in the manifest's
`stages` list) captures the whole transaction:

```yaml
name: extract_required
command: scripts/extract_required.pl sim-run-root/lists/dirC/sim-out.dat
         provenance/products/extracted/required.csv
controlled_scripts: [extract_required]
status: pass
return_code: 0
inputs:
  - relative_path: provenance/scheduler/job-state.json     # DONE gate evidence
  - relative_path: provenance/scheduler/accounting.yaml
  - relative_path: sim-run-root/lists/dirC/sim-out.dat
    sha256: 85382a6a356f0cf357afae3bc742a33d439b01ae2b33a39ed8762cff55d8d447
outputs:
  - relative_path: provenance/products/extracted/required.csv
    role: extracted_product
    sha256: d02d79e1372bb8ef28ff223f4816d3959dec990c574442cdd93e6d53624be815
```

Two things to notice:

1. The scheduler evidence appears as declared *inputs* to extraction. That is
   the extraction gate made visible: extraction refuses to run unless
   `job-state.json` shows terminal `DONE`. A failed, timed-out, or missing job
   stops here instead of producing a plausible-looking CSV.
2. The input hash (`85382a...`) matches the raw output inventory, and the
   output hash (`d02d79...`) is about to reappear in the product inventory.

And the payoff for holding that earlier thought: the CSV row
`dirC,ex1.dat,67,e9f4ce672451` carries the first 12 characters of the SHA-256
that the manifest recorded for the materialized controlled input
`input/dirC/ex1.dat` (`e9f4ce672451e0df...`). The derived product's *content*
is verifiably about the controlled inputs the run admitted.

## Validation evidence

The `validate` stage checked the CSV against
`configs/expected_shape.required_extract.yaml` and wrote
`provenance/validations/required_extract.json`:

```json
{
  "path": "products/extracted/required.csv",
  "status": "pass",
  "total_rows": 4,
  "data_rows": 3,
  "header": ["logical_group", "example", "bytes", "sha256_prefix"],
  "checks": [
    {"name": "non_empty",              "status": "pass"},
    {"name": "minimum_data_row_count", "status": "pass"},
    {"name": "column_count",           "status": "pass"},
    {"name": "header",                 "status": "pass"}
  ]
}
```

## Manifest links

`runs/demo_001/provenance/manifest.yaml` ties the whole chain into one
document. For `required.csv` specifically:

- `repositories` — the controlled-source tag, resolved commit, and per-script
  Git blob + SHA-256 identity.
- `inputs` — each materialized input with `copy_from_controlled_source`
  lineage back to `fixtures/controlled_inputs/dirC/*.dat`.
- `runtime_scripts` — `procs/run-script.sh` materialization lineage.
- `scheduler` — job id, submission, terminal `DONE`, exit code 0, and links to
  all five scheduler evidence files.
- `stages` — the `extract_required` entry with command, inputs, outputs, and
  return code shown above.
- `raw_simulation_outputs` — `lists/dirC/sim-out.dat` with hash `85382a...`.
- `derived_products` — the product record:

  ```yaml
  - relative_path: products/extracted/required.csv
    product_area: extracted
    role: extracted_product
    producing_stage: extract_required
    sha256: d02d79e1372bb8ef28ff223f4816d3959dec990c574442cdd93e6d53624be815
    size_bytes: 129
  ```

- `validations` — the semantic shape-check verdict for the same path, plus the
  validation receipt path and SHA-256.

## Final manifest receipts

The manifest includes stages completed before assembly; it does not attempt to
contain evidence about its own final bytes. After `manifest.yaml` is written,
`provenance/logs/manifest.stage.json` records its SHA-256. Smoke validates those
unchanged bytes, stage order/success, artifact hashes, selected-source and
producer links, scheduler coherence, and successful product validations. It
then writes `provenance/validations/manifest_smoke.json` and
`provenance/logs/manifest_smoke.stage.json` with the same manifest hash.

This avoids self-reference: neither finalization receipt is embedded in the
manifest it finalizes or verifies. The hashes provide local integrity checks
and selected-commit binding, but no signature, trusted timestamp, tamper-proof
storage, or immutable archive.

## What this proves

Starting from nothing but `required.csv` and the manifest, a reviewer can
answer:

- **Which inputs produced this?** The `dirC` controlled inputs, by full path
  and hash — and the CSV content itself embeds their hash prefixes.
- **What code produced it?** `scripts/extract_required.pl` from
  `controlled-source-demo` at commit `de04ae3`, tag
  `controlled-source-demo-v0.1.2`, operating on a raw output produced by the
  Git-tracked, hash-recorded `procs/run-script.sh`.
- **Did the simulation actually finish?** Yes — scheduler-owned terminal
  `DONE` with exit code 0, with the wait history showing the job was genuinely
  asynchronous.
- **Is the product intact and sane?** Its SHA-256 is recorded, and an explicit
  shape validation passed.

Every arrow in the chain is a file you can open. That is the MVP's claim:
not that it runs a simulation, but that it leaves this trail every time.
