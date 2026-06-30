## Context

The archived MVP proved the provenance wrapper pattern and already had first-class stage evidence for the main executable workflow stages. A follow-up review noted that support/orchestration stages such as preflight, workspace preparation, materialization, inventory, validation, manifest assembly, and manifest smoke validation should also appear as explicit stage attempts.

This change is retrospective documentation for the hardening already implemented in code. The implementation writes support stage evidence under `runs/{run_id}/provenance/logs/` and includes all configured stage names in manifest order.

## Decisions

1. Treat all configured stages as manifest-visible stage attempts.

   The manifest should not make downstream readers infer support-stage execution from side effects alone. Each configured stage should have explicit evidence with stage name, status, command, working directory/cwd, configured inputs/outputs, evidence path, timing, logs, and return code where applicable.

2. Preserve simple command validation rather than designing a shell parser.

   Stage commands remain restricted to simple executable-plus-arguments forms. Preflight rejects shell interpreters and obvious shell metacharacter constructs. This closes practical bypass paths for the MVP without attempting to safely parse arbitrary shell programs.

3. Keep production lifecycle concerns deferred.

   This change does not add real LSF asynchrony, resumable stage attempts, retry history, or partial-run merge semantics. Those remain separate production follow-ups.

## Validation

- `make check` validates the implemented stage evidence behavior and command hardening tests.
- `openspec validate --specs --strict --json` validates the main specs after the retrospective spec revisions.
- `bd lint --json` validates bead hygiene.
