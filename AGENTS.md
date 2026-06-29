# AGENTS.md

## Current State
- This repo currently contains concept/planning material, not the runnable MVP scaffold described in `README.md` and `docs/provenance_first_mvp_concept_spec.md`.
- Do not assume `Makefile`, `ansible/`, `src/provenance/`, `tests/`, `requirements.txt`, or `controlled-source-demo` exist until you create or verify them.
- Root `openspec/` exists but currently has empty `specs/` and no active changes under `openspec/changes/`.

## Intended MVP Shape
- Build a local Ubuntu/WSL synthetic reference implementation, not production HPC deployment.
- Use Ansible as the outer harness, Make as the local stage runner, and Python helpers for Git state, inventory, SHA-256 hashing, validation, and manifest assembly.
- The workflow model uses two sibling repos: this provenance wrapper repo and `../controlled-source-demo` for synthetic controlled scripts/fixtures.
- Preserve `runs/{run_id}/sim-run-root/` as the simulation contract: `input/`, `lists/`, `files/`, and `procs/run-script.sh`.
- Put all evidence and derived products under sibling `runs/{run_id}/provenance/`, including `manifest.yaml`, logs, inventories, scheduler metadata, validations, extracted CSVs, and reports.
- `dirA`, `dirB`, and `dirC` intentionally repeat under multiple simulation areas; identify artifacts by full relative path plus `sim_area`/`logical_group`, never by leaf directory name alone.

## Provenance Rules
- Git-controlled source/scripts are a hard entrance gate; do not add a non-Git fallback for workflow scripts.
- Preflight should fail if required repos are missing, refs do not resolve, worktrees are dirty, scripts are missing/untracked, or stage commands point at uncontrolled local scripts.
- `sim-run-root/procs/run-script.sh` must be materialized from controlled source, not hand-authored inside a run directory.
- Generated CSV/XLSX/PPT/report artifacts are derived products; do not store them in Git and do not place them inside `sim-run-root/`.
- Manifest output is the main deliverable; it must connect controlled inputs/scripts, materialization choices, stages, logs, raw outputs, derived products, validations, and hash status.
- Use SHA-256 for MVP hashes; large production-output hash policy is intentionally deferred.
- Mock LSF only for the MVP; do not require `bsub`, `bjobs`, `bhist`, `bacct`, or a real scheduler.

## Commands
- Planned bootstrap command from docs: `make bootstrap-controlled-source` creates/tags `../controlled-source-demo` as `controlled-source-demo-v0.1.0` once the Makefile exists.
- Planned run command from docs:
  ```bash
  ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
    -i ansible/inventory/localhost.ini \
    -e run_id=demo_001 \
    -e controlled_source_repo=../controlled-source-demo \
    -e controlled_source_ref=controlled-source-demo-v0.1.0
  ```
- These commands are currently design targets, not verified executable commands, until the scaffold is implemented.

## OpenCode/OpenSpec
- Repo-local OpenCode commands exist under `.opencode/commands/`: `/opsx-propose`, `/opsx-apply`, `/opsx-explore`, and `/opsx-archive`.
- For substantial implementation work, prefer the local OpenSpec workflow: propose the change, implement tasks, then archive when complete.
- If using OpenSpec CLI output, trust resolved paths from `openspec status --change <name> --json`; do not assume fixed change/artifact paths beyond what the CLI reports.

<!-- BEGIN BEADS INTEGRATION v:1 profile:full hash:0a1bbe8a -->

## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Quality

- Use `--acceptance` and `--design` fields when creating issues
- Use `--validate` to check description completeness

### Lifecycle

- `bd defer <id>` / `bd supersede <id>` for issue management
- `bd stale` / `bd orphans` / `bd lint` for hygiene
- `bd human <id>` to flag for human decisions
- `bd formula list` / `bd mol pour <name>` for structured workflows

### Auto-Sync

bd automatically syncs via Dolt:

- Each write auto-commits to Dolt history
- No manual export/import needed!

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and docs/QUICKSTART.md.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**

- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- END BEADS INTEGRATION -->
