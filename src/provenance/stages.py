"""Executable synthetic workflow stages for the provenance MVP."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from provenance.hashing import hash_artifact
from provenance.inventory import infer_metadata


@dataclass(frozen=True)
class StageArtifact:
    """Evidence for one stage input or output artifact."""

    relative_path: str
    exists: bool
    sim_area: str | None
    logical_group: str | None
    role: str
    sha256: str | None = None
    hash_status: str | None = None

    def to_dict(self) -> dict[str, str | bool | None]:
        """Return a JSON/YAML friendly representation."""

        return {
            "relative_path": self.relative_path,
            "exists": self.exists,
            "sim_area": self.sim_area,
            "logical_group": self.logical_group,
            "role": self.role,
            "sha256": self.sha256,
            "hash_status": self.hash_status,
        }


@dataclass(frozen=True)
class StageResult:
    """Structured evidence for one executed stage."""

    name: str
    command: str
    working_directory: str
    stdout_log: str
    stderr_log: str
    status: str
    return_code: int
    inputs: tuple[StageArtifact, ...]
    outputs: tuple[StageArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML friendly representation."""

        return {
            "name": self.name,
            "command": self.command,
            "working_directory": self.working_directory,
            "logs": {
                "stdout": self.stdout_log,
                "stderr": self.stderr_log,
            },
            "status": self.status,
            "return_code": self.return_code,
            "inputs": [artifact.to_dict() for artifact in self.inputs],
            "outputs": [artifact.to_dict() for artifact in self.outputs],
        }


def run_synthetic_simulation(
    *,
    config_path: Path | str,
    run_id: str,
    controlled_source_repo: Path | str,
    workspace_root: Path | str = Path("."),
) -> StageResult:
    """Execute the configured controlled synthetic simulation stage.

    The stage runs the materialized ``procs/run-script.sh`` from the run's
    ``sim-run-root`` and passes the controlled source engine path through the
    environment. The raw output remains under ``sim-run-root/lists/dirC`` while
    logs and stage evidence are written under the provenance sidecar.
    """

    if not run_id:
        raise ValueError("run_id must be non-empty")

    root = Path(workspace_root).expanduser().resolve()
    controlled_root = Path(controlled_source_repo).expanduser().resolve()
    config = _read_yaml_mapping(Path(config_path))
    layout = _mapping(config.get("layout"), "layout")
    stage = _stage_by_name(config, "run_simulation")
    run_root = root / _format_layout_path(layout, "run_root", run_id)
    sim_run_root = root / _format_layout_path(layout, "sim_run_root", run_id)
    provenance_root = root / _format_layout_path(layout, "provenance_root", run_id)
    log_root = provenance_root / "logs"
    log_root.mkdir(parents=True, exist_ok=True)

    command = _non_empty_string(stage.get("command"), "stages.run_simulation.command")
    working_directory_key = _non_empty_string(
        stage.get("working_directory"), "stages.run_simulation.working_directory"
    )
    working_directory = _working_directory(
        root, sim_run_root, controlled_root, working_directory_key
    )
    argv = _command_argv(command, working_directory, sim_run_root)

    stdout_log = log_root / "run_simulation.stdout.log"
    stderr_log = log_root / "run_simulation.stderr.log"
    env = os.environ.copy()
    env["CONTROLLED_SOURCE_REPO"] = controlled_root.as_posix()
    env["SYNTHETIC_SIM_ENGINE"] = (controlled_root / "scripts/synthetic_sim_engine.sh").as_posix()

    with (
        stdout_log.open("w", encoding="utf-8") as stdout_obj,
        stderr_log.open("w", encoding="utf-8") as stderr_obj,
    ):
        completed = subprocess.run(  # noqa: S603 - command is validated by preflight/config
            argv,
            cwd=working_directory,
            env=env,
            stdout=stdout_obj,
            stderr=stderr_obj,
            check=False,
            text=True,
        )

    inputs = tuple(
        _artifact(_stage_artifact_path(root, run_root, input_path), input_path, include_hash=False)
        for input_path in _stage_paths(stage.get("inputs"), "inputs")
    )
    outputs = tuple(
        _artifact(_stage_artifact_path(root, run_root, output_path), output_path, include_hash=True)
        for output_path in _stage_paths(stage.get("outputs"), "outputs")
    )
    status = (
        "pass" if completed.returncode == 0 and all(output.exists for output in outputs) else "fail"
    )

    return StageResult(
        name="run_simulation",
        command=command,
        working_directory=working_directory.relative_to(root).as_posix(),
        stdout_log=stdout_log.relative_to(root).as_posix(),
        stderr_log=stderr_log.relative_to(root).as_posix(),
        status=status,
        return_code=completed.returncode,
        inputs=inputs,
        outputs=outputs,
    )


def _artifact(path: Path, relative_path: Path, *, include_hash: bool) -> StageArtifact:
    normalized_relative = relative_path.as_posix()
    metadata_path = _metadata_relative_path(relative_path)
    metadata = infer_metadata(metadata_path)
    exists = path.exists()
    hash_record = (
        hash_artifact(path, display_path=normalized_relative) if include_hash and exists else None
    )
    return StageArtifact(
        relative_path=normalized_relative,
        exists=exists,
        sim_area=metadata.sim_area,
        logical_group=metadata.logical_group,
        role=metadata.role,
        sha256=hash_record.sha256 if hash_record is not None else None,
        hash_status=hash_record.status.value if hash_record is not None else None,
    )


def _stage_artifact_path(root: Path, run_root: Path, relative_path: Path) -> Path:
    first = relative_path.parts[0] if relative_path.parts else ""
    if first in {"sim-run-root", "provenance"}:
        return run_root / relative_path
    return root / relative_path


def _metadata_relative_path(relative_path: Path) -> str:
    parts = relative_path.parts
    if "sim-run-root" in parts:
        index = parts.index("sim-run-root")
        return Path(*parts[index + 1 :]).as_posix()
    return relative_path.as_posix()


def _command_argv(command: str, working_directory: Path, sim_run_root: Path) -> list[str]:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("stage command must not be empty")
    executable = Path(argv[0])
    if not executable.is_absolute() and not (working_directory / executable).exists():
        sim_relative = sim_run_root / executable
        if sim_relative.exists():
            argv[0] = sim_relative.as_posix()
    return argv


def _stage_by_name(config: dict[str, Any], name: str) -> dict[str, Any]:
    for stage in _list(config.get("stages"), "stages"):
        stage_mapping = _mapping(stage, "stages[]")
        if stage_mapping.get("name") == name:
            return stage_mapping
    raise ValueError(f"configured stage is missing: {name}")


def _stage_paths(value: object, field_name: str) -> tuple[Path, ...]:
    return tuple(
        Path(path) for path in _string_list(value or [], f"stages.run_simulation.{field_name}")
    )


def _working_directory(
    root: Path, sim_run_root: Path, controlled_root: Path, working_directory: str
) -> Path:
    if working_directory == "wrapper_repo":
        return root
    if working_directory == "sim-run-root":
        return sim_run_root
    if working_directory == "controlled_source_repo":
        return controlled_root
    raise ValueError(f"unknown stage working_directory: {working_directory}")


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


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(value)


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value
