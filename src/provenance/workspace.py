"""Run workspace preparation helpers for the synthetic provenance MVP."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from provenance.git_state import capture_repository_state, resolve_ref
from provenance.hashing import hash_artifact


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
    destination_path: Path
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
            "destination_path": self.destination_path.as_posix(),
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

    if not run_id:
        raise ValueError("run_id must be non-empty")

    root = Path(workspace_root).expanduser().resolve()
    config = _read_yaml_mapping(Path(config_path))
    layout = _mapping(config.get("layout"), "layout")

    run_root = root / _format_layout_path(layout, "run_root", run_id)
    sim_run_root = root / _format_layout_path(layout, "sim_run_root", run_id)
    provenance_root = root / _format_layout_path(layout, "provenance_root", run_id)

    if provenance_root == sim_run_root or provenance_root.is_relative_to(sim_run_root):
        raise ValueError("provenance_root must not be inside sim_run_root")

    simulation_directories = tuple(
        sim_run_root / area
        for area in _string_list(layout.get("simulation_areas"), "layout.simulation_areas")
    )
    provenance_directories = tuple(
        provenance_root / relative_path
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
    sim_run_root = root / _format_layout_path(layout, "sim_run_root", run_id)

    artifacts: list[MaterializedArtifact] = []
    for group in _string_list(
        inputs.get("logical_groups"), "materialization.inputs.logical_groups"
    ):
        for filename in _string_list(inputs.get("files"), "materialization.inputs.files"):
            source_relative = source_root / group / filename
            destination_relative = destination_root / group / filename
            source = controlled_root / source_relative
            destination = sim_run_root.parent / destination_relative
            artifacts.append(
                _copy_controlled_file(
                    root=root,
                    controlled_root=controlled_root,
                    source=source,
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

    return MaterializationResult(run_id=run_id, artifacts=tuple(artifacts))


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
    sim_run_root = root / _format_layout_path(layout, "sim_run_root", run_id)

    artifacts: list[MaterializedArtifact] = []
    for script_name in runtime_script_names:
        script = _mapping(configured_scripts.get(script_name), f"controlled_scripts.{script_name}")
        source_relative = Path(_non_empty_string(script.get("relative_path"), "relative_path"))
        materialized_path = Path(
            _non_empty_string(script.get("materialized_path"), "materialized_path")
        )
        mode = _non_empty_string(script.get("materialization_mode"), "materialization_mode")
        destination = sim_run_root.parent / materialized_path
        artifacts.append(
            _copy_controlled_file(
                root=root,
                controlled_root=controlled_root,
                source=controlled_root / source_relative,
                source_relative=source_relative,
                destination=destination,
                source_ref=controlled_source_ref,
                resolved_commit=resolved_commit,
                head_commit=head_commit,
                mode=mode,
                sim_area="procs",
                logical_group=None,
                role="runtime_script",
            )
        )

    return MaterializationResult(run_id=run_id, artifacts=tuple(artifacts))


def _format_layout_path(layout: dict[str, Any], key: str, run_id: str) -> Path:
    value = layout.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"layout.{key} must be a non-empty string")
    return Path(value.format(run_id=run_id))


def _materialization_context(
    *,
    config_path: Path | str,
    run_id: str,
    controlled_source_repo: Path | str,
    controlled_source_ref: str,
    workspace_root: Path | str,
) -> tuple[Path, Path, str, str | None, dict[str, Any]]:
    if not run_id:
        raise ValueError("run_id must be non-empty")
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
    if controlled_state.head_commit != resolved_commit:
        raise ValueError(
            "controlled source HEAD must match controlled_source_ref before materialization: "
            f"HEAD={controlled_state.head_commit}, ref={resolved_commit}"
        )
    return (
        root,
        controlled_state.top_level,
        resolved_commit,
        controlled_state.head_commit,
        _read_yaml_mapping(Path(config_path)),
    )


def _copy_controlled_file(
    *,
    root: Path,
    controlled_root: Path,
    source: Path,
    source_relative: Path,
    destination: Path,
    source_ref: str,
    resolved_commit: str,
    head_commit: str | None,
    mode: str,
    sim_area: str,
    logical_group: str | None,
    role: str,
) -> MaterializedArtifact:
    if not source.is_file():
        raise FileNotFoundError(f"controlled source materialization input is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    hash_record = hash_artifact(destination, display_path=destination.relative_to(root).as_posix())
    return MaterializedArtifact(
        source_repository=controlled_root,
        source_ref=source_ref,
        source_resolved_commit=resolved_commit,
        source_head_commit=head_commit,
        source_path=source_relative,
        destination_path=destination.relative_to(root),
        materialization_mode=mode,
        sha256=hash_record.sha256,
        hash_status=hash_record.status.value,
        sim_area=sim_area,
        logical_group=logical_group,
        role=role,
    )


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}
    return _mapping(loaded, path.as_posix())


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
