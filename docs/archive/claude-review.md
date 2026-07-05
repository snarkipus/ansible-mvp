# External Review (Historical)

> **Status: historical, resolved.** This is an external code review captured on
> 2026-07-03. Every finding below was subsequently fixed or explicitly accepted
> and documented as a limitation via the archived OpenSpec change
> `2026-07-04-harden-run-freshness-and-execution-context` and follow-up
> maintenance commits. Do not treat these findings as current defects; see
> `docs/how_to_use_this_mvp.md` ("Final MVP Verification and Deferred
> Limitations") for the accepted limitations that remain by design.

I've now read the full implementation (all src/provenance modules, Makefile, Ansible layer, configs, bootstrap script,
  controlled-source templates, specs, and the tests), and cross-checked the actual final_verification_001 run evidence on disk.
  Here's the review.

  Overall verdict

  The implementation is disciplined and matches the specs closely. The gate is real (clean-worktree, tracked-script,
  approved-command-path, and no-shell-metacharacter checks are all enforced and negatively tested), the sim-root/provenance
  separation is enforced in code (workspace.py:111, scheduler.py:54-57), and the Ansible layer stays appropriately thin. The findings
  below are ordered by how much I think they matter.

  Clear issues

  1. manifest-smoke validates the manifest, then silently rewrites it (cli.py:795-803). After the smoke check passes,
  _cmd_smoke_manifest re-assembles the manifest and overwrites manifest.yaml. So the manifest that ends up on disk is not the
  artifact that was smoke-validated, and validations/manifest_smoke.json records a "pass" for content that no longer exists. The
  rewritten manifest is never re-checked — if the second assembly were ever wrong, the run would still report success. I understand
  the motivation (getting manifest_smoke.stage.json evidence into the manifest itself), but for a provenance-first system, the
  verification receipt not matching the final artifact is exactly the failure mode the project exists to prevent. A cleaner shape:
  accept that the final stage's evidence lives beside, not inside, the manifest — or smoke-check the rewritten manifest and make that
  the recorded result. Also, a command named "smoke" mutating its subject is a surprise for anyone running make manifest-smoke
  standalone to inspect an old run.

  2. Support-stage evidence is synthesized, not observed (stages.py:96-189). stage_attempt_evidence hardcodes status="pass" and
  return_code=0, and fabricates stdout logs ("Recorded successful orchestration stage: ...") for commands it never observed running.
  Similarly _cmd_build_reports writes its own fake build_reports.stdout.log (cli.py:436-438). Combined with the fact that
  support-stage evidence is only written on success (validate skips it on failure at cli.py:728-731, smoke likewise), the stages
  section of the manifest is a record of declared success rather than captured execution — for support stages, command: make
  preflight is what the config says, not what ran. The spec scopes this to clean runs, so it's defensible for the MVP, but it's the
  one pattern I'd flag hardest before anyone templates production code from this: real factory evidence should come from the thing
  that executed (return code, actual streams), and a failed attempt should leave evidence too. The three executed stages
  (run_simulation, extractions) do this correctly — they capture real return codes, real logs, and write evidence on failure. The
  asymmetry is worth a documented limitation at minimum.

  3. The documented "final verification" predates the current implementation. Every directory under runs/ (including
  final_verification_001) is dated 2026-06-29, but six commits touching src/, configs/, and the Makefile landed after that
  (support-stage evidence, lifecycle metadata, operator workflow shape). The on-disk verification manifest has no workflow section
  and only 4 stages — it verifies an older contract, and its manifest_smoke.json "pass" is from the old smoke rules. This is
  substantially mitigated by test_synthetic_workflow_smoke.py, which runs the full ansible-playbook flow in a temp checkout and
  asserts the complete current contract (all 14 stage-evidence files, operator_flow ordering, lifecycle fields). But the claim in
  docs/how_to_use_this_mvp.md:264 ("Final verification ... 2026-06-29") is stale as evidence for what's in the tree today. Cheap fix:
  rerun the documented three commands and update the date.

  4. assemble-run-manifest assembles and writes the manifest twice (cli.py:743-770). Write → record own stage evidence → re-assemble
  → write again. It works (the second pass picks up manifest.stage.json), but there's no comment explaining it, and it reads like a
  copy-paste bug. This plus finding 1 means a clean run assembles the manifest three times. The self-reference problem ("the manifest
  stage can't fully describe itself") deserves one explicit design note rather than two silent workarounds.

  Overreach / deviations from the emulated factory shape

  These are minor; mostly things to be aware of rather than fix.

  - Extraction runs from the live controlled worktree, not a pinned materialization. extract_required/extract_ad_hoc execute scripts
  with working_directory: controlled_source_repo. Materialization enforces HEAD == resolved ref (workspace.py:278-282), but nothing
  re-verifies the worktree between the separate make invocations, and the manifest hashes controlled scripts at manifest-assembly
  time (manifest.py:295), not execution time. In a clean local run these coincide; as a template for HPC, this TOCTOU seam should be
  a stated limitation.
  - stage_defaults.shell: bash in run.synthetic.yaml:107 is dead config — and actively misleading, since preflight explicitly rejects
  shell interpreters. I'd delete it.
  - The wrapper gate doesn't cover everything that determines behavior. controlled_paths omits src/provenance/__init__.py,
  pyproject.toml, and uv.lock. A dirty uv.lock changes dependency versions of the code doing the hashing/validation, and preflight
  would pass.
  - _stage_command_argv's generic fallback (stages.py:531-534) resolves an unmatched executable against the controlled root for any
  command kind — slightly more permissive than the preflight contract implies, though in practice gated upstream.
  - Preflight writes into runs/{run_id}/provenance/logs/ before prepare-workspace runs. The admission stage creates part of the
  workspace it's guarding. Only on success, so no spec violation, but the ordering is a bit muddled.

  Nits

  - README Expected Repository Pattern (line 136) calls the wrapper provenance-mvp/; everywhere else it's ansible-mvp/.
  - .gitignore ignores *.csv/*.xlsx/*.pptx globally — fine today, but it would silently swallow any future curated fixture in those
  formats; the pending define-artifact-lifecycle-and-git-policy change is the right place to settle that.
  - _producing_stage_for_product (cli.py:637-646) infers producing stage from hardcoded filenames rather than from stage-declared
  outputs; the config already has the linkage, so this will silently return None for any product added via the documented extension
  path.

  Nothing here reads as scope creep beyond the emulated-data-factory intent — the mock LSF stage stays metadata-only, no
  archival/warehouse behavior snuck in, and the pending lifecycle proposal correctly stays docs-only. If I were to pick one thing to
  fix before calling this done, it's finding 1: the smoke-then-rewrite loop undermines the core "receipt matches artifact" promise
  the rest of the repo works hard to keep.
