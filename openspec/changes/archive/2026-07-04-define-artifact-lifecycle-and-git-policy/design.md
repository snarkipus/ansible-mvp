## Design

This change is a policy/design change, not a runtime feature. It establishes vocabulary and boundaries so later implementation work does not blur source control, run evidence, and archival storage.

## Artifact Classes

| Class | Git | Manifest | Archive/Freeze |
|---|---:|---:|---:|
| Factory definition: Makefile, Ansible, Python helpers, config, specs, tests, docs | yes | repository state/reference | optional copy/reference |
| Tiny curated fixtures/examples | yes when intentionally part of scaffold | yes when consumed | yes for frozen demo runs |
| Normal run workspace under `runs/{run_id}/` | no | manifest is the run receipt | optional if frozen |
| Stage logs, scheduler evidence, inventories, validations | no | yes | yes if frozen |
| Raw simulation outputs | no | yes | policy-dependent; may be external reference for large outputs |
| Extracted CSVs and generated reports | no | yes | yes if selected/frozen/promoted |
| Jinja templates and render code | yes | repository state/reference | optional copy/reference |
| Jinja-rendered consumed inputs | no ordinary commits | yes as materialized consumed inputs | yes for frozen runs |

## Lifecycle States

Use these vocabulary candidates for future manifest/schema work:

- `local_only`: exists in the local run workspace; not archived.
- `archived`: copied or packaged into an immutable archive location.
- `promoted`: selected as a delivered output or release artifact.
- `discardable`: safe to remove after debugging or retention window.
- `external_reference`: represented by URI/path plus hash/status instead of copied into the archive.

These names are policy candidates. Schema implementation can refine names, but should preserve the distinctions.

## Candidate Manifest Fields

For artifacts or artifact groups, reserve these concepts:

- `lifecycle_state`
- `archive_status`
- `archive_uri`
- `archive_policy`
- `retention_class`
- `promotion_status`
- `release_labels`
- `external_reference`
- `hash_status`

Future schema work should define exact placement and cardinality.

## Jinja-Rendered Consumed Inputs

Rendered simulation inputs are generated artifacts, but they define exactly what the simulation consumed. Treat them as materialized inputs:

- template and renderer are controlled source;
- external reference files are controlled source with resolved commits and hashes;
- render context is evidence;
- rendered file lives under `sim-run-root/input/`;
- manifest records the rendered file as consumed input evidence;
- frozen archives preserve the exact rendered file.

## Archive/Freeze Direction

A future archive command should be boring and explicit:

- refuse if `manifest.yaml` is missing;
- refuse if manifest smoke validation fails;
- preserve manifest, checksums, validations, logs, inventories, selected products, and exact consumed inputs;
- write an archive README describing run id, source commits, validation status, included products, and inspection/replay notes;
- allow large raw outputs to be represented as external references when production policy requires it.

Do not implement the command in this change.
