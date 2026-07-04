"""Mock scheduler metadata helpers for the synthetic provenance MVP."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from provenance.config import read_config_mapping

LSF_TOOL_NAMES: tuple[str, ...] = ("bsub", "bjobs", "bhist", "bacct")


def write_mock_lsf_metadata(
    *,
    config_path: Path | str,
    run_id: str,
    workspace_root: Path | str = Path("."),
    output: Path | str | None = None,
    tool_resolver: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Write mock LSF scheduler metadata without requiring real LSF tools.

    The MVP explicitly runs in ``mock_lsf`` mode. Real LSF binaries are recorded
    when present, but their absence is evidence rather than a failure.
    """

    if not run_id:
        raise ValueError("run_id must be non-empty")

    root = Path(workspace_root).expanduser().resolve()
    config = _read_yaml_mapping(Path(config_path))
    layout = _mapping(config.get("layout"), "layout")
    scheduler = _mapping(config.get("scheduler"), "scheduler")

    mode = _non_empty_string(scheduler.get("mode"), "scheduler.mode")
    if mode != "mock_lsf":
        raise ValueError(f"scheduler.mode must be mock_lsf for the MVP: {mode}")
    if bool(scheduler.get("require_real_lsf", False)):
        raise ValueError("scheduler.require_real_lsf must be false for mock_lsf mode")

    run_root = root / _format_layout_path(layout, "run_root", run_id)
    sim_run_root = root / _format_layout_path(layout, "sim_run_root", run_id)
    provenance_root = root / _format_layout_path(layout, "provenance_root", run_id)
    default_metadata_path = run_root / _non_empty_string(
        scheduler.get("metadata_path"), "scheduler.metadata_path"
    )
    output_path = Path(output) if output is not None else default_metadata_path
    if not output_path.is_absolute():
        output_path = root / output_path

    if output_path == sim_run_root or output_path.is_relative_to(sim_run_root):
        raise ValueError("scheduler metadata must not be written inside sim_run_root")
    if not (output_path == provenance_root or output_path.is_relative_to(provenance_root)):
        raise ValueError("scheduler metadata must be written under provenance_root")

    tool_status = {
        name: {"available": (resolved := tool_resolver(name)) is not None, "path": resolved}
        for name in LSF_TOOL_NAMES
    }
    payload: dict[str, Any] = {
        "run_id": run_id,
        "scheduler": "mock_lsf",
        "mode": mode,
        "real_lsf_required": False,
        "real_lsf_tools": tool_status,
        "submission": {
            "job_id": f"mock-{run_id}",
            "queue": "mock-local",
            "status": "submitted",
            "command": "make submit-mock-lsf",
            "submitted_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        },
        "metadata_path": output_path.relative_to(root).as_posix(),
        "sim_run_root": sim_run_root.relative_to(root).as_posix(),
        "provenance_root": provenance_root.relative_to(root).as_posix(),
        "notes": [
            "Mock scheduler metadata only; real LSF commands are not invoked.",
            "Absent bsub, bjobs, bhist, or bacct binaries do not block the synthetic MVP.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return payload


def _format_layout_path(layout: dict[str, Any], key: str, run_id: str) -> Path:
    value = layout.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"layout.{key} must be a non-empty string")
    return Path(value.format(run_id=run_id))


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
