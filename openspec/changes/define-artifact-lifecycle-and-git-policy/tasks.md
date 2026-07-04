## 1. Policy Proposal

- [x] 1.1 Document Git boundary and artifact classifications in OpenSpec proposal/design/spec deltas.
- [x] 1.2 Reserve manifest vocabulary for archive status, archive URI/reference, archive policy, retention class, promotion status, release labels, lifecycle state, and external references.
- [x] 1.3 Document Jinja-rendered consumed input policy as generated input evidence, not ordinary derived product output.
- [x] 1.4 Define archive/freeze design expectations without implementing runtime archive commands.

## 2. Validation

- [x] 2.1 Run `openspec validate define-artifact-lifecycle-and-git-policy --type change --strict --json`.
- [x] 2.2 Run `bd lint --json`.
