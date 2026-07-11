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
    source_category: str = "controlled_artifact"
    destination_category: str = "run_artifact"

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
            "source_category": self.source_category,
            "destination_category": self.destination_category,
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
    run_root = resolve_layout_path(root, layout, "run_root", run_id)
    sim_run_root = resolve_layout_path(root, layout, "sim_run_root", run_id)
    input_root = resolve_root_relative_path(
        sim_run_root, "input", field_name="materialization.inputs designated input area"
    )

    artifacts: list[MaterializedArtifact] = []
    for group in _string_list(
        inputs.get("logical_groups"), "materialization.inputs.logical_groups"
    ):
        for filename in _string_list(inputs.get("files"), "materialization.inputs.files"):
            source_path = resolve_root_relative_path(
                controlled_root,
                source_root / group / filename,
                field_name="materialization.inputs source path",
            )
            source_relative = source_path.relative_to(controlled_root)
            destination = _resolve_materialization_destination(
                run_root,
                destination_root / group / filename,
                designated_root=input_root,
                field_name="materialization.inputs destination path",
            )
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
                    source_category="controlled_input",
                    destination_category="simulation_input",
                )
            )

    result = MaterializationResult(run_id=run_id, artifacts=tuple(artifacts))
    _write_materialization_evidence(root, config, run_id, "materialized_inputs.json", result)
    return result


def verify_materialization_evidence(
    evidence_path: Path | str,
    *,
    workspace_root: Path | str,
    controlled_source_repo: Path | str,
) -> tuple[dict[str, Any], ...]:
    """Verify materialized bytes and modes against preflight-admitted Git identities."""

    path = Path(evidence_path)
    if not path.is_absolute():
        path = Path(workspace_root).expanduser().resolve() / path
    if not path.is_file():
        raise ValueError(f"materialization evidence is missing: {path}")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("artifacts"), list):
        raise ValueError(f"materialization evidence must contain an artifacts list: {path}")

    root = Path(workspace_root).expanduser().resolve()
    preflight_path = path.parent.parent / "preflight.json"
    if not preflight_path.is_file():
        raise ValueError(f"preflight admission evidence is missing: {preflight_path}")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    admitted_raw = preflight.get("controlled_artifacts") if isinstance(preflight, dict) else None
    if not isinstance(admitted_raw, list):
        raise ValueError("preflight admission evidence must contain controlled_artifacts")
    admitted: dict[str, dict[str, Any]] = {}
    for artifact in admitted_raw:
        if not isinstance(artifact, dict):
            raise ValueError("preflight controlled artifact must be a mapping")
        destination = artifact.get("destination_path")
        if not isinstance(destination, str) or not destination:
            raise ValueError("preflight controlled artifact destination_path is incomplete")
        if destination in admitted:
            raise ValueError(f"preflight admits duplicate destination_path: {destination}")
        admitted[destination] = artifact

    inventory_roles = {
        "materialized_inputs.json": {"input"},
        "materialized_runtime_scripts.json": {"runtime_script", "controlled_code"},
    }
    applicable_roles = inventory_roles.get(path.name)
    if applicable_roles is None:
        raise ValueError(f"unknown materialization evidence inventory: {path.name}")
    expected_destinations = {
        destination
        for destination, artifact in admitted.items()
        if artifact.get("role") in applicable_roles
    }
    actual_destinations: list[str] = []
    for artifact in loaded["artifacts"]:
        if not isinstance(artifact, dict):
            raise ValueError(f"materialization artifact must be a mapping: {path}")
        destination = artifact.get("destination_path")
        if not isinstance(destination, str) or not destination:
            raise ValueError(f"materialization artifact destination_path is incomplete: {path}")
        actual_destinations.append(destination)
    duplicate_destinations = sorted(
        destination
        for destination in set(actual_destinations)
        if actual_destinations.count(destination) > 1
    )
    if duplicate_destinations:
        raise ValueError(
            "materialization evidence contains duplicate destination rows: "
            + ", ".join(duplicate_destinations)
        )
    actual_set = set(actual_destinations)
    if actual_set != expected_destinations:
        missing = sorted(expected_destinations - actual_set)
        unexpected = sorted(actual_set - expected_destinations)
        raise ValueError(
            "materialization evidence must cover every applicable preflight-admitted artifact "
            f"exactly once; missing={missing}, unexpected={unexpected}"
        )
    controlled_root = Path(controlled_source_repo).expanduser().resolve()
    verified: list[dict[str, Any]] = []
    for raw_artifact in loaded["artifacts"]:
        destination_value = raw_artifact.get("destination_path")
        admission = admitted.get(destination_value)
        if not isinstance(admission, dict):
            raise ValueError(
                f"materialization artifact was not admitted by preflight: {destination_value}"
            )
        selected_commit = admission.get("selected_commit")
        source_path = admission.get("relative_path")
        if not isinstance(selected_commit, str) or not isinstance(source_path, str):
            raise ValueError(f"preflight artifact identity is incomplete: {destination_value}")
        identity = selected_tree_artifact_identity(controlled_root, selected_commit, source_path)
        immutable_fields = {
            "source_resolved_commit": selected_commit,
            "source_path": source_path,
            "source_blob_oid": identity.blob_oid,
            "source_file_mode": identity.file_mode,
            "source_sha256": identity.sha256,
            "destination_path": admission.get("destination_path"),
            "destination_file_mode": admission.get("destination_file_mode"),
            "materialization_mode": admission.get("materialization_mode"),
            "sim_area": admission.get("sim_area"),
            "logical_group": admission.get("logical_group"),
            "role": admission.get("role"),
            "source_category": admission.get("source_category"),
            "destination_category": admission.get("destination_category"),
        }
        for field, expected in immutable_fields.items():
            if raw_artifact.get(field) != expected:
                raise ValueError(
                    f"materialization inventory disagrees with preflight admission for "
                    f"{destination_value}: {field}"
                )
        expected_hash = identity.sha256
        expected_mode = admission.get("destination_file_mode")
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
    sim_run_root = resolve_layout_path(root, layout, "sim_run_root", run_id)
    provenance_root = resolve_layout_path(root, layout, "provenance_root", run_id)
    runtime_root = resolve_root_relative_path(
        sim_run_root, "procs", field_name="controlled runtime-script designated area"
    )
    controlled_code_root = resolve_root_relative_path(
        provenance_root,
        "controlled-source",
        field_name="controlled-code designated area",
    )

    artifacts: list[MaterializedArtifact] = []
    for script_name in runtime_script_names:
        script = _mapping(configured_scripts.get(script_name), f"controlled_scripts.{script_name}")
        source_path = resolve_root_relative_path(
            controlled_root,
            _non_empty_string(script.get("relative_path"), "relative_path"),
            field_name=f"controlled_scripts.{script_name}.relative_path",
        )
        source_relative = source_path.relative_to(controlled_root)
        materialized_path = Path(
            _non_empty_string(script.get("materialized_path"), "materialized_path")
        )
        mode = _non_empty_string(script.get("materialization_mode"), "materialization_mode")
        role = "runtime_script" if script_name == "run_script" else "controlled_code"
        designated_root = runtime_root if role == "runtime_script" else controlled_code_root
        destination = _resolve_materialization_destination(
            run_root,
            materialized_path,
            designated_root=designated_root,
            field_name=f"controlled_scripts.{script_name}.materialized_path",
        )
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
                logical_group=script_name,
                role=role,
                source_category="controlled_script",
                destination_category=role,
            )
        )

    result = MaterializationResult(run_id=run_id, artifacts=tuple(artifacts))
    _write_materialization_evidence(
        root, config, run_id, "materialized_runtime_scripts.json", result
    )
    return result


