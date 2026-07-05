# Final MVP Verification (2026-07-04)

Historical verification log, relocated from `docs/how_to_use_this_mvp.md`
during the 2026-07-05 documentation restructuring. The durable evidence
caveats from the original section now live in the operator guide's
"Evidence Caveats" section.

Final verification for the MVP scaffold was refreshed on 2026-07-04 with:

```bash
make bootstrap-controlled-source
make check
ansible-playbook ansible/playbooks/run_synthetic_workflow.yml \
  -i ansible/inventory/localhost.ini \
  -e run_id=final_verification_20260704_hardening2 \
  -e controlled_source_repo=../controlled-source-demo \
  -e controlled_source_ref=controlled-source-demo-v0.1.1
```

The bootstrap, quality gate, and clean synthetic workflow completed
successfully. The manifest included run-level timestamps and
`run.execution_context`. A second Ansible run with the same `run_id` failed at
preflight because the run root already existed, and
`make preflight RUN_ROOT_POLICY=reuse` succeeded for the same run id as an
explicit focused-debugging escape hatch. Maintainer-only OpenSpec and bead
hygiene checks were also run during development; they are not required for
ordinary demo execution. Generated verification outputs are intentionally
ignored under `runs/`.
