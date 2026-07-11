"""Controlled-source preflight gate for the synthetic provenance MVP."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from provenance.config import read_config_mapping, validate_run_configuration
from provenance.git_state import (
    GitStateError,
    ScriptIdentity,
    assert_clean_tracked_files,
    capture_repository_state,
    resolve_ref,
    script_identity,
    selected_tree_artifact_identity,
)


class PreflightError(RuntimeError):
    """Raised when the workflow must not proceed past preflight."""


_SHELL_INTERPRETERS = {"bash", "dash", "ksh", "sh", "zsh"}
_UNSAFE_SHELL_CHARS = frozenset("|&;<>`$()")


@dataclass(frozen=True)
class PreflightResult:
    """Structured preflight evidence for logs and manifests."""

    status: str
    wrapper_repo: dict[str, Any]
    wrapper_factory_definition: list[dict[str, Any]]
    controlled_source_repo: dict[str, Any]
    controlled_scripts: list[dict[str, Any]]
    controlled_artifacts: list[dict[str, Any]]
    stages: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML friendly representation."""

        return {
            "status": self.status,
            "wrapper_repo": self.wrapper_repo,
            "wrapper_factory_definition": self.wrapper_factory_definition,
            "controlled_source_repo": self.controlled_source_repo,
            "controlled_scripts": self.controlled_scripts,
            "controlled_artifacts": self.controlled_artifacts,
            "stages": self.stages,
        }


def run_preflight(
    *,
    config_path: Path | str,
    wrapper_repo: Path | str,
    controlled_source_repo: Path | str,
    controlled_source_ref: str,
    run_id: str = "demo_001",
) -> PreflightResult:
    """Validate repositories, controlled paths, scripts, and stage commands."""

    config = _read_yaml_mapping(Path(config_path))
    wrapper_path = Path(wrapper_repo).expanduser().resolve()
    controlled_path = Path(controlled_source_repo).expanduser().resolve()
    failures: list[str] = []

    wrapper_state = capture_repository_state(wrapper_path)
    controlled_state = capture_repository_state(controlled_path)
    wrapper_repo_root = wrapper_state.top_level or wrapper_path
    controlled_repo_root = controlled_state.top_level or controlled_path

    try:
        validate_run_configuration(
            config,
            workspace_root=wrapper_repo_root,
            controlled_source_root=controlled_repo_root,
            run_id=run_id,
        )
    except ValueError as exc:
        failures.append(f"run configuration is invalid: {exc}")

    if not wrapper_state.exists:
        failures.append(f"wrapper repository path does not exist: {wrapper_state.path}")
    elif not wrapper_state.is_git_worktree:
        failures.append(f"wrapper repository is not a Git worktree: {wrapper_state.path}")

    if not controlled_state.exists:
        failures.append(
            f"controlled source repository path does not exist: {controlled_state.path}"
        )
    elif not controlled_state.is_git_worktree:
        failures.append(
            f"controlled source repository is not a Git worktree: {controlled_state.path}"
        )
    elif not controlled_state.is_clean:
        dirty = ", ".join(entry.path for entry in controlled_state.status_entries)
        failures.append(f"controlled source repository is dirty: {dirty}")

    resolved_ref: str | None = None
    if controlled_state.is_git_worktree:
        try:
            resolved_ref = resolve_ref(controlled_repo_root, controlled_source_ref).resolved_commit
        except GitStateError as exc:
            failures.append(f"controlled source ref failed to resolve: {exc}")

    wrapper_config = _mapping(
        _mapping(config.get("repositories"), "repositories").get("wrapper"), "wrapper"
    )
    wrapper_controlled_paths = _string_list(
        wrapper_config.get("controlled_paths"), "repositories.wrapper.controlled_paths"
    )
    if wrapper_state.is_git_worktree:
        try:
            assert_clean_tracked_files(wrapper_repo_root, wrapper_controlled_paths)
        except GitStateError as exc:
            failures.append(str(exc))
    wrapper_factory_definition = _selected_tree_inventory(
        wrapper_repo_root,
        wrapper_state.head_commit,
        wrapper_controlled_paths,
        role="wrapper_factory_definition",
        failures=failures,
    )

    controlled_scripts, script_identities = _validate_controlled_scripts(
        config, controlled_repo_root, controlled_state.is_git_worktree, failures
    )
    controlled_artifacts = _validate_selected_commit_artifacts(
        config, controlled_repo_root, resolved_ref, failures
    )
    stages = _validate_stages(config, script_identities, failures)
    _validate_scheduler_payload(config, failures)

    if failures:
        raise PreflightError("preflight failed: " + "; ".join(failures))

    return PreflightResult(
        status="pass",
        wrapper_repo={
            "path": wrapper_repo_root.as_posix(),
            "head_commit": wrapper_state.head_commit,
            "clean_policy": wrapper_config.get("clean_policy", "configured_paths_only"),
            "controlled_paths": wrapper_controlled_paths,
        },
        wrapper_factory_definition=wrapper_factory_definition,
        controlled_source_repo={
            "path": controlled_repo_root.as_posix(),
            "ref": controlled_source_ref,
            "resolved_commit": resolved_ref,
            "head_commit": controlled_state.head_commit,
            "is_clean": controlled_state.is_clean,
        },
        controlled_scripts=controlled_scripts,
        controlled_artifacts=controlled_artifacts,
        stages=stages,
    )


