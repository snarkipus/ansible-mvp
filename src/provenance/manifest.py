"""Manifest assembly helpers for the provenance-first synthetic MVP.

This module keeps manifest construction explicit and small.  Orchestration code
can collect facts from the other helper modules, pass them here, and receive a
deterministic mapping suitable for writing as ``manifest.yaml``.
"""

from __future__ import annotations

import getpass
import json
import platform
import re
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

import yaml

from provenance.config import read_config_mapping, read_yaml_mapping
from provenance.git_state import capture_repository_state, resolve_ref
from provenance.hashing import HashPolicy, sha256_file
from provenance.paths import resolve_layout_path

ManifestScalar = str | int | float | bool | None
ManifestValue = ManifestScalar | list["ManifestValue"] | dict[str, "ManifestValue"]
ManifestMapping = Mapping[str, ManifestValue]
ManifestDict = dict[str, ManifestValue]

MANIFEST_VERSION = "0.1"
REQUIRED_TOP_LEVEL_SECTIONS: tuple[str, ...] = (
    "manifest_version",
    "run",
    "workflow",
    "repositories",
    "simulation_layout",
    "controlled_source_gate",
    "scheduler",
    "inputs",
    "runtime_scripts",
    "stages",
    "raw_simulation_outputs",
    "derived_products",
    "validations",
    "logs",
    "hash_policy",
    "notes",
)
REQUIRED_NON_EMPTY_KEY_PATHS: tuple[str, ...] = (
    "manifest_version",
    "run.run_id",
    "run.run_root",
    "run.started_at",
    "run.finished_at",
    "run.execution_context",
    "run.execution_context.executed_by",
    "run.execution_context.hostname",
    "run.execution_context.platform",
    "run.execution_context.python_version",
    "run.execution_context.git_version",
    "workflow.operator_flow",
    "workflow.operator_flow[].stage",
    "workflow.operator_flow[].display_name",
    "workflow.operator_flow[].lifecycle_class",
    "workflow.operator_flow[].display_order",
    "workflow.operator_flow[].status",
    "repositories",
    "repositories[].name",
    "repositories[].path",
    "repositories[].resolved_commit",
    "repositories[].worktree_status",
    "simulation_layout.run_root",
    "simulation_layout.sim_run_root",
    "simulation_layout.provenance_root",
    "controlled_source_gate.status",
    "scheduler.mode",
    "inputs",
    "runtime_scripts",
    "stages",
    "stages[].display_name",
    "stages[].lifecycle_class",
    "stages[].display_order",
    "stages[].operator_visible",
    "raw_simulation_outputs",
    "derived_products",
    "validations",
    "validations[].status",
    "logs",
    "hash_policy.algorithm",
    "notes",
)


class SerializableRecord(Protocol):
    """Protocol for helper dataclasses that expose manifest-ready mappings."""

    def to_dict(self) -> Mapping[str, object]:
        """Return a serializable mapping."""
        ...


ManifestRecord = Mapping[str, object] | SerializableRecord | object


@dataclass(frozen=True)
class ManifestAssemblyInput:
    """Facts needed to assemble ``runs/{run_id}/provenance/manifest.yaml``.

    Most fields are intentionally generic so the assembler can be used before
    later orchestration beads finalize on-disk evidence formats. Records from
    ``git_state``, ``inventory``, ``hashing``, and ``validation`` are normalized
    into plain YAML-safe values.
    """

    run: Mapping[str, object]
    repositories: Sequence[ManifestRecord]
    simulation_layout: Mapping[str, object]
    controlled_source_gate: Mapping[str, object]
    scheduler: Mapping[str, object]
    inputs: Sequence[ManifestRecord] = ()
    runtime_scripts: Sequence[ManifestRecord] = ()
    stages: Sequence[ManifestRecord] = ()
    workflow: Mapping[str, object] | None = None
    raw_simulation_outputs: Sequence[ManifestRecord] = ()
    derived_products: Sequence[ManifestRecord] = ()
    validations: Sequence[ManifestRecord] = ()
    logs: Sequence[ManifestRecord] = ()
    hash_policy: Mapping[str, object] | HashPolicy = HashPolicy()
    notes: Sequence[str] = ()
    config: Mapping[str, object] | None = None
    manifest_version: str = MANIFEST_VERSION


