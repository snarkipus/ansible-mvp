# Provenance-First Simulation Workflow MVP

A local synthetic reference implementation of an operator-triggered
**provenance factory** for sparse HPC-style analysis runs.

## What this is

This MVP demonstrates a repeatable pattern: it verifies Git-controlled source,
materializes a fresh run workspace, submits a scheduler-shaped job across a
mock LSF boundary, waits for terminal scheduler evidence, extracts and
validates products, and assembles a manifest that ties everything together.

The single run story:

```text
An operator selects a controlled source ref.
The wrapper resolves and inventories selected-commit source, then prepares a fresh run.
Selected-commit inputs and scripts are materialized into read-only run-local paths.
The mock scheduler submits the simulation payload asynchronously.
The workflow waits for terminal scheduler DONE before extracting.
Extracted products are validated before reports are generated.
The manifest ties source, scheduler evidence, raw outputs, products,
validations, and pre-assembly stage evidence together; sibling receipts bind
assembly and smoke validation to its unchanged final hash.
```

That is the MVP. Everything else is scaffolding.

**What this is not:** a production scheduler, CI system, artifact registry,
workflow platform, or real LSF integration. The simulation itself is
synthetic; the provenance pattern is the point.

## What problem it demonstrates

Engineering analysis runs produce reports whose lineage is usually
reconstructed from memory: which inputs, which script versions, did the job
actually finish, and can anyone prove it later? This MVP builds the
**provenance spine first** — every generated artifact traces back to
controlled source, inputs, execution context, scheduler truth, raw outputs,
extraction stages, and validations, all connected in
`runs/{run_id}/provenance/manifest.yaml`.

Two design commitments follow from that:

- **Controlled source is a hard entrance gate.** Workflow scripts and inputs
  must come from a clean Git repo at a resolved ref. There is no non-Git
  fallback; preflight fails fast otherwise.
- **Scheduler truth gates products.** Extraction runs only after the mock
  scheduler records terminal `DONE`. Failed or timed-out jobs leave
  inspectable evidence instead of plausible-looking products.
- **Selected commits bind consumed bytes.** Preflight inventories Git blob,
  mode, and SHA-256 identities from the resolved commit; execution uses
  verified run-local copies rather than re-reading a mutable source worktree.

## Quickstart

Run everything from a Linux shell (Ubuntu/WSL on Windows — not native
PowerShell or CMD). Required tools: Git, Make, Ansible, Python 3.11+, Perl,
and `uv`.

Bootstrap the synthetic controlled-source sibling repo (demo bootstrap only,
not a production factory stage):

```bash
make bootstrap-controlled-source
```

Run the synthetic workflow:

```bash
ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
  -i ansible/inventory/localhost.ini \
  -e run_id=demo_001 \
  -e controlled_source_repo=../controlled-source-demo \
  -e controlled_source_ref=controlled-source-demo-v0.1.2
```

Use a fresh `run_id` for each full run; preflight refuses an existing
`runs/{run_id}`. For code changes, `make check` is the quality gate
(format, lint, types, tests).

Run IDs must match `[A-Za-z0-9][A-Za-z0-9._-]*`. Configured and derived paths
must be relative, contain no `..`, and remain inside their designated workspace
root.

## What a successful run produces

```text
runs/demo_001/
├── sim-run-root/                      # preserved simulation contract
│   ├── input/  lists/  files/        # inputs and raw outputs
│   └── procs/run-script.sh           # materialized controlled script
└── provenance/                        # wrapper-owned evidence sidecar
    ├── manifest.yaml                  # immutable run provenance spine
    ├── preflight.json
    ├── scheduler/                     # submission, job/terminal state, accounting
    ├── logs/                          # stage evidence; manifest receipt holds final hash
    ├── inventories/
    ├── validations/
    └── products/
        ├── extracted/required.csv  ad_hoc.csv
        └── reports/summary.xlsx  chart.png  briefing.pptx
```

`sim-run-root/` keeps the familiar simulation layout. Everything the wrapper
learns or derives goes in `provenance/`, never inside the simulation tree, and
generated run products are never committed to Git.

## How to inspect the manifest

```bash
less runs/demo_001/provenance/manifest.yaml
```

Start with `workflow.operator_flow` (the short stage story), then
`repositories` (selected commits and artifact identities), `scheduler`
(coherent receipt status, job id, terminal state, exit code),
`derived_products`, and `validations`. Finally compare
`logs/manifest.stage.json` and `validations/manifest_smoke.json`: both identify
the SHA-256 of the unchanged `manifest.yaml`; neither receipt is embedded in
the file it finalizes.

The best way to understand what the manifest buys you is the artifact trace:
[`docs/trace_required_csv.md`](docs/trace_required_csv.md) follows one CSV
from controlled tag to validated product, file by file.

## Tooling roles

| Tool | Role | Why |
|---|---|---|
| Ansible | Thin operational harness | Environment admission, variable injection, per-stage visibility, fail-fast sequencing, future remote-host seam. Not the provenance engine. |
| Make | Local stage contract | Ubiquitous and available in restrictive environments; stable target names for humans and Ansible. Intentionally replaceable. |
| Python | Provenance/evidence engine | Owns everything that computes, decides, or leaves evidence: gating, hashing, scheduler state, validation, manifest assembly. |
| `uv` | Python environment/runner | Reproducible project-local tooling; conda or another approved manager could fill the same role. |
| Git | Controlled source gate | Hard entrance criterion for scripts and inputs; generated products stay out. |
| Mock LSF | Scheduler boundary | Models submit/wait/collect for one monolithic job without requiring `bsub`/`bjobs`/`bhist`/`bacct`. A seam, not a simulator. |

Rationale and nuances live in
[`docs/architecture.md`](docs/architecture.md).

## Current limitations

Stated plainly so MVP scope does not silently become a production contract:

- No real LSF integration; the mock boundary is the replacement seam.
- No resume/retry semantics: failed runs stay inspectable, then you start a
  fresh `run_id`.
- No signing, trusted timestamps, tamper-evident preservation, immutable
  archive, cataloging, or promotion workflow. Evidence is selected-commit-bound
  and locally hashed, but remains mutable local evidence.
- No large-output hashing policy beyond SHA-256 at MVP scale.
- No formal manifest schema; smoke validation enforces structure and current
  cross-record semantics in code.
- No CI/git-hook trigger; runs are sparse and human-gated by design.
- No multi-job scheduling, job arrays, or daemonized scheduling.
- Evidence may contain absolute local paths; it is host-bound evidence, not a
  portable archive format.
- Support-stage evidence records orchestration success, not a full
  process-level audit trail.

## Where to read next

- [`docs/how_to_use_this_mvp.md`](docs/how_to_use_this_mvp.md) — operator
  guide: prerequisites, running, inspecting evidence, troubleshooting, safe
  extension rules.
- [`docs/trace_required_csv.md`](docs/trace_required_csv.md) — trace one
  artifact through the full provenance chain.
- [`docs/architecture.md`](docs/architecture.md) — design notes: tool roles
  and rationale, run layout, stage contract, scheduler seam, hashing policy,
  manifest expectations.
