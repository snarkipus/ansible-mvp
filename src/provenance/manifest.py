"""Manifest assembly helpers for the provenance-first synthetic MVP.

This module keeps manifest construction explicit and small.  Orchestration code
can collect facts from the other helper modules, pass them here, and receive a
deterministic mapping suitable for writing as ``manifest.yaml``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

import yaml

from provenance.git_state import capture_repository_state, resolve_ref, script_identity
from provenance.hashing import HashPolicy, hash_artifact

ManifestScalar = str | int | float | bool | None
ManifestValue = ManifestScalar | list["ManifestValue"] | dict[str, "ManifestValue"]
ManifestMapping = Mapping[str, ManifestValue]
ManifestDict = dict[str, ManifestValue]

MANIFEST_VERSION = "0.1"
REQUIRED_TOP_LEVEL_SECTIONS: tuple[str, ...] = (
    "manifest_version",
    "run",
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
    config = _read_yaml_mapping(config_file)
    layout_config = _required_mapping(config, "layout")
    repositories_config = _required_mapping(config, "repositories")
    controlled_scripts_config = _required_mapping(config, "controlled_scripts")
    scheduler_config = _required_mapping(config, "scheduler")

    run_root = root / _format_layout_path(layout_config, "run_root", run_id)
    sim_run_root = root / _format_layout_path(layout_config, "sim_run_root", run_id)
    provenance_root = root / _format_layout_path(layout_config, "provenance_root", run_id)
    inventories_root = provenance_root / "inventories"
    logs_root = provenance_root / "logs"
    validations_root = provenance_root / "validations"

    scheduler_path = run_root / _required_string(scheduler_config, "metadata_path")
    preflight_path = provenance_root / "preflight.json"

    wrapper_repo = _repository_manifest_record(
        name=str(_required_mapping(repositories_config, "wrapper").get("name", "ansible-mvp")),
        path=root,
        requested_ref=None,
    )
    controlled_repo = _controlled_repository_manifest_record(
        name=str(
            _required_mapping(repositories_config, "controlled_source").get(
                "name", "controlled-source-demo"
            )
        ),
        path=Path(controlled_source_repo).expanduser().resolve(),
        requested_ref=controlled_source_ref,
        controlled_scripts=controlled_scripts_config,
    )

    stages = _ordered_stage_records(_read_json_records(logs_root, "*.stage.json"), config)
    logs = _log_records(root, logs_root)
    validations = _read_json_records(validations_root, "*.json")

    assembly_input = ManifestAssemblyInput(
        run={
            "run_id": run_id,
            "description": _required_mapping(config, "run").get("description"),
            "run_root": run_root.relative_to(root).as_posix(),
        },
        repositories=(wrapper_repo, controlled_repo),
        simulation_layout={
            "run_root": run_root.relative_to(root).as_posix(),
            "sim_run_root": sim_run_root.relative_to(root).as_posix(),
            "provenance_root": provenance_root.relative_to(root).as_posix(),
            "simulation_areas": layout_config.get("simulation_areas", []),
            "canonical_raw_output": layout_config.get("canonical_raw_output"),
        },
        controlled_source_gate=_read_json_mapping(preflight_path),
        scheduler=_read_yaml_mapping(scheduler_path),
        inputs=_read_json_list(inventories_root / "pre_run_inputs.json"),
        runtime_scripts=_read_json_list(inventories_root / "pre_run_controlled_scripts.json"),
        stages=stages,
        raw_simulation_outputs=_read_json_list(inventories_root / "post_run_raw_outputs.json"),
        derived_products=_read_json_list(inventories_root / "post_run_derived_products.json"),
        validations=validations,
        logs=logs,
        hash_policy=_required_mapping(config, "hash_policy"),
        notes=(
            "Synthetic local MVP manifest assembled from workflow evidence files.",
            "Generated products are kept under provenance/ and out of sim-run-root/.",
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
    *, name: str, path: Path, requested_ref: str, controlled_scripts: Mapping[str, object]
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
        identity = script_identity(path, relative_path)
        hash_result = hash_artifact(identity.absolute_path)
        script_records.append(
            {
                "name": script_name,
                "relative_path": identity.relative_path,
                "repository_commit": identity.repository_commit,
                "blob_oid": identity.blob_oid,
                "sha256": hash_result.sha256,
                "hash_status": hash_result.status.value,
                "file_mode": identity.file_mode,
                "executable": identity.executable,
                "is_tracked": identity.is_tracked,
            }
        )
    record["tracked_script_paths"] = [script["relative_path"] for script in script_records]
    record["scripts"] = script_records
    return record


def _read_json_records(directory: Path, pattern: str) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    return [_read_json_mapping(path) for path in sorted(directory.glob(pattern))]


def _ordered_stage_records(
    records: Sequence[dict[str, Any]], config: Mapping[str, object]
) -> list[dict[str, Any]]:
    configured_names = [
        str(stage.get("name"))
        for stage in _required_list(config, "stages")
        if isinstance(stage, Mapping) and isinstance(stage.get("name"), str)
    ]
    order = {name: index for index, name in enumerate(configured_names)}
    return sorted(records, key=lambda record: order.get(str(record.get("name")), len(order)))


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


def _format_layout_path(layout: Mapping[str, object], key: str, run_id: str) -> Path:
    value = layout.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"layout.{key} must be a non-empty string")
    return Path(value.format(run_id=run_id))


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML input must be a mapping: {path}")
    return loaded


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