def assemble_manifest(input_data: ManifestAssemblyInput) -> ManifestDict:
    """Assemble a deterministic manifest mapping from collected provenance facts."""

    manifest: ManifestDict = {
        "manifest_version": input_data.manifest_version,
        "run": _normalize_mapping(input_data.run),
        "workflow": _normalize_mapping(input_data.workflow or {}),
        "repositories": _normalize_records(input_data.repositories),
        "simulation_layout": _normalize_mapping(input_data.simulation_layout),
        "controlled_source_gate": _normalize_mapping(input_data.controlled_source_gate),
        "scheduler": _normalize_mapping(input_data.scheduler),
        "inputs": _normalize_records(input_data.inputs),
        "runtime_scripts": _normalize_records(input_data.runtime_scripts),
        "stages": _normalize_records(input_data.stages),
        "raw_simulation_outputs": _normalize_records(input_data.raw_simulation_outputs),
        "derived_products": _normalize_records(input_data.derived_products),
        "validations": _normalize_records(input_data.validations),
        "logs": _normalize_records(input_data.logs),
        "hash_policy": _normalize_record(input_data.hash_policy),
        "notes": list(input_data.notes),
    }
    if input_data.config is not None:
        manifest["config"] = _normalize_mapping(input_data.config)
    return manifest


