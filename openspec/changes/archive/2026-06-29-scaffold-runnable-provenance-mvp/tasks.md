## 1. Project Scaffold

- [x] 1.1 Add root `.gitignore` entries for generated run outputs, generated reports, Python caches, and local virtual environments without ignoring source/config files needed for the MVP.
- [x] 1.2 Add `pyproject.toml` managed by `uv` with the MVP runtime, test, lint, format, and type-check dependencies: PyYAML, pytest, ruff, basedpyright, openpyxl, python-pptx, and any minimal chart dependency selected for `chart.png`.
- [x] 1.3 Create the repository structure for `ansible/`, `configs/`, `scripts/`, `src/provenance/`, `templates/`, `tests/`, and `runs/.gitkeep`.
- [x] 1.4 Add `ruff` and `basedpyright` configuration for typed Python helpers, including package discovery for `src/provenance` and test-friendly type-check settings.
- [x] 1.5 Add a Makefile with documented targets for bootstrap, preflight, workspace preparation, materialization, mock scheduler, simulation, extraction, reporting, inventory, validation, manifest generation, format, lint, typecheck, test, check, and clean operations.

## 2. Controlled Source Demo Bootstrap

- [x] 2.1 Implement `make bootstrap-controlled-source` to create or verify a sibling `../controlled-source-demo` Git repository.
- [x] 2.2 Populate the controlled source demo with tracked synthetic fixture inputs for `dirA`, `dirB`, and `dirC`.
- [x] 2.3 Add tracked controlled scripts to the demo repo: `procs/run-script.sh`, `scripts/synthetic_sim_engine.sh`, `scripts/extract_required.pl`, and `scripts/ad_hoc_extract.py`.
- [x] 2.4 Commit the controlled source demo contents and tag the expected reference `controlled-source-demo-v0.1.0`.
- [x] 2.5 Make bootstrap fail clearly when an existing `../controlled-source-demo` is incompatible, dirty, missing expected tracked files, or missing the expected tag.

## 3. Provenance Helper Package

- [x] 3.1 Add `src/provenance/git_state.py` to capture repository existence, Git worktree status, ref resolution, tracked-file checks, and script identity details.
- [x] 3.2 Add `src/provenance/inventory.py` to inventory files with relative path, size, mtime, simulation/product area, logical group, and role metadata.
- [x] 3.3 Add `src/provenance/hashing.py` to compute SHA-256 hashes and represent hash status for MVP artifacts.
- [x] 3.4 Add `src/provenance/validation.py` to perform simple file existence, non-empty, row-count, column-count, and header checks for CSV products.
- [x] 3.5 Add `src/provenance/manifest.py` to assemble the run manifest from config, Git state, inventories, stages, logs, scheduler metadata, validations, products, and hash policy.
- [x] 3.6 Add `src/provenance/cli.py` exposing focused commands for Git state, inventory, validation, manifest assembly, and manifest smoke validation.

## 4. Run Orchestration

- [x] 4.1 Add `configs/run.synthetic.yaml` and `configs/expected_shape.required_extract.yaml` with the documented synthetic run, controlled scripts, stage declarations, approved command paths, hash policy, layout, and validation expectations.
- [x] 4.2 Add `ansible/inventory/localhost.ini`, group variables, and `ansible/playbooks/run_synthetic_workflow.yml` for local execution.
- [x] 4.3 Implement preflight so missing repos, non-Git repos, unresolved refs, dirty controlled source state, dirty wrapper controlled paths, missing scripts, untracked scripts, unknown controlled script references, and uncontrolled stage command paths fail before execution.
- [x] 4.4 Implement workspace preparation for `runs/{run_id}/sim-run-root/` and `runs/{run_id}/provenance/` without placing provenance files inside `sim-run-root/`.
- [x] 4.5 Implement input and runtime-script materialization, including copying `procs/run-script.sh` from controlled source into `sim-run-root/procs/run-script.sh`.
- [x] 4.6 Implement mock LSF submission metadata under `provenance/scheduler/` without requiring real LSF commands.

## 5. Synthetic Workflow Stages

- [x] 5.1 Implement the synthetic simulation stage so controlled scripts write the raw output `sim-run-root/lists/dirC/sim-out.dat`.
- [x] 5.2 Implement required extraction to produce `provenance/products/extracted/required.csv` from raw outputs.
- [x] 5.3 Implement ad hoc extraction to produce `provenance/products/extracted/ad_hoc.csv` from raw outputs.
- [x] 5.4 Implement minimal report generation to produce `summary.xlsx`, `chart.png`, and `briefing.pptx` under `provenance/products/reports/` while keeping generated products out of Git.
- [x] 5.5 Capture per-stage logs under `provenance/logs/` and make stage status/return codes available to the manifest.

## 6. Manifest And Validation

- [x] 6.1 Generate pre-run input and controlled-script inventories under `provenance/inventories/`.
- [x] 6.2 Generate post-run raw-output and derived-product inventories under `provenance/inventories/`, including raw output identity for `sim-run-root/lists/dirC/sim-out.dat` with `sim_area: lists` and `logical_group: dirC`.
- [x] 6.3 Run CSV shape validation for `required.csv` and write validation evidence under `provenance/validations/`.
- [x] 6.4 Assemble `runs/{run_id}/provenance/manifest.yaml` with required top-level sections and links between repositories, branch/tag/describe output, script hashes, scheduler metadata, inputs, runtime scripts, stages, logs, raw outputs, derived products, validations, notes, and hash policy.
- [x] 6.5 Add manifest smoke validation that fails when required top-level sections or key values are missing.

## 7. Tests And Documentation

- [x] 7.1 Add unit tests for Git state capture, tracked script detection, wrapper controlled path detection, SHA-256 hashing, inventory metadata, CSV shape validation, and manifest smoke validation.
- [x] 7.2 Add smoke tests for a clean synthetic run, dirty controlled source failure, dirty wrapper controlled path failure, untracked script failure, uncontrolled stage command failure, missing ref failure, absent real LSF tools, manifest generation, exact report product generation, product separation from `sim-run-root/`, and required CSV validation.
- [x] 7.3 Add a quality gate target that runs `uv run ruff format --check`, `uv run ruff check`, `uv run basedpyright`, and `uv run pytest` in that order.
- [x] 7.4 Add `docs/how_to_use_this_mvp.md` for junior engineers, covering prerequisites, setup, bootstrap, run commands, expected outputs, manifest inspection, extension points, controlled-script rules, validation/report additions, troubleshooting, and what not to change.
- [x] 7.5 Update README quickstart notes if implementation details differ from the existing documented command shape, and link to the handoff guide.
- [x] 7.6 Run the relevant test suite, quality gate, and a local clean synthetic workflow command, then record any known limitations or deferred follow-up work.