def _validate_controlled_scripts(
    config: dict[str, Any],
    controlled_repo_root: Path,
    controlled_repo_is_git: bool,
    failures: list[str],
) -> tuple[list[dict[str, Any]], dict[str, ScriptIdentity]]:
    configured = _mapping(config.get("controlled_scripts"), "controlled_scripts")
    payloads: list[dict[str, Any]] = []
    identities: dict[str, ScriptIdentity] = {}
    for name, raw_spec in configured.items():
        spec = _mapping(raw_spec, f"controlled_scripts.{name}")
        repository = spec.get("repository")
        relative_path = spec.get("relative_path")
        if repository != "controlled_source":
            failures.append(f"controlled script {name} uses unknown repository: {repository}")
            continue
        if not isinstance(relative_path, str) or not relative_path:
            failures.append(f"controlled script {name} is missing relative_path")
            continue
        if not controlled_repo_is_git:
            continue

        try:
            identity = script_identity(controlled_repo_root, relative_path)
        except GitStateError as exc:
            failures.append(f"controlled script {name} failed Git checks: {exc}")
            continue
        identities[name] = identity
        if not identity.exists:
            failures.append(f"controlled script {name} is missing: {relative_path}")
        elif not identity.is_tracked:
            failures.append(f"controlled script {name} is untracked: {relative_path}")
        elif identity.is_dirty:
            failures.append(f"controlled script {name} is dirty: {relative_path}")
        if bool(spec.get("executable", False)) and not identity.executable:
            failures.append(f"controlled script {name} is not executable: {relative_path}")
        payloads.append(
            {
                "name": name,
                "repository": repository,
                "relative_path": identity.relative_path,
                "blob_oid": identity.blob_oid,
                "file_mode": identity.file_mode,
                "executable": identity.executable,
                "is_usable": identity.is_usable,
            }
        )
    return payloads, identities


def _selected_tree_inventory(
    repository: Path,
    selected_commit: str | None,
    relative_paths: list[str],
    *,
    role: str,
    failures: list[str],
) -> list[dict[str, Any]]:
    if selected_commit is None:
        return []
    records: list[dict[str, Any]] = []
    for relative_path in relative_paths:
        try:
            identity = selected_tree_artifact_identity(repository, selected_commit, relative_path)
        except GitStateError as exc:
            failures.append(f"{role} failed selected-commit checks: {exc}")
            continue
        record: dict[str, Any] = identity.to_dict()
        record["role"] = role
        records.append(record)
    return records


def _validate_selected_commit_artifacts(
    config: dict[str, Any],
    controlled_repo_root: Path,
    selected_commit: str | None,
    failures: list[str],
) -> list[dict[str, Any]]:
    if selected_commit is None:
        return []

    declarations: list[tuple[str, str, str | None]] = []
    scripts = _mapping(config.get("controlled_scripts"), "controlled_scripts")
    for name, raw_script in scripts.items():
        script = _mapping(raw_script, f"controlled_scripts.{name}")
        relative_path = script.get("relative_path")
        if isinstance(relative_path, str) and relative_path:
            declarations.append((relative_path, "controlled_script", str(name)))

    materialization = _mapping(config.get("materialization"), "materialization")
    inputs = _mapping(materialization.get("inputs"), "materialization.inputs")
    source_root = Path(_non_empty_string(inputs.get("source_root"), "source_root"))
    for group in _string_list(
        inputs.get("logical_groups"), "materialization.inputs.logical_groups"
    ):
        for filename in _string_list(inputs.get("files"), "materialization.inputs.files"):
            declarations.append(((source_root / group / filename).as_posix(), "input", group))

    artifacts: list[dict[str, Any]] = []
    for relative_path, role, logical_group in declarations:
        try:
            identity = selected_tree_artifact_identity(
                controlled_repo_root, selected_commit, relative_path
            )
        except GitStateError as exc:
            failures.append(f"controlled {role} failed selected-commit checks: {exc}")
            continue
        payload: dict[str, Any] = identity.to_dict()
        payload.update({"role": role, "logical_group": logical_group})
        artifacts.append(payload)
    return artifacts