def _resolve_materialization_destination(
    run_root: Path,
    candidate: Path | str,
    *,
    designated_root: Path,
    field_name: str,
) -> Path:
    """Resolve a run-relative destination and constrain it to its declared area."""

    destination = resolve_root_relative_path(run_root, candidate, field_name=field_name)
    if not destination.is_relative_to(designated_root):
        raise ValueError(f"{field_name} must be under its designated area: {designated_root}")
    return destination


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
    preflight_path = root / "runs" / run_id / "provenance" / "preflight.json"
    if not preflight_path.is_file():
        raise ValueError(f"preflight admission evidence is missing: {preflight_path}")
    try:
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"preflight admission evidence is unreadable: {preflight_path}") from exc
    admitted_repo = preflight.get("controlled_source_repo") if isinstance(preflight, dict) else None
    if not isinstance(admitted_repo, dict) or preflight.get("status") != "pass":
        raise ValueError(
            "preflight admission evidence does not contain a passed controlled repository"
        )
    admitted_path = admitted_repo.get("path")
    admitted_ref = admitted_repo.get("ref")
    resolved_commit = admitted_repo.get("resolved_commit")
    admitted_head = admitted_repo.get("head_commit")
    if admitted_path != controlled_state.top_level.as_posix():
        raise ValueError("controlled source repository disagrees with preflight admission")
    if admitted_ref != controlled_source_ref:
        raise ValueError("controlled source ref disagrees with preflight admission")
    if not isinstance(resolved_commit, str) or not resolved_commit:
        raise ValueError("preflight controlled source resolved commit is missing")
    # Deliberately do not resolve the caller's ref here: it may have moved after
    # admission. Git object lookup below is pinned to this admitted commit.
    return (
        root,
        controlled_state.top_level,
        resolved_commit,
        admitted_head if isinstance(admitted_head, str) else None,
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
    source_category: str,
    destination_category: str,
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
        source_category=source_category,
        destination_category=destination_category,
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
