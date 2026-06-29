"""Manifest assembly helpers for the provenance-first synthetic MVP.

This module keeps manifest construction explicit and small.  Orchestration code
can collect facts from the other helper modules, pass them here, and receive a
deterministic mapping suitable for writing as ``manifest.yaml``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, Sequence, cast

import yaml

from provenance.hashing import HashPolicy

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


def missing_required_sections(manifest: Mapping[str, object]) -> tuple[str, ...]:
    """Return required top-level sections absent from a manifest mapping."""

    return tuple(section for section in REQUIRED_TOP_LEVEL_SECTIONS if section not in manifest)


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
    "missing_required_sections",
    "write_manifest",
]
