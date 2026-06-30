## 1. Stage Evidence Hardening

- [x] 1.1 Implement support/orchestration stage-attempt evidence for configured stages.
- [x] 1.2 Ensure manifest assembly includes all configured stage names in configured order.
- [x] 1.3 Add or update tests that prove support stage evidence exists and appears in the manifest.
- [x] 1.4 Update `openspec/specs/provenance-manifest/spec.md` with the first-class stage-attempt evidence requirement.

## 2. Command Hardening Spec

- [x] 2.1 Document the simple command-structure restriction in `openspec/specs/controlled-source-gate/spec.md`.
- [x] 2.2 Validate that the command-hardening spec reflects the implemented low-complexity behavior without requiring a full shell parser.

## 3. Verification

- [x] 3.1 Run `make check`.
- [x] 3.2 Run `openspec validate --specs --strict --json`.
- [x] 3.3 Run `bd lint --json`.
