"""Shared run identifier and root-containment policy."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def validate_run_id(run_id: str) -> str:
    """Return a safe run identifier or raise ``ValueError``."""

    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError(
            "run_id must match [A-Za-z0-9][A-Za-z0-9._-]* "
            "and must not contain path separators or traversal"
        )
    return run_id


def resolve_root_relative_path(
    root: Path | str,
    candidate: Path | str,
    *,
    field_name: str,
) -> Path:
    """Resolve a non-empty relative path and require it to remain under ``root``."""

    root_path = Path(root).expanduser().resolve()
    candidate_path = Path(candidate)
    if not str(candidate) or candidate_path == Path("."):
        raise ValueError(f"{field_name} must be a non-empty relative path")
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        raise ValueError(f"{field_name} must be a relative path without '..': {candidate}")

    resolved = (root_path / candidate_path).resolve()
    if not resolved.is_relative_to(root_path):
        raise ValueError(f"{field_name} resolves outside its designated root: {candidate}")
    return resolved


def resolve_layout_path(
    root: Path | str,
    layout: Mapping[str, object],
    key: str,
    run_id: str,
) -> Path:
    """Resolve one configured layout template beneath the workspace root."""

    validate_run_id(run_id)
    value = layout.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"layout.{key} must be a non-empty string")
    try:
        rendered = value.format(run_id=run_id)
    except (IndexError, KeyError, ValueError) as exc:
        raise ValueError(f"layout.{key} is not a valid run_id template: {value}") from exc
    return resolve_root_relative_path(root, rendered, field_name=f"layout.{key}")
