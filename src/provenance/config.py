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
    scheduler = loaded.get("scheduler")
    if scheduler is not None:
        validate_scheduler_config(scheduler)
    return loaded


def validate_scheduler_config(value: object) -> None:
    """Validate the scheduler section used by the local mock-LSF boundary."""

    if not isinstance(value, dict):
        raise ValueError("scheduler must be a mapping")
    _required_string(value, "mode", expected="mock_lsf")
    _required_string(value, "emulator_execution_mode", expected="local_async")
    _required_string(value, "metadata_path")
    if value.get("require_real_lsf") is not False:
        raise ValueError("scheduler.require_real_lsf must be false")
    _positive_number(value, "poll_interval_seconds")
    _positive_number(value, "wait_timeout_seconds")
    if value["poll_interval_seconds"] > value["wait_timeout_seconds"]:
        raise ValueError("scheduler.poll_interval_seconds must not exceed wait_timeout_seconds")
    _required_string(value, "payload_stage", expected="run_simulation")
    _required_string(value, "payload_command", expected="procs/run-script.sh")
    _required_string(value, "payload_command_kind", expected="materialized_controlled_script")
    _required_string(value, "payload_approved_command_path", expected="procs/run-script.sh")
    delay = value.get("runtime_delay")
    if not isinstance(delay, dict):
        raise ValueError("scheduler.runtime_delay must be a mapping")
    min_seconds = _non_negative_number(delay, "min_seconds", prefix="scheduler.runtime_delay")
    max_seconds = _non_negative_number(delay, "max_seconds", prefix="scheduler.runtime_delay")
    if max_seconds < min_seconds:
        raise ValueError("scheduler.runtime_delay.max_seconds must be >= min_seconds")
    _required_string(
        delay, "jitter", expected="deterministic_run_id", prefix="scheduler.runtime_delay"
    )
    approved_targets = value.get("approved_make_targets")
    if not isinstance(approved_targets, list) or not all(
        isinstance(item, str) and item for item in approved_targets
    ):
        raise ValueError("scheduler.approved_make_targets must be a list of non-empty strings")
    required_targets = {"submit-mock-lsf", "wait-mock-lsf", "collect-mock-lsf"}
    missing = required_targets.difference(approved_targets)
    if missing:
        raise ValueError(
            "scheduler.approved_make_targets missing required target(s): "
            + ", ".join(sorted(missing))
        )


def read_yaml_mapping(path: Path | str) -> dict[str, Any]:
    """Read a YAML mapping without applying config schema validation."""

    config_path = Path(path)
    with config_path.open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML input must be a mapping: {config_path}")
    return loaded


def _required_string(
    source: dict[str, Any], key: str, *, expected: str | None = None, prefix: str = "scheduler"
) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{prefix}.{key} must be a non-empty string")
    if expected is not None and value != expected:
        raise ValueError(f"{prefix}.{key} must be {expected!r}: {value!r}")
    return value


def _positive_number(source: dict[str, Any], key: str) -> float:
    value = source.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"scheduler.{key} must be a positive number")
    return float(value)


def _non_negative_number(source: dict[str, Any], key: str, *, prefix: str) -> float:
    value = source.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{prefix}.{key} must be a non-negative number")
    return float(value)
