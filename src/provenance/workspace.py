"""Run workspace preparation helpers for the synthetic provenance MVP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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


def _format_layout_path(layout: dict[str, Any], key: str, run_id: str) -> Path:
    value = layout.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"layout.{key} must be a non-empty string")
    return Path(value.format(run_id=run_id))


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}
    return _mapping(loaded, path.as_posix())


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(value)
