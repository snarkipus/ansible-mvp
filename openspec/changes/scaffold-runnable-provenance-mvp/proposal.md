## Why

The repository currently has a strong provenance-first concept but no runnable scaffold to prove it. This change turns the concept into a local Ubuntu/WSL reference implementation that preserves the existing simulation workflow shape while making source, execution, outputs, and derived products traceable through a manifest.

## What Changes

- Add the initial runnable project scaffold for the provenance MVP: Ansible playbook, inventory, Makefile, typed Python helper package, scripts, configs, templates, tests, Python tooling, and generated-run ignore rules.
- Add a bootstrap path for a sibling `../controlled-source-demo` Git repository containing synthetic controlled inputs and executable workflow scripts.
- Add a strict preflight gate that fails when controlled repositories, refs, scripts, worktree state, or stage command paths violate the Git-controlled source policy.
- Add a local synthetic run path that creates `runs/{run_id}/sim-run-root/` with the canonical `input/`, `lists/`, `files/`, and `procs/` areas while writing provenance evidence under `runs/{run_id}/provenance/`.
- Add helper commands for Git state capture, file inventory, SHA-256 hashing, simple CSV shape validation, and `manifest.yaml` assembly.
- Add Python project tooling with `uv`, `ruff`, and `mypy` so implementation and verification use explicit, repeatable commands.
- Add a handoff-oriented “how to use this MVP” guide for junior engineers who need to run, understand, extend, and adapt the template.
- Add smoke tests for the clean run path and important preflight/manifest validation behavior.
- Defer production HPC deployment, real LSF integration, archival/vaulting, formal schema validation, and data-platform modernization.

## Capabilities

### New Capabilities

- `controlled-source-gate`: Verifies required repositories, refs, worktree cleanliness, tracked scripts, and approved script paths before a workflow run.
- `synthetic-provenance-run`: Runs a local synthetic workflow that preserves the canonical simulation layout and separates provenance evidence from simulation runtime files.
- `provenance-manifest`: Inventories, hashes, validates, and records the full synthetic run story in a machine-readable YAML manifest.

### Modified Capabilities

- None.

## Impact

- Adds executable project structure under the repository root, including `Makefile`, `pyproject.toml`, `uv.lock`, `ansible/`, `configs/`, `scripts/`, `src/provenance/`, `templates/`, `tests/`, and `runs/.gitkeep`.
- Adds user-facing handoff documentation, expected at `docs/how_to_use_this_mvp.md`, explaining setup, run commands, generated outputs, extension points, and guardrails.
- Creates or updates `.gitignore` to exclude generated run outputs and generated report artifacts from source control.
- Uses local tooling dependencies documented for the MVP: Git, Make, Ansible, Python 3.11+, Perl, `uv`, `ruff`, `mypy`, PyYAML, pytest, openpyxl, and python-pptx.
- Creates a sibling `../controlled-source-demo` repository during bootstrap; that repository is part of the synthetic demo boundary but is not stored inside this repository.