def write_manifest(manifest: Mapping[str, object], path: Path | str) -> Path:
    """Write ``manifest`` as deterministic YAML and return the destination path."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_mapping(manifest)
    with destination.open("w", encoding="utf-8") as file_obj:
        yaml.safe_dump(normalized, file_obj, sort_keys=False)
    return destination


def assemble_run_manifest(
    *,
    config_path: Path | str,
    run_id: str,
    workspace_root: Path | str = Path("."),
    controlled_source_repo: Path | str,
    controlled_source_ref: str,
) -> ManifestDict:
    """Assemble a run manifest from the evidence files written by workflow stages."""

    if not run_id:
        raise ValueError("run_id must be non-empty")

    root = Path(workspace_root).expanduser().resolve()
    config_file = Path(config_path)
    config = read_config_mapping(config_file)
    layout_config = _required_mapping(config, "layout")
    repositories_config = _required_mapping(config, "repositories")
    controlled_scripts_config = _required_mapping(config, "controlled_scripts")
    scheduler_config = _required_mapping(config, "scheduler")

    run_root = resolve_layout_path(root, layout_config, "run_root", run_id)
    sim_run_root = resolve_layout_path(root, layout_config, "sim_run_root", run_id)
    provenance_root = resolve_layout_path(root, layout_config, "provenance_root", run_id)
    inventories_root = provenance_root / "inventories"
    logs_root = provenance_root / "logs"
    validations_root = provenance_root / "validations"

    scheduler_path = run_root / _required_string(scheduler_config, "metadata_path")
    scheduler_root = provenance_root / "scheduler"
    preflight_path = provenance_root / "preflight.json"
    preflight = _read_json_mapping(preflight_path)

    wrapper_repo = _repository_manifest_record(
        name=str(_required_mapping(repositories_config, "wrapper").get("name", "ansible-mvp")),
        path=root,
        requested_ref=None,
    )
    wrapper_factory_definition = preflight.get("wrapper_factory_definition", [])
    if not isinstance(wrapper_factory_definition, list):
        raise ValueError("preflight wrapper_factory_definition must be a list")
    wrapper_repo["factory_definition"] = wrapper_factory_definition
    selected_controlled_artifacts = preflight.get("controlled_artifacts", [])
    if not isinstance(selected_controlled_artifacts, list):
        raise ValueError("preflight controlled_artifacts must be a list")
    controlled_repo = _controlled_repository_manifest_record(
        name=str(
            _required_mapping(repositories_config, "controlled_source").get(
                "name", "controlled-source-demo"
            )
        ),
        path=Path(controlled_source_repo).expanduser().resolve(),
        requested_ref=controlled_source_ref,
        controlled_scripts=controlled_scripts_config,
        selected_artifacts=selected_controlled_artifacts,
    )

    stages = _ordered_stage_records(_read_json_records(logs_root, "*.stage.json"), config)
    logs = _log_records(root, logs_root)
    validations = _validation_records(root, validations_root)
    run_started_at, run_finished_at = _run_time_range(stages)

    assembly_input = ManifestAssemblyInput(
        run={
            "run_id": run_id,
            "description": _required_mapping(config, "run").get("description"),
            "run_root": run_root.relative_to(root).as_posix(),
            "started_at": run_started_at,
            "finished_at": run_finished_at,
            "execution_context": _execution_context(),
        },
        workflow={"operator_flow": _operator_flow(stages)},
        repositories=(wrapper_repo, controlled_repo),
        simulation_layout={
            "run_root": run_root.relative_to(root).as_posix(),
            "sim_run_root": sim_run_root.relative_to(root).as_posix(),
            "provenance_root": provenance_root.relative_to(root).as_posix(),
            "simulation_areas": layout_config.get("simulation_areas", []),
            "canonical_raw_output": layout_config.get("canonical_raw_output"),
        },
        controlled_source_gate=preflight,
        scheduler=_scheduler_manifest_record(
            root=root,
            scheduler_path=scheduler_path,
            scheduler_root=scheduler_root,
            receipt_path=validations_root / "scheduler_receipt.json",
        ),
        inputs=_read_json_list(inventories_root / "pre_run_inputs.json"),
        runtime_scripts=_read_json_list(inventories_root / "pre_run_controlled_scripts.json"),
        stages=stages,
        raw_simulation_outputs=_read_json_list(inventories_root / "post_run_raw_outputs.json"),
        derived_products=_read_json_list(inventories_root / "post_run_derived_products.json"),
        validations=validations,
        logs=logs,
        hash_policy={
            **_required_mapping(config, "hash_policy"),
            "assurance": {
                "capture": "local evidence recorded",
                "binding": "controlled inputs and executed code bound to selected Git commit",
                "preservation": "not implemented; no signing or immutable archive",
            },
        },
        notes=(
            "Synthetic local MVP manifest assembled from workflow evidence files.",
            "Generated products are kept under provenance/ and out of sim-run-root/.",
            "Controlled inputs and executed code are selected-commit-bound.",
            "Evidence is local and mutable; signing, trusted timestamps, and immutable "
            "archival are not implemented.",
        ),
        config={"run_config": config_file.as_posix()},
    )
    return assemble_manifest(assembly_input)


def missing_required_sections(manifest: Mapping[str, object]) -> tuple[str, ...]:
    """Return required top-level sections absent from a manifest mapping."""

    return tuple(section for section in REQUIRED_TOP_LEVEL_SECTIONS if section not in manifest)


def missing_required_key_values(manifest: Mapping[str, object]) -> tuple[str, ...]:
    """Return required key paths whose values are absent or empty.

    The MVP deliberately uses smoke-level validation instead of a full schema. A
    value is considered present when it is not ``None``, an empty string, or an
    empty collection. Paths ending in ``[]`` apply to every record in a required
    non-empty list and report the first missing item by index.
    """

    missing: list[str] = []
    for key_path in REQUIRED_NON_EMPTY_KEY_PATHS:
        missing.extend(_missing_for_key_path(manifest, key_path))
    return tuple(missing)


def semantic_consistency_errors(
    manifest: Mapping[str, object],
    *,
    config_path: Path | str,
    workspace_root: Path | str = Path("."),
) -> tuple[str, ...]:
    """Return semantic contradictions in a purported successful-run manifest."""

    errors: list[str] = []
    root = Path(workspace_root).expanduser().resolve()
    config = read_config_mapping(Path(config_path))
    configured_stages = [
        stage
        for stage in _mapping_records(config.get("stages"))
        if stage.get("name") not in {"manifest", "manifest_smoke"}
    ]
    stages = _mapping_records(manifest.get("stages"))
    expected_names = [str(stage.get("name")) for stage in configured_stages]
    actual_names = [str(stage.get("name")) for stage in stages]
    duplicates = sorted({name for name in actual_names if actual_names.count(name) > 1})
    if duplicates:
        errors.append(f"stages contain duplicate names: {', '.join(duplicates)}")
    if actual_names != expected_names:
        errors.append(
            f"stages must match configured pre-assembly order: expected {expected_names!r}, "
            f"got {actual_names!r}"
        )
    for index, stage in enumerate(stages):
        name = stage.get("name", f"index {index}")
        if stage.get("status") != "pass" or stage.get("return_code") != 0:
            errors.append(f"stage {name!r} must pass with zero return_code")

    for section in ("inputs", "runtime_scripts", "raw_simulation_outputs", "derived_products"):
        for index, record in enumerate(_mapping_records(manifest.get(section))):
            label = f"{section}[{index}]"
            _validate_artifact_record(record, label=label, root=root, errors=errors)

    _validate_repository_artifacts(manifest, errors)
    stage_by_name = {
        str(stage.get("name")): stage for stage in stages if isinstance(stage.get("name"), str)
    }
    for index, product in enumerate(_mapping_records(manifest.get("derived_products"))):
        producer = product.get("producing_stage")
        workflow_path = product.get("workflow_relative_path")
        stage = stage_by_name.get(str(producer))
        outputs = stage.get("outputs") if stage is not None else None
        declared_outputs = {
            output if isinstance(output, str) else output.get("relative_path")
            for output in outputs or []
            if isinstance(output, str | Mapping)
        }
        if stage is None or workflow_path not in declared_outputs:
            errors.append(
                f"derived_products[{index}] producer {producer!r} does not declare output "
                f"{workflow_path!r}"
            )

    validations = _mapping_records(manifest.get("validations"))
    validation_by_path = {
        record.get("path"): record for record in validations if isinstance(record.get("path"), str)
    }
    for name, spec in _required_mapping(config, "validations").items():
        if not isinstance(spec, Mapping):
            continue
        product_path = spec.get("product_path")
        display_path = (
            product_path.removeprefix("provenance/") if isinstance(product_path, str) else None
        )
        validation = validation_by_path.get(display_path)
        if validation is None or validation.get("status") != "pass":
            errors.append(f"configured product validation {name!r} is missing or not successful")
    for index, validation in enumerate(validations):
        if validation.get("status") != "pass":
            errors.append(f"validations[{index}] is not successful")
        if "evidence_path" in validation:
            _validate_artifact_record(
                validation, label=f"validations[{index}]", root=root, errors=errors
            )

    _validate_controlled_source_links(manifest, errors)
    _validate_scheduler_semantics(manifest, errors)
    return tuple(errors)


def _repository_manifest_record(
    *, name: str, path: Path, requested_ref: str | None
) -> dict[str, Any]:
    state = capture_repository_state(path)
    return {
        "name": name,
        "path": state.path.as_posix(),
        "requested_ref": requested_ref,
        "resolved_commit": state.head_commit,
        "head_commit": state.head_commit,
        "branch": state.branch,
        "describe": state.describe,
        "worktree_status": "clean" if state.is_clean else "dirty",
    }


def _controlled_repository_manifest_record(
    *,
    name: str,
    path: Path,
    requested_ref: str,
    controlled_scripts: Mapping[str, object],
    selected_artifacts: Sequence[object],
) -> dict[str, Any]:
    record = _repository_manifest_record(name=name, path=path, requested_ref=requested_ref)
    record["resolved_commit"] = resolve_ref(path, requested_ref).resolved_commit
    script_records: list[dict[str, Any]] = []
    for script_name in controlled_scripts:
        spec = _required_mapping(controlled_scripts, script_name)
        if spec.get("repository") != "controlled_source":
            continue
        relative_path = spec.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError(f"controlled_scripts.{script_name}.relative_path must be non-empty")
        selected = next(
            (
                artifact
                for artifact in selected_artifacts
                if isinstance(artifact, Mapping)
                and artifact.get("role") == "controlled_script"
                and artifact.get("relative_path") == relative_path
            ),
            None,
        )
        if selected is None:
            raise ValueError(f"selected controlled-script identity is missing: {relative_path}")
        script_records.append({"name": script_name, **dict(selected), "hash_status": "hashed"})
    record["tracked_script_paths"] = [script["relative_path"] for script in script_records]
    record["scripts"] = script_records
    record["selected_artifacts"] = list(selected_artifacts)
    return record


def _run_time_range(stages: Sequence[Mapping[str, Any]]) -> tuple[str | None, str | None]:
    starts = [
        value for stage in stages if isinstance(value := stage.get("started_at"), str) and value
    ]
    finishes = [
        value for stage in stages if isinstance(value := stage.get("finished_at"), str) and value
    ]
    return (min(starts) if starts else None, max(finishes) if finishes else None)


def _execution_context() -> dict[str, str]:
    return {
        "executed_by": getpass.getuser(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "git_version": _git_version(),
    }


def _git_version() -> str:
    try:
        completed = subprocess.run(
            ["git", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return completed.stdout.strip() or "unavailable"


def _read_json_records(directory: Path, pattern: str) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    return [_read_json_mapping(path) for path in sorted(directory.glob(pattern))]


def _ordered_stage_records(
    records: Sequence[dict[str, Any]], config: Mapping[str, object]
) -> list[dict[str, Any]]:
    pre_assembly_records = [
        record for record in records if record.get("name") not in {"manifest", "manifest_smoke"}
    ]
    display_order_by_name: dict[str, int] = {}
    for stage in _required_list(config, "stages"):
        if not isinstance(stage, Mapping):
            continue
        name = stage.get("name")
        display_order = stage.get("display_order")
        if isinstance(name, str) and isinstance(display_order, int):
            display_order_by_name[name] = display_order
    return sorted(
        pre_assembly_records,
        key=lambda record: display_order_by_name.get(
            str(record.get("name")), len(pre_assembly_records)
        ),
    )


def _operator_flow(stages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    flow: list[dict[str, Any]] = []
    for stage in stages:
        if stage.get("operator_visible") is not True:
            continue
        flow.append(
            {
                "stage": stage.get("name"),
                "display_name": stage.get("display_name"),
                "lifecycle_class": stage.get("lifecycle_class"),
                "display_order": stage.get("display_order"),
                "status": stage.get("status"),
                "evidence_path": stage.get("evidence_path"),
            }
        )
    return flow


def _scheduler_manifest_record(
    *, root: Path, scheduler_path: Path, scheduler_root: Path, receipt_path: Path
) -> dict[str, Any]:
    submission = _read_yaml_mapping(scheduler_path)
    job_state_path = scheduler_root / "job-state.json"
    terminal_state_path = scheduler_root / "terminal-state.json"
    accounting_path = scheduler_root / "accounting.yaml"
    stdout_log = scheduler_root / "stdout.log"
    stderr_log = scheduler_root / "stderr.log"

    job_state = _read_optional_json_mapping(job_state_path)
    terminal_state = _read_optional_json_mapping(terminal_state_path)
    accounting = _read_optional_yaml_mapping(accounting_path)
    final_record = accounting or terminal_state or job_state or {}

    payload_evidence = _first_string(
        final_record.get("payload_stage_evidence"),
        job_state.get("payload_stage_evidence") if job_state else None,
        submission.get("payload_stage_evidence"),
    )
    job_id = _first_string(
        final_record.get("job_id"),
        job_state.get("job_id") if job_state else None,
        _nested_string(submission, "submission", "job_id"),
    )

    record = dict(submission)
    record.update(
        {
            "job_id": job_id,
            "final_state": _first_string(
                final_record.get("state"), job_state.get("state") if job_state else None
            ),
            "exit_code": final_record.get("exit_code"),
            "evidence": {
                "submission": _relative_path(root, scheduler_path),
                "job_state": _relative_path(root, job_state_path)
                if job_state_path.is_file()
                else None,
                "terminal_state": _relative_path(root, terminal_state_path)
                if terminal_state_path.is_file()
                else None,
                "accounting": _relative_path(root, accounting_path)
                if accounting_path.is_file()
                else None,
                "payload_stage": payload_evidence,
                "stdout_log": _relative_path(root, stdout_log) if stdout_log.is_file() else None,
                "stderr_log": _relative_path(root, stderr_log) if stderr_log.is_file() else None,
            },
            "terminal_job_state": terminal_state,
            "accounting": accounting,
            "receipt_validation": _read_optional_json_mapping(receipt_path),
            "future_real_lsf_equivalent": (accounting or {}).get(
                "future_real_lsf_equivalent", ["bsub", "bjobs", "bhist", "bacct"]
            ),
        }
    )
    return record


def _missing_for_key_path(manifest: Mapping[str, object], key_path: str) -> list[str]:
    current_values: list[object] = [manifest]
    display_paths: list[str] = [""]
    for part in key_path.split("."):
        next_values: list[object] = []
        next_display_paths: list[str] = []
        if part.endswith("[]"):
            key = part[:-2]
            for value, display_path in zip(current_values, display_paths, strict=True):
                if not isinstance(value, Mapping):
                    return [key_path]
                sequence = value.get(key)
                if not _has_non_empty_value(sequence) or not isinstance(sequence, list | tuple):
                    return [_join_key_path(display_path, key)]
                for index, item in enumerate(sequence):
                    next_values.append(item)
                    next_display_paths.append(f"{_join_key_path(display_path, key)}[{index}]")
        else:
            for value, display_path in zip(current_values, display_paths, strict=True):
                if not isinstance(value, Mapping):
                    return [key_path]
                if part not in value or not _has_non_empty_value(value.get(part)):
                    return [_join_key_path(display_path, part)]
                next_values.append(value[part])
                next_display_paths.append(_join_key_path(display_path, part))
        current_values = next_values
        display_paths = next_display_paths
    return []


def _has_non_empty_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping | list | tuple):
        return bool(value)
    return True


def _join_key_path(prefix: str, part: str) -> str:
    return f"{prefix}.{part}" if prefix else part


def _validation_records(root: Path, directory: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not directory.exists():
        return records
    for path in sorted(directory.glob("*.json")):
        record = _read_json_mapping(path)
        record["evidence_path"] = _relative_path(root, path)
        record["sha256"] = sha256_file(path)
        records.append(record)
    return records


def _mapping_records(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [record for record in value if isinstance(record, Mapping)]


def _validate_artifact_record(
    record: Mapping[str, Any], *, label: str, root: Path, errors: list[str]
) -> None:
    relative_path = record.get("run_relative_path", record.get("evidence_path"))
    if not isinstance(relative_path, str) or not relative_path:
        errors.append(f"{label} has no workspace-relative artifact path")
        return
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        errors.append(f"{label} path escapes workspace root: {relative_path!r}")
        return
    digest = record.get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        errors.append(f"{label} has malformed SHA-256: {digest!r}")
        return
    if not path.is_file():
        errors.append(f"{label} artifact is missing: {relative_path}")
    elif sha256_file(path) != digest:
        errors.append(f"{label} SHA-256 does not match on-disk bytes: {relative_path}")


def _validate_controlled_source_links(manifest: Mapping[str, object], errors: list[str]) -> None:
    repositories = _mapping_records(manifest.get("repositories"))
    controlled = next(
        (repository for repository in repositories if repository.get("selected_artifacts")), None
    )
    if controlled is None:
        errors.append("controlled-source repository identity is missing")
        return
    controlled_commit = controlled.get("resolved_commit")
    selected_by_path = {
        record.get("relative_path"): record
        for record in _mapping_records(controlled.get("selected_artifacts"))
        if isinstance(record.get("relative_path"), str)
    }
    for section in ("inputs", "runtime_scripts"):
        for index, artifact in enumerate(_mapping_records(manifest.get(section))):
            identity_value = artifact.get("materialization", artifact)
            identity = identity_value if isinstance(identity_value, Mapping) else {}
            source_path = identity.get("source_path")
            selected = selected_by_path.get(source_path)
            label = f"{section}[{index}]"
            if selected is None:
                errors.append(f"{label} source {source_path!r} has no selected-commit identity")
                continue
            comparisons = (
                ("source_resolved_commit", controlled_commit),
                ("source_resolved_commit", selected.get("selected_commit")),
                ("source_blob_oid", selected.get("blob_oid")),
                ("source_file_mode", selected.get("file_mode")),
                ("source_sha256", selected.get("sha256")),
                ("sha256", identity.get("source_sha256")),
            )
            for field_name, expected in comparisons:
                actual = (
                    artifact.get(field_name) if field_name == "sha256" else identity.get(field_name)
                )
                if actual != expected:
                    errors.append(
                        f"{label} {field_name} does not match linked selected-source identity"
                    )


def _validate_repository_artifacts(manifest: Mapping[str, object], errors: list[str]) -> None:
    for repository_index, repository in enumerate(_mapping_records(manifest.get("repositories"))):
        repository_path = repository.get("path")
        if not isinstance(repository_path, str):
            errors.append(f"repositories[{repository_index}] has no repository path")
            continue
        base = Path(repository_path).expanduser().resolve()
        resolved_commit = repository.get("resolved_commit")
        for collection in ("factory_definition", "selected_artifacts"):
            for artifact_index, artifact in enumerate(_mapping_records(repository.get(collection))):
                label = f"repositories[{repository_index}].{collection}[{artifact_index}]"
                relative_path = artifact.get("relative_path")
                digest = artifact.get("sha256")
                selected_commit = artifact.get("selected_commit")
                if selected_commit != resolved_commit:
                    errors.append(f"{label} selected commit does not match repository identity")
                if not isinstance(relative_path, str) or not relative_path:
                    errors.append(f"{label} has no repository-relative path")
                    continue
                path = (base / relative_path).resolve()
                if not path.is_relative_to(base):
                    errors.append(f"{label} path escapes repository: {relative_path!r}")
                elif not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    errors.append(f"{label} has malformed SHA-256: {digest!r}")
                elif not path.is_file():
                    errors.append(f"{label} artifact is missing: {relative_path}")
                elif sha256_file(path) != digest:
                    errors.append(f"{label} SHA-256 does not match repository bytes")


def _validate_scheduler_semantics(manifest: Mapping[str, object], errors: list[str]) -> None:
    scheduler_value = manifest.get("scheduler")
    scheduler = scheduler_value if isinstance(scheduler_value, Mapping) else {}
    receipt_value = scheduler.get("receipt_validation")
    receipt = receipt_value if isinstance(receipt_value, Mapping) else {}
    if receipt.get("status") != "pass" or receipt.get("errors") not in ([], ()):
        errors.append("scheduler receipt validation is missing or not successful")
    run_value = manifest.get("run")
    run = run_value if isinstance(run_value, Mapping) else {}
    expected_run_id = run.get("run_id")
    expected_job_id = scheduler.get("job_id")
    expected_receipt_id = receipt.get("receipt_id")
    if receipt.get("run_id") != expected_run_id or receipt.get("job_id") != expected_job_id:
        errors.append("scheduler receipt run/job identity does not match manifest")
    for component_name in ("terminal_job_state", "accounting"):
        component_value = scheduler.get(component_name)
        component = component_value if isinstance(component_value, Mapping) else {}
        if (
            component.get("run_id") != expected_run_id
            or component.get("job_id") != expected_job_id
            or component.get("receipt_id") != expected_receipt_id
        ):
            errors.append(f"scheduler {component_name} identity is inconsistent")
        if component.get("state") != "DONE" or component.get("exit_code") != 0:
            errors.append(f"scheduler {component_name} must record DONE with zero exit_code")


def _read_json_list(path: Path) -> list[Any]:
    loaded = _read_json(path)
    if not isinstance(loaded, list):
        raise ValueError(f"JSON evidence must be a list: {path}")
    return loaded


def _read_json_mapping(path: Path) -> dict[str, Any]:
    loaded = _read_json(path)
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON evidence must be a mapping: {path}")
    return loaded


def _read_optional_json_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_json_mapping(path)


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _log_records(root: Path, logs_root: Path) -> list[dict[str, Any]]:
    if not logs_root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(logs_root.glob("*.log")):
        relative = path.relative_to(root).as_posix()
        name_parts = path.name.rsplit(".", 2)
        records.append(
            {
                "path": relative,
                "stage": name_parts[0],
                "stream": name_parts[1] if len(name_parts) == 3 else None,
                "size_bytes": path.stat().st_size,
            }
        )
    return records


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    return read_yaml_mapping(path)


def _read_optional_yaml_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_yaml_mapping(path)


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _nested_string(source: Mapping[str, Any], key: str, nested_key: str) -> str | None:
    nested = source.get(key)
    if not isinstance(nested, Mapping):
        return None
    value = nested.get(nested_key)
    return value if isinstance(value, str) and value else None


def _required_mapping(source: Mapping[str, object], key: str) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    return value


def _required_list(source: Mapping[str, object], key: str) -> list[Any]:
    value = source.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _required_string(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _normalize_records(records: Sequence[ManifestRecord]) -> list[ManifestValue]:
    return [_normalize_record(record) for record in records]


def _normalize_mapping(mapping: Mapping[str, object]) -> ManifestDict:
    return cast(ManifestDict, _normalize_value(mapping))


def _normalize_record(record: ManifestRecord) -> ManifestValue:
    if hasattr(record, "to_dict"):
        return _normalize_value(cast(SerializableRecord, record).to_dict())
    return _normalize_value(record)


def _normalize_value(value: object) -> ManifestValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Enum):
        return cast(ManifestScalar, value.value)
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_normalize_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_value(asdict(value))
    return cast(ManifestScalar, str(value))


__all__ = [
    "MANIFEST_VERSION",
    "REQUIRED_TOP_LEVEL_SECTIONS",
    "ManifestAssemblyInput",
    "assemble_manifest",
    "assemble_run_manifest",
    "missing_required_sections",
    "missing_required_key_values",
    "write_manifest",
]