def _validate_stages(
    config: dict[str, Any],
    script_identities: dict[str, ScriptIdentity],
    failures: list[str],
) -> list[dict[str, Any]]:
    approved_paths = _mapping(config.get("approved_command_paths"), "approved_command_paths")
    stages = _list(config.get("stages"), "stages")
    payloads: list[dict[str, Any]] = []
    controlled_script_names = set(_mapping(config.get("controlled_scripts"), "controlled_scripts"))

    for index, raw_stage in enumerate(stages):
        stage = _mapping(raw_stage, f"stages[{index}]")
        name = str(stage.get("name") or f"#{index}")
        kind = stage.get("command_kind")
        approved_path = stage.get("approved_command_path")
        if not isinstance(approved_path, str) or not approved_path:
            failures.append(f"stage {name} is missing approved_command_path")
            continue

        repo_key = _stage_repository_key(str(kind))
        if repo_key is None:
            failures.append(f"stage {name} has unknown command_kind: {kind}")
            continue
        repo_approved_paths = set(
            _string_list(approved_paths.get(repo_key), f"approved_command_paths.{repo_key}")
        )
        if approved_path not in repo_approved_paths:
            failures.append(
                f"stage {name} uses uncontrolled approved_command_path "
                f"for {repo_key}: {approved_path}"
            )

        command = stage.get("command")
        if isinstance(command, str) and command:
            _validate_command_matches_approved_path(
                name, str(kind), command, approved_path, failures
            )
        else:
            failures.append(f"stage {name} is missing command")

        expected_scripts = _string_list(
            stage.get("expected_controlled_scripts", []),
            f"stages[{index}].expected_controlled_scripts",
        )
        for script_name in expected_scripts:
            if script_name not in controlled_script_names:
                failures.append(f"stage {name} references unknown controlled script: {script_name}")
            elif script_name not in script_identities:
                failures.append(
                    f"stage {name} references unusable controlled script: {script_name}"
                )

        payloads.append(
            {
                "name": name,
                "command_kind": kind,
                "approved_command_path": approved_path,
                "expected_controlled_scripts": expected_scripts,
            }
        )
    return payloads


def _validate_scheduler_payload(config: dict[str, Any], failures: list[str]) -> None:
    if "scheduler" not in config:
        return
    scheduler = _mapping(config.get("scheduler"), "scheduler")
    payload_stage_name = scheduler.get("payload_stage")
    if not isinstance(payload_stage_name, str) or not payload_stage_name:
        failures.append("scheduler.payload_stage must identify the controlled payload stage")
        return

    payload_stage: dict[str, Any] | None = None
    for raw_stage in _list(config.get("stages"), "stages"):
        stage = _mapping(raw_stage, "stages[]")
        if stage.get("name") == payload_stage_name:
            payload_stage = stage
            break
    if payload_stage is None:
        failures.append(f"scheduler payload stage is not configured: {payload_stage_name}")
        return

    expected_values = {
        "command": scheduler.get("payload_command"),
        "command_kind": scheduler.get("payload_command_kind"),
        "approved_command_path": scheduler.get("payload_approved_command_path"),
    }
    for field_name, expected in expected_values.items():
        if payload_stage.get(field_name) != expected:
            failures.append(
                f"scheduler payload {field_name} does not match stage {payload_stage_name}: "
                f"{expected!r} != {payload_stage.get(field_name)!r}"
            )

    if payload_stage.get("command_kind") not in {
        "controlled_source_script",
        "materialized_controlled_script",
    }:
        failures.append(
            f"scheduler payload stage {payload_stage_name} must resolve to controlled workflow code"
        )

    approved_paths = _mapping(config.get("approved_command_paths"), "approved_command_paths")
    controlled_paths = set(
        _string_list(
            approved_paths.get("controlled_source"), "approved_command_paths.controlled_source"
        )
    )
    approved_path = payload_stage.get("approved_command_path")
    if approved_path not in controlled_paths:
        failures.append(
            f"scheduler payload stage {payload_stage_name} uses uncontrolled path: {approved_path}"
        )


def _validate_command_matches_approved_path(
    name: str, kind: str, command: str, approved_path: str, failures: list[str]
) -> None:
    tokens = _validate_simple_command(name, command, failures)
    if not tokens:
        return
    first_token = tokens[0]
    if kind == "wrapper_make_target":
        if first_token != "make" or approved_path != "Makefile":
            failures.append(f"stage {name} is not constrained to the wrapper Makefile")
    elif kind == "controlled_source_script":
        if first_token != approved_path:
            failures.append(
                f"stage {name} command path {first_token} "
                f"does not match approved path {approved_path}"
            )
    elif kind == "materialized_controlled_script":
        if first_token.removeprefix("sim-run-root/") != approved_path:
            failures.append(
                f"stage {name} materialized command {first_token} does not map to {approved_path}"
            )


def _validate_simple_command(name: str, command: str, failures: list[str]) -> list[str] | None:
    """Validate a configured stage command is executable-plus-arguments only."""

    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        failures.append(f"stage {name} command is not parseable: {exc}")
        return None

    if not tokens:
        failures.append(f"stage {name} command is empty")
        return None

    if any(char in command for char in _UNSAFE_SHELL_CHARS):
        failures.append(
            f"stage {name} command uses shell-style syntax; "
            "only simple executable-plus-arguments commands are allowed"
        )

    executable_name = Path(tokens[0]).name
    if executable_name in _SHELL_INTERPRETERS:
        failures.append(
            f"stage {name} command invokes shell interpreter {tokens[0]}; "
            "configured stage commands must not use shell interpreters"
        )

    return tokens


def _stage_repository_key(kind: str) -> str | None:
    if kind == "wrapper_make_target":
        return "wrapper"
    if kind in {"controlled_source_script", "materialized_controlled_script"}:
        return "controlled_source"
    return None


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    return read_config_mapping(path)


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return value


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value
