"""Shared configuration loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from provenance.paths import resolve_layout_path, resolve_root_relative_path, validate_run_id

SUPPORTED_SCHEMA_VERSION = "0.1"
LIFECYCLE_CLASSES = frozenset({"admission", "setup", "evidence", "factory", "finalization"})
WORKING_DIRECTORIES = {
    "wrapper_make_target": "wrapper_repo",
    "controlled_source_script": "controlled_source_repo",
    "materialized_controlled_script": "sim-run-root",
}


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


def validate_run_configuration(
    config: dict[str, Any],
    *,
    workspace_root: Path | str,
    controlled_source_root: Path | str,
    run_id: str,
) -> None:
    """Validate the complete run declaration and all configured path boundaries."""

    validate_run_id(run_id)
    wrapper_root = Path(workspace_root).expanduser().resolve()
    controlled_root = Path(controlled_source_root).expanduser().resolve()
    layout = _mapping(config.get("layout"), "layout")
    run_root = resolve_layout_path(wrapper_root, layout, "run_root", run_id)
    sim_root = resolve_layout_path(wrapper_root, layout, "sim_run_root", run_id)
    provenance_root = resolve_layout_path(wrapper_root, layout, "provenance_root", run_id)
    _require_strict_child(sim_root, run_root, "layout.sim_run_root", "layout.run_root")
    _require_strict_child(provenance_root, run_root, "layout.provenance_root", "layout.run_root")
    if sim_root == provenance_root or sim_root.is_relative_to(provenance_root):
        raise ValueError("layout.sim_run_root must be separate from layout.provenance_root")
    if provenance_root.is_relative_to(sim_root):
        raise ValueError("layout.provenance_root must be separate from layout.sim_run_root")

    for area in _string_list(layout.get("simulation_areas"), "layout.simulation_areas"):
        resolve_root_relative_path(sim_root, area, field_name="layout.simulation_areas")
    for path in _string_list(layout.get("provenance_directories"), "layout.provenance_directories"):
        resolve_root_relative_path(
            provenance_root, path, field_name="layout.provenance_directories"
        )
    raw_output = resolve_root_relative_path(
        sim_root,
        _required_string(layout, "canonical_raw_output", prefix="layout"),
        field_name="layout.canonical_raw_output",
    )
    if not raw_output.is_relative_to(sim_root / "lists"):
        raise ValueError("layout.canonical_raw_output must be under sim-run-root/lists")

    scripts = _mapping(config.get("controlled_scripts"), "controlled_scripts")
    for name, raw_script in scripts.items():
        if not isinstance(name, str) or not name:
            raise ValueError("controlled_scripts names must be non-empty strings")
        script = _mapping(raw_script, f"controlled_scripts.{name}")
        resolve_root_relative_path(
            controlled_root,
            _required_string(script, "relative_path", prefix=f"controlled_scripts.{name}"),
            field_name=f"controlled_scripts.{name}.relative_path",
        )
        materialized_path = script.get("materialized_path")
        if materialized_path is not None:
            resolved = _resolve_run_declared_path(
                run_root,
                sim_root,
                provenance_root,
                materialized_path,
                field_name=f"controlled_scripts.{name}.materialized_path",
                allow_wrapper=False,
                wrapper_root=wrapper_root,
            )
            if not (
                resolved.is_relative_to(sim_root / "procs")
                or resolved.is_relative_to(provenance_root / "controlled-source")
            ):
                raise ValueError(
                    f"controlled_scripts.{name}.materialized_path must be under "
                    "sim-run-root/procs or provenance/controlled-source"
                )

    approved_paths = _mapping(config.get("approved_command_paths"), "approved_command_paths")
    for repository, root in (("wrapper", wrapper_root), ("controlled_source", controlled_root)):
        paths = _unique_string_list(
            approved_paths.get(repository), f"approved_command_paths.{repository}"
        )
        for path in paths:
            resolve_root_relative_path(
                root, path, field_name=f"approved_command_paths.{repository}"
            )

    approved_targets = set(
        _unique_string_list(config.get("approved_make_targets"), "approved_make_targets")
    )
    scheduler = _mapping(config.get("scheduler"), "scheduler")
    scheduler_targets = set(
        _unique_string_list(
            scheduler.get("approved_make_targets"), "scheduler.approved_make_targets"
        )
    )
    if not scheduler_targets.issubset(approved_targets):
        raise ValueError(
            "scheduler.approved_make_targets must be a subset of approved_make_targets"
        )

    _validate_materialization(config, controlled_root, run_root, sim_root, provenance_root, scripts)
    _validate_stage_declarations(
        config,
        wrapper_root=wrapper_root,
        controlled_root=controlled_root,
        run_root=run_root,
        sim_root=sim_root,
        provenance_root=provenance_root,
        approved_targets=approved_targets,
        script_names=set(scripts),
    )
    _validate_support_paths(config, wrapper_root, run_root, sim_root, provenance_root)


def _validate_materialization(
    config: dict[str, Any],
    controlled_root: Path,
    run_root: Path,
    sim_root: Path,
    provenance_root: Path,
    scripts: dict[str, Any],
) -> None:
    materialization = _mapping(config.get("materialization"), "materialization")
    inputs = _mapping(materialization.get("inputs"), "materialization.inputs")
    source_root = _required_string(inputs, "source_root", prefix="materialization.inputs")
    destination_root = _required_string(inputs, "destination_root", prefix="materialization.inputs")
    groups = _unique_string_list(
        inputs.get("logical_groups"), "materialization.inputs.logical_groups"
    )
    files = _unique_string_list(inputs.get("files"), "materialization.inputs.files")
    if inputs.get("mode") != "copy_from_controlled_source":
        raise ValueError("materialization.inputs.mode must be 'copy_from_controlled_source'")
    for group in groups:
        for filename in files:
            resolve_root_relative_path(
                controlled_root,
                Path(source_root) / group / filename,
                field_name="materialization.inputs source path",
            )
            destination = _resolve_run_declared_path(
                run_root,
                sim_root,
                provenance_root,
                Path(destination_root) / group / filename,
                field_name="materialization.inputs destination path",
                allow_wrapper=False,
                wrapper_root=run_root,
            )
            if not destination.is_relative_to(sim_root / "input"):
                raise ValueError(
                    "materialization.inputs destination paths must be under sim-run-root/input"
                )

    runtime_scripts = _unique_string_list(
        materialization.get("runtime_scripts"), "materialization.runtime_scripts"
    )
    for name in runtime_scripts:
        if name not in scripts:
            raise ValueError(f"materialization.runtime_scripts references unknown script: {name}")
        script = _mapping(scripts[name], f"controlled_scripts.{name}")
        if script.get("materialization_mode") != "copy_from_controlled_source":
            raise ValueError(
                f"controlled_scripts.{name}.materialization_mode must be "
                "'copy_from_controlled_source'"
            )
        if not isinstance(script.get("materialized_path"), str):
            raise ValueError(f"controlled_scripts.{name}.materialized_path is required")


def _validate_stage_declarations(
    config: dict[str, Any],
    *,
    wrapper_root: Path,
    controlled_root: Path,
    run_root: Path,
    sim_root: Path,
    provenance_root: Path,
    approved_targets: set[str],
    script_names: set[str],
) -> None:
    stages = _list(config.get("stages"), "stages")
    if not stages:
        raise ValueError("stages must not be empty")
    names: set[str] = set()
    display_orders: set[int] = set()
    for index, raw_stage in enumerate(stages):
        stage = _mapping(raw_stage, f"stages[{index}]")
        prefix = f"stages[{index}]"
        name = _required_string(stage, "name", prefix=prefix)
        if name in names:
            raise ValueError(f"stages contains duplicate name: {name}")
        names.add(name)
        _required_string(stage, "display_name", prefix=prefix)
        lifecycle = _required_string(stage, "lifecycle_class", prefix=prefix)
        if lifecycle not in LIFECYCLE_CLASSES:
            raise ValueError(f"{prefix}.lifecycle_class is unknown: {lifecycle}")
        display_order = stage.get("display_order")
        if not isinstance(display_order, int) or isinstance(display_order, bool):
            raise ValueError(f"{prefix}.display_order must be an integer")
        if display_order in display_orders:
            raise ValueError(f"stages contains duplicate display_order: {display_order}")
        display_orders.add(display_order)
        if not isinstance(stage.get("operator_visible"), bool):
            raise ValueError(f"{prefix}.operator_visible must be a boolean")

        kind = _required_string(stage, "command_kind", prefix=prefix)
        expected_working_directory = WORKING_DIRECTORIES.get(kind)
        if expected_working_directory is None:
            raise ValueError(f"{prefix}.command_kind is unknown: {kind}")
        working_directory = _required_string(stage, "working_directory", prefix=prefix)
        if working_directory != expected_working_directory:
            raise ValueError(
                f"{prefix}.working_directory must be {expected_working_directory!r} for {kind}"
            )
        command = _required_string(stage, "command", prefix=prefix)
        if kind == "wrapper_make_target":
            tokens = command.split()
            if len(tokens) != 2 or tokens[0] != "make" or tokens[1] not in approved_targets:
                raise ValueError(f"{prefix}.command must be exactly 'make <approved target>'")

        expected_scripts = _unique_string_list(
            stage.get("expected_controlled_scripts", []),
            f"{prefix}.expected_controlled_scripts",
        )
        unknown_scripts = set(expected_scripts).difference(script_names)
        if unknown_scripts:
            raise ValueError(
                f"{prefix}.expected_controlled_scripts references unknown script(s): "
                + ", ".join(sorted(unknown_scripts))
            )
        for field in ("inputs", "outputs"):
            for path in _unique_string_list(stage.get(field, []), f"{prefix}.{field}"):
                _resolve_run_declared_path(
                    run_root,
                    sim_root,
                    provenance_root,
                    path,
                    field_name=f"{prefix}.{field}",
                    allow_wrapper=field == "inputs",
                    wrapper_root=wrapper_root,
                )
        for path in _unique_string_list(
            stage.get("expected_inputs", []), f"{prefix}.expected_inputs"
        ):
            resolve_root_relative_path(
                controlled_root, path, field_name=f"{prefix}.expected_inputs"
            )


def _validate_support_paths(
    config: dict[str, Any],
    wrapper_root: Path,
    run_root: Path,
    sim_root: Path,
    provenance_root: Path,
) -> None:
    scheduler = _mapping(config.get("scheduler"), "scheduler")
    scheduler_path = _resolve_run_declared_path(
        run_root,
        sim_root,
        provenance_root,
        _required_string(scheduler, "metadata_path", prefix="scheduler"),
        field_name="scheduler.metadata_path",
        allow_wrapper=False,
        wrapper_root=wrapper_root,
    )
    if not scheduler_path.is_relative_to(provenance_root / "scheduler"):
        raise ValueError("scheduler.metadata_path must be under provenance/scheduler")

    stage_defaults = _mapping(config.get("stage_defaults"), "stage_defaults")
    log_path = _resolve_run_declared_path(
        run_root,
        sim_root,
        provenance_root,
        _required_string(stage_defaults, "log_directory", prefix="stage_defaults"),
        field_name="stage_defaults.log_directory",
        allow_wrapper=False,
        wrapper_root=wrapper_root,
    )
    if not log_path.is_relative_to(provenance_root):
        raise ValueError("stage_defaults.log_directory must be under provenance_root")

    validations = _mapping(config.get("validations"), "validations")
    for name, raw_validation in validations.items():
        validation = _mapping(raw_validation, f"validations.{name}")
        resolve_root_relative_path(
            wrapper_root,
            _required_string(validation, "config_path", prefix=f"validations.{name}"),
            field_name=f"validations.{name}.config_path",
        )
        product = _resolve_run_declared_path(
            run_root,
            sim_root,
            provenance_root,
            _required_string(validation, "product_path", prefix=f"validations.{name}"),
            field_name=f"validations.{name}.product_path",
            allow_wrapper=False,
            wrapper_root=wrapper_root,
        )
        evidence = _resolve_run_declared_path(
            run_root,
            sim_root,
            provenance_root,
            _required_string(validation, "evidence_path", prefix=f"validations.{name}"),
            field_name=f"validations.{name}.evidence_path",
            allow_wrapper=False,
            wrapper_root=wrapper_root,
        )
        if not product.is_relative_to(provenance_root / "products"):
            raise ValueError(f"validations.{name}.product_path must be under provenance/products")
        if not evidence.is_relative_to(provenance_root / "validations"):
            raise ValueError(
                f"validations.{name}.evidence_path must be under provenance/validations"
            )

    manifest = _mapping(config.get("manifest"), "manifest")
    output = _resolve_run_declared_path(
        run_root,
        sim_root,
        provenance_root,
        _required_string(manifest, "output_path", prefix="manifest"),
        field_name="manifest.output_path",
        allow_wrapper=False,
        wrapper_root=wrapper_root,
    )
    if not output.is_relative_to(provenance_root):
        raise ValueError("manifest.output_path must be under provenance_root")


def _resolve_run_declared_path(
    run_root: Path,
    sim_root: Path,
    provenance_root: Path,
    value: object,
    *,
    field_name: str,
    allow_wrapper: bool,
    wrapper_root: Path,
) -> Path:
    if not isinstance(value, str | Path) or not str(value):
        raise ValueError(f"{field_name} must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must be a relative path without '..': {value}")
    if path.parts and path.parts[0] == "sim-run-root":
        resolved = resolve_root_relative_path(run_root, path, field_name=field_name)
        if not resolved.is_relative_to(sim_root):
            raise ValueError(f"{field_name} must remain under sim_run_root")
        return resolved
    if path.parts and path.parts[0] == "provenance":
        resolved = resolve_root_relative_path(run_root, path, field_name=field_name)
        if not resolved.is_relative_to(provenance_root):
            raise ValueError(f"{field_name} must remain under provenance_root")
        return resolved
    if allow_wrapper:
        return resolve_root_relative_path(wrapper_root, path, field_name=field_name)
    raise ValueError(f"{field_name} must start with sim-run-root/ or provenance/")


def _require_strict_child(path: Path, parent: Path, field: str, parent_field: str) -> None:
    if path == parent or not path.is_relative_to(parent):
        raise ValueError(f"{field} must be strictly inside {parent_field}")


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return value


def _unique_string_list(value: object, name: str) -> list[str]:
    result = _string_list(value, name)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    return result


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
