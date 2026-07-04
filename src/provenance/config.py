"""Shared configuration loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SUPPORTED_SCHEMA_VERSION = "0.1"


def read_config_mapping(path: Path | str) -> dict[str, Any]:
    """Read a YAML config mapping and enforce the MVP schema version."""

    config_path = Path(path)
    loaded = read_yaml_mapping(config_path)
    schema_version = loaded.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"{config_path.as_posix()} schema_version must be "
            f"{SUPPORTED_SCHEMA_VERSION!r}: {schema_version!r}"
        )
    return loaded


def read_yaml_mapping(path: Path | str) -> dict[str, Any]:
    """Read a YAML mapping without applying config schema validation."""

    config_path = Path(path)
    with config_path.open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML input must be a mapping: {config_path}")
    return loaded
