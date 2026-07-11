"""Run workspace preparation helpers for the synthetic provenance MVP."""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from provenance.config import read_config_mapping, validate_run_configuration
from provenance.git_state import (
    SelectedTreeArtifactIdentity,
    capture_repository_state,
    resolve_ref,
    selected_tree_artifact_identity,
)
from provenance.hashing import hash_artifact, sha256_file
from provenance.paths import resolve_layout_path, resolve_root_relative_path, validate_run_id


@dataclass(frozen=True)
class WorkspacePreparationResult:
    """Structured evidence for prepared run and provenance directories."""

    run_id: str
    run_root: Path
    sim_run_root: Path
    provenance_root: Path
    simulation_directories: tuple[Path, ...]
    provenance_directories: tuple[Path, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML friendly representation."""

        return {
            "run_id": self.run_id,
            "run_root": self.run_root.as_posix(),
            "sim_run_root": self.sim_run_root.as_posix(),
            "provenance_root": self.provenance_root.as_posix(),
            "simulation_directories": [path.as_posix() for path in self.simulation_directories],
            "provenance_directories": [path.as_posix() for path in self.provenance_directories],
        }


@dataclass(frozen=True)
class MaterializedArtifact:
    """Evidence for one file copied from controlled source into a run."""

    source_repository: Path
    source_ref: str
    source_resolved_commit: str
    source_head_commit: str | None
    source_path: Path
    source_blob_oid: str
    source_file_mode: str
    source_sha256: str
    destination_path: Path
    destination_file_mode: str
    materialization_mode: str
    sha256: str | None
    hash_status: str
    sim_area: str | None = None
    logical_group: str | None = None
    role: str = "artifact"

    def to_dict(self) -> dict[str, str | None]:
        """Return a JSON/YAML friendly representation."""

        return {
            "source_repository": self.source_repository.as_posix(),
            "source_ref": self.source_ref,
            "source_resolved_commit": self.source_resolved_commit,
            "source_head_commit": self.source_head_commit,
            "source_path": self.source_path.as_posix(),
            "source_blob_oid": self.source_blob_oid,
            "source_file_mode": self.source_file_mode,
            "source_sha256": self.source_sha256,
            "destination_path": self.destination_path.as_posix(),
            "destination_file_mode": self.destination_file_mode,
            "materialization_mode": self.materialization_mode,
            "sha256": self.sha256,
            "hash_status": self.hash_status,
            "sim_area": self.sim_area,
            "logical_group": self.logical_group,
            "role": self.role,
        }


@dataclass(frozen=True)
class MaterializationResult:
    """Structured evidence for a materialization operation."""

    run_id: str
    artifacts: tuple[MaterializedArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML friendly representation."""

        return {
            "run_id": self.run_id,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


def prepare_workspace(
    *,
    config_path: Path | str,
    run_id: str,
    workspace_root: Path | str = Path("."),
) -> WorkspacePreparationResult:
    """Create separated simulation and provenance workspaces for a run."""

    validate_run_id(run_id)
    root = Path(workspace_root).expanduser().resolve()
    config = _read_yaml_mapping(Path(config_path))
    validate_run_configuration(
        config,
        workspace_root=root,
        controlled_source_root=root,
        run_id=run_id,
    )
    layout = _mapping(config.get("layout"), "layout")

    run_root = resolve_layout_path(root, layout, "run_root", run_id)
    sim_run_root = resolve_layout_path(root, layout, "sim_run_root", run_id)
    provenance_root = resolve_layout_path(root, layout, "provenance_root", run_id)

    if provenance_root == sim_run_root or provenance_root.is_relative_to(sim_run_root):
        raise ValueError("provenance_root must not be inside sim_run_root")

    simulation_directories = tuple(
        resolve_root_relative_path(sim_run_root, area, field_name="layout.simulation_areas")
        for area in _string_list(layout.get("simulation_areas"), "layout.simulation_areas")
    )
    provenance_directories = tuple(
        resolve_root_relative_path(
            provenance_root,
            relative_path,
            field_name="layout.provenance_directories",
        )
        for relative_path in _string_list(
            layout.get("provenance_directories"), "layout.provenance_directories"
        )
    )

    run_root.mkdir(parents=True, exist_ok=True)
    sim_run_root.mkdir(parents=True, exist_ok=True)
    provenance_root.mkdir(parents=True, exist_ok=True)
    for directory in (*simulation_directories, *provenance_directories):
        directory.mkdir(parents=True, exist_ok=True)

    return WorkspacePreparationResult(
        run_id=run_id,
        run_root=run_root.relative_to(root),
        sim_run_root=sim_run_root.relative_to(root),
        provenance_root=provenance_root.relative_to(root),
        simulation_directories=tuple(path.relative_to(root) for path in simulation_directories),
        provenance_directories=tuple(path.relative_to(root) for path in provenance_directories),
    )


def materialize_inputs(
    *,
    config_path: Path | str,
    run_id: str,
    controlled_source_repo: Path | str,
    controlled_source_ref: str,
    workspace_root: Path | str = Path("."),
) -> MaterializationResult:
    """Copy configured controlled input fixtures into ``sim-run-root/input``."""

    root, controlled_root, resolved_commit, head_commit, config = _materialization_context(
        config_path=config_path,
        run_id=run_id,
        controlled_source_repo=controlled_source_repo,
        controlled_source_ref=controlled_source_ref,
        workspace_root=workspace_root,
    )
    layout = _mapping(config.get("layout"), "layout")
    materialization = _mapping(config.get("materialization"), "materialization")
    inputs = _mapping(materialization.get("inputs"), "materialization.inputs")
    source_root = Path(_non_empty_string(inputs.get("source_root"), "source_root"))
    destination_root = Path(_non_empty_string(inputs.get("destination_root"), "destination_root"))
    mode = _non_empty_string(inputs.get("mode"), "mode")
    sim_run_root = resolve_layout_path(root, layout, "sim_run_root", run_id)

    artifacts: list[MaterializedArtifact] = []
    for group in _string_list(
        inputs.get("logical_groups"), "materialization.inputs.logical_groups"
    ):
        for filename in _string_list(inputs.get("files"), "materialization.inputs.files"):
            source_relative = source_root / group / filename
            destination_relative = destination_root / group / filename
            destination = sim_run_root.parent / destination_relative
            artifacts.append(
                _materialize_selected_file(
                    root=root,
                    controlled_root=controlled_root,
                    source_relative=source_relative,
                    destination=destination,
                    source_ref=controlled_source_ref,
                    resolved_commit=resolved_commit,
                    head_commit=head_commit,
                    mode=mode,
                    sim_area="input",
                    logical_group=group,
                    role="input",
                )
            )

    result = MaterializationResult(run_id=run_id, artifacts=tuple(artifacts))
    _write_materialization_evidence(root, config, run_id, "materialized_inputs.json", result)
    return result


def verify_materialization_evidence(
    evidence_path: Path | str,
    *,
    workspace_root: Path | str,
) -> tuple[dict[str, Any], ...]:
    """Verify materialized bytes and modes against their selected-tree identities."""

    path = Path(evidence_path)
    if not path.is_absolute():
        path = Path(workspace_root).expanduser().resolve() / path
    if not path.is_file():
        raise ValueError(f"materialization evidence is missing: {path}")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("artifacts"), list):
        raise ValueError(f"materialization evidence must contain an artifacts list: {path}")

    root = Path(workspace_root).expanduser().resolve()
    verified: list[dict[str, Any]] = []
    for raw_artifact in loaded["artifacts"]:
        if not isinstance(raw_artifact, dict):
            raise ValueError(f"materialization artifact must be a mapping: {path}")
        destination_value = raw_artifact.get("destination_path")
        expected_hash = raw_artifact.get("source_sha256")
        expected_mode = raw_artifact.get("destination_file_mode")
        if not all(
            isinstance(value, str) and value for value in (destination_value, expected_hash)
        ):
            raise ValueError(f"materialization artifact identity is incomplete: {path}")
        destination = root / str(destination_value)
        if not destination.is_file():
            raise ValueError(f"materialized artifact is missing: {destination_value}")
        actual_hash = sha256_file(destination)
        if actual_hash != expected_hash:
            raise ValueError(
                f"materialized artifact integrity mismatch: {destination_value}; "
                f"expected {expected_hash}, got {actual_hash}"
            )
        actual_mode = f"{stat.S_IMODE(destination.stat().st_mode):04o}"
        if isinstance(expected_mode, str) and actual_mode != expected_mode:
            raise ValueError(
                f"materialized artifact mode mismatch: {destination_value}; "
                f"expected {expected_mode}, got {actual_mode}"
            )
        verified.append(raw_artifact)
    return tuple(verified)


def _write_materialization_evidence(
    root: Path,
    config: dict[str, Any],
    run_id: str,
    filename: str,
    result: MaterializationResult,
) -> None:
    provenance_root = resolve_layout_path(
        root, _mapping(config.get("layout"), "layout"), "provenance_root", run_id
    )
    path = provenance_root / "inventories" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def materialize_runtime_scripts(
    *,
    config_path: Path | str,
    run_id: str,
    controlled_source_repo: Path | str,
    controlled_source_ref: str,
    workspace_root: Path | str = Path("."),
) -> MaterializationResult:
    """Copy configured runtime scripts into ``sim-run-root/procs``."""

    root, controlled_root, resolved_commit, head_commit, config = _materialization_context(
        config_path=config_path,
        run_id=run_id,
        controlled_source_repo=controlled_source_repo,
        controlled_source_ref=controlled_source_ref,
        workspace_root=workspace_root,
    )
    layout = _mapping(config.get("layout"), "layout")
    configured_scripts = _mapping(config.get("controlled_scripts"), "controlled_scripts")
    runtime_script_names = _string_list(
        _mapping(config.get("materialization"), "materialization").get("runtime_scripts"),
        "materialization.runtime_scripts",
    )
    run_root = resolve_layout_path(root, layout, "run_root", run_id)

    artifacts: list[MaterializedArtifact] = []
    for script_name in runtime_script_names:
        script = _mapping(configured_scripts.get(script_name), f"controlled_scripts.{script_name}")
        source_relative = Path(_non_empty_string(script.get("relative_path"), "relative_path"))
        materialized_path = Path(
            _non_empty_string(script.get("materialized_path"), "materialized_path")
        )
        mode = _non_empty_string(script.get("materialization_mode"), "materialization_mode")
        destination = run_root / materialized_path
        artifacts.append(
            _materialize_selected_file(
                root=root,
                controlled_root=controlled_root,
                source_relative=source_relative,
                destination=destination,
                source_ref=controlled_source_ref,
                resolved_commit=resolved_commit,
                head_commit=head_commit,
                mode=mode,
                sim_area="procs" if materialized_path.parts[0] == "sim-run-root" else None,
                logical_group=None,
                role="runtime_script" if script_name == "run_script" else "controlled_code",
            )
        )

    result = MaterializationResult(run_id=run_id, artifacts=tuple(artifacts))
    _write_materialization_evidence(
        root, config, run_id, "materialized_runtime_scripts.json", result
    )
    return result


def _materialization_context(
    *,
    config_path: Path | str,
    run_id: str,
    controlled_source_repo: Path | str,
    controlled_source_ref: str,
    workspace_root: Path | str,
) -> tuple[Path, Path, str, str | None, dict[str, Any]]:
    validate_run_id(run_id)
    root = Path(workspace_root).expanduser().resolve()
    controlled_state = capture_repository_state(controlled_source_repo)
    if not controlled_state.is_git_worktree or controlled_state.top_level is None:
        raise ValueError(
            f"controlled source repository must be a Git worktree: {controlled_source_repo}"
        )
    if not controlled_state.is_clean:
        dirty = ", ".join(entry.path for entry in controlled_state.status_entries)
        raise ValueError(
            f"controlled source repository must be clean before materialization: {dirty}"
        )
    resolved_commit = resolve_ref(controlled_state.top_level, controlled_source_ref).resolved_commit
    return (
        root,
        controlled_state.top_level,
        resolved_commit,
        controlled_state.head_commit,
        _read_yaml_mapping(Path(config_path)),
    )


def _materialize_selected_file(
    *,
    root: Path,
    controlled_root: Path,
    source_relative: Path,
    destination: Path,
    source_ref: str,
    resolved_commit: str,
    head_commit: str | None,
    mode: str,
    sim_area: str | None,
    logical_group: str | None,
    role: str,
) -> MaterializedArtifact:
    identity: SelectedTreeArtifactIdentity = selected_tree_artifact_identity(
        controlled_root, resolved_commit, source_relative
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(identity.content)
    destination.chmod(0o555 if identity.executable else 0o444)
    hash_record = hash_artifact(destination, display_path=destination.relative_to(root).as_posix())
    if hash_record.sha256 != identity.sha256:
        raise ValueError(
            f"materialized artifact hash differs from selected commit: {source_relative}"
        )
    return MaterializedArtifact(
        source_repository=controlled_root,
        source_ref=source_ref,
        source_resolved_commit=resolved_commit,
        source_head_commit=head_commit,
        source_path=source_relative,
        source_blob_oid=identity.blob_oid,
        source_file_mode=identity.file_mode,
        source_sha256=identity.sha256,
        destination_path=destination.relative_to(root),
        destination_file_mode="0555" if identity.executable else "0444",
        materialization_mode=mode,
        sha256=hash_record.sha256,
        hash_status=hash_record.status.value,
        sim_area=sim_area,
        logical_group=logical_group,
        role=role,
    )


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    return read_config_mapping(path)


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(value)
