"""Local mock-LSF scheduler helpers for the synthetic provenance MVP."""

from __future__ import annotations

import errno
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from provenance.config import read_config_mapping
from provenance.stages import run_synthetic_simulation

LSF_TOOL_NAMES: tuple[str, ...] = ("bsub", "bjobs", "bhist", "bacct")


def submit_mock_lsf_job(
    *,
    config_path: Path | str,
    run_id: str,
    controlled_source_repo: Path | str,
    workspace_root: Path | str = Path("."),
    output: Path | str | None = None,
    tool_resolver: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Submit the local async mock-LSF payload and return submission evidence."""

    context = _scheduler_context(config_path, run_id, workspace_root)
    controlled_root = Path(controlled_source_repo).expanduser().resolve()
    state_path = context["state_path"]
    if _has_live_existing_job(state_path):
        raise ValueError(f"mock LSF job is already live for run_id {run_id!r}: {state_path}")

    stdout_log = context["scheduler_root"] / "stdout.log"
    stderr_log = context["scheduler_root"] / "stderr.log"
    terminal_state_path = context["terminal_state_path"]
    terminal_state_path.unlink(missing_ok=True)
    submitted_at = _utc_now()
    initial_state = {
        "run_id": run_id,
        "scheduler": "mock_lsf",
        "job_id": context["job_id"],
        "state": "RUN",
        "pid": None,
        "process_group_id": None,
        "submitted_at": _format_timestamp(submitted_at),
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "payload_stage_evidence": context["payload_stage_evidence"],
        "stdout_log": _relative(context["root"], stdout_log),
        "stderr_log": _relative(context["root"], stderr_log),
        "terminal_state_path": _relative(context["root"], terminal_state_path),
        "notes": ["Local async mock LSF job submitted; terminal state is wrapper-owned."],
    }
    _write_json(state_path, initial_state)

    wrapper_code = (
        "from pathlib import Path; "
        "from provenance.scheduler import run_mock_lsf_wrapper; "
        "raise SystemExit(run_mock_lsf_wrapper("
        "config_path=Path(%r), run_id=%r, workspace_root=Path(%r), "
        "controlled_source_repo=Path(%r)))"
        % (
            str(Path(config_path).expanduser().resolve()),
            run_id,
            str(context["root"]),
            str(controlled_root),
        )
    )
    with (
        stdout_log.open("w", encoding="utf-8") as stdout_obj,
        stderr_log.open("w", encoding="utf-8") as stderr_obj,
    ):
        process = subprocess.Popen(  # noqa: S603 - invokes this controlled Python package
            [sys.executable, "-c", wrapper_code],
            cwd=context["root"],
            stdout=stdout_obj,
            stderr=stderr_obj,
            start_new_session=True,
        )

    state = _read_json_mapping(state_path)
    if state.get("state") not in _TERMINAL_STATES:
        state["pid"] = process.pid
        state["process_group_id"] = process.pid
        state["process_start_time_ticks"] = _process_start_time_ticks(process.pid)
        _write_json(state_path, state)

    payload = {
        "run_id": run_id,
        "scheduler": "mock_lsf",
        "mode": context["scheduler"]["mode"],
        "emulator_execution_mode": context["scheduler"]["emulator_execution_mode"],
        "real_lsf_required": False,
        "real_lsf_tools": _tool_status(tool_resolver),
        "submission": {
            "job_id": context["job_id"],
            "queue": "mock-local",
            "status": "submitted",
            "state": "RUN",
            "command": "make submit-mock-lsf",
            "payload_command": context["scheduler"]["payload_command"],
            "submitted_at_utc": _format_timestamp(submitted_at),
            "pid": process.pid,
            "process_group_id": process.pid,
            "process_start_time_ticks": state.get("process_start_time_ticks"),
        },
        "metadata_path": _relative(context["root"], context["submission_path"]),
        "job_state_path": _relative(context["root"], state_path),
        "terminal_state_path": _relative(context["root"], terminal_state_path),
        "accounting_path": _relative(context["root"], context["accounting_path"]),
        "sim_run_root": _relative(context["root"], context["sim_run_root"]),
        "provenance_root": _relative(context["root"], context["provenance_root"]),
        "notes": [
            "Mock scheduler metadata only; real LSF commands are not invoked.",
            "Absent bsub, bjobs, bhist, or bacct binaries do not block the synthetic MVP.",
            "Terminal state is written by a scheduler-owned local wrapper process.",
        ],
    }

    output_path = _resolve_scheduler_output(context, output, default=context["submission_path"])
    _write_yaml(output_path, payload)
    return payload


def wait_mock_lsf_job(
    *,
    config_path: Path | str,
    run_id: str,
    workspace_root: Path | str = Path("."),
) -> dict[str, Any]:
    """Wait for the local async mock-LSF job to reach terminal state."""

    context = _scheduler_context(config_path, run_id, workspace_root)
    scheduler = context["scheduler"]
    timeout = float(scheduler["wait_timeout_seconds"])
    interval = float(scheduler["poll_interval_seconds"])
    state_path = context["state_path"]
    if not state_path.is_file():
        raise ValueError(f"mock LSF job state does not exist: {state_path}")

    deadline = time.monotonic() + timeout
    observations: list[dict[str, Any]] = []
    while True:
        current = _read_json_mapping(state_path)
        observations.append(
            {
                "observed_at": _format_timestamp(_utc_now()),
                "state": current.get("state"),
                "pid_alive": _pid_alive(
                    current.get("pid"), current.get("process_start_time_ticks")
                ),
            }
        )
        if current.get("state") in _TERMINAL_STATES:
            current["wait_observations"] = observations
            _write_json(state_path, current)
            return current
        if time.monotonic() >= deadline:
            return _record_timeout(context, current, observations)
        if not _pid_alive(current.get("pid"), current.get("process_start_time_ticks")):
            terminal = _read_optional_json_mapping(context["terminal_state_path"])
            if terminal is not None:
                terminal["wait_observations"] = observations
                _write_json(state_path, terminal)
                return terminal
            current.update(
                {
                    "state": "EXIT",
                    "status_reason": "process_vanished_missing_terminal_state",
                    "finished_at": _format_timestamp(_utc_now()),
                    "wait_observations": observations,
                }
            )
            _write_json(state_path, current)
            return current
        time.sleep(interval)


def collect_mock_lsf_accounting(
    *,
    config_path: Path | str,
    run_id: str,
    workspace_root: Path | str = Path("."),
    output: Path | str | None = None,
) -> dict[str, Any]:
    """Collect final mock-LSF accounting evidence for a terminal job."""

    context = _scheduler_context(config_path, run_id, workspace_root)
    state = _read_json_mapping(context["state_path"])
    if state.get("state") not in _TERMINAL_STATES:
        raise ValueError(f"mock LSF job is not terminal: {state.get('state')}")

    started_at = state.get("started_at")
    finished_at = state.get("finished_at")
    accounting = {
        "run_id": run_id,
        "scheduler": "mock_lsf",
        "job_id": context["job_id"],
        "state": state.get("state"),
        "exit_code": state.get("exit_code"),
        "queue": "mock-local",
        "submitted_at": state.get("submitted_at"),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": _elapsed_seconds(started_at, finished_at),
        "source": "mock_lsf_emulator",
        "job_state_path": _relative(context["root"], context["state_path"]),
        "payload_stage_evidence": state.get("payload_stage_evidence"),
        "future_real_lsf_equivalent": ["bjobs", "bhist", "bacct"],
    }
    output_path = _resolve_scheduler_output(context, output, default=context["accounting_path"])
    _write_yaml(output_path, accounting)
    return accounting


def run_mock_lsf_wrapper(
    *,
    config_path: Path | str,
    run_id: str,
    workspace_root: Path | str,
    controlled_source_repo: Path | str,
) -> int:
    """Run the scheduler-owned payload wrapper and write terminal state files."""

    context = _scheduler_context(config_path, run_id, workspace_root)
    state_path = context["state_path"]
    state = _wait_for_submitted_state_with_pid(state_path)
    started_at = _utc_now()
    state["state"] = "RUN"
    state["started_at"] = _format_timestamp(started_at)
    _write_json(state_path, state)
    try:
        result = run_synthetic_simulation(
            config_path=config_path,
            run_id=run_id,
            workspace_root=workspace_root,
            controlled_source_repo=controlled_source_repo,
        )
        payload_evidence_path = context["root"] / context["payload_stage_evidence"]
        result_payload = result.to_dict()
        result_payload["evidence_path"] = context["payload_stage_evidence"]
        _write_json(payload_evidence_path, result_payload)
        return_code = result.return_code
        terminal_state = "DONE" if result.return_code == 0 and result.status == "pass" else "EXIT"
        finished_value = result.finished_at or _format_timestamp(_utc_now())
        started_value = result.started_at or _format_timestamp(started_at)
    except Exception as exc:  # pragma: no cover - exercised through subprocess tests
        return_code = 1
        terminal_state = "EXIT"
        finished_value = _format_timestamp(_utc_now())
        started_value = _format_timestamp(started_at)
        stderr_log = context["scheduler_root"] / "stderr.log"
        with stderr_log.open("a", encoding="utf-8") as stderr_obj:
            stderr_obj.write(f"mock LSF payload wrapper failed: {exc}\n")
            stderr_obj.write(traceback.format_exc())
    terminal = {
        **state,
        "state": terminal_state,
        "started_at": started_value,
        "finished_at": finished_value,
        "exit_code": return_code,
        "payload_stage_evidence": context["payload_stage_evidence"],
    }
    _write_json(context["terminal_state_path"], terminal)
    _write_json(state_path, terminal)
    return return_code


def write_mock_lsf_metadata(
    *,
    config_path: Path | str,
    run_id: str,
    workspace_root: Path | str = Path("."),
    output: Path | str | None = None,
    tool_resolver: Callable[[str], str | None] = shutil.which,
    controlled_source_repo: Path | str | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias for submitting a mock-LSF job."""

    if controlled_source_repo is None:
        raise ValueError("controlled_source_repo is required for local_async mock LSF submit")
    return submit_mock_lsf_job(
        config_path=config_path,
        run_id=run_id,
        workspace_root=workspace_root,
        controlled_source_repo=controlled_source_repo,
        output=output,
        tool_resolver=tool_resolver,
    )


def _scheduler_context(
    config_path: Path | str, run_id: str, workspace_root: Path | str
) -> dict[str, Any]:
    if not run_id:
        raise ValueError("run_id must be non-empty")
    root = Path(workspace_root).expanduser().resolve()
    config = read_config_mapping(Path(config_path))
    layout = _mapping(config.get("layout"), "layout")
    scheduler = _mapping(config.get("scheduler"), "scheduler")
    run_root = root / _format_layout_path(layout, "run_root", run_id)
    sim_run_root = root / _format_layout_path(layout, "sim_run_root", run_id)
    provenance_root = root / _format_layout_path(layout, "provenance_root", run_id)
    scheduler_root = provenance_root / "scheduler"
    scheduler_root.mkdir(parents=True, exist_ok=True)
    submission_path = run_root / _non_empty_string(
        scheduler.get("metadata_path"), "scheduler.metadata_path"
    )
    return {
        "root": root,
        "config": config,
        "scheduler": scheduler,
        "run_root": run_root,
        "sim_run_root": sim_run_root,
        "provenance_root": provenance_root,
        "scheduler_root": scheduler_root,
        "submission_path": submission_path,
        "state_path": scheduler_root / "job-state.json",
        "terminal_state_path": scheduler_root / "terminal-state.json",
        "accounting_path": scheduler_root / "accounting.yaml",
        "job_id": f"mock-{run_id}",
        "payload_stage_evidence": f"runs/{run_id}/provenance/logs/run_simulation.stage.json",
    }


def _record_timeout(
    context: dict[str, Any], state: dict[str, Any], observations: list[dict[str, Any]]
) -> dict[str, Any]:
    pid = state.get("pid")
    cleanup = _terminate_process_group(pid)
    state.update(
        {
            "state": "TIMEOUT",
            "status_reason": "wait_timeout",
            "finished_at": _format_timestamp(_utc_now()),
            "cleanup": cleanup,
            "wait_observations": observations,
        }
    )
    _write_json(context["state_path"], state)
    return state


def _terminate_process_group(pid: object) -> dict[str, Any]:
    if not isinstance(pid, int) or pid <= 0:
        return {"attempted": False, "reason": "missing_pid"}
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"attempted": True, "signal": "SIGTERM", "result": "not_found"}
    except PermissionError:
        return {"attempted": True, "signal": "SIGTERM", "result": "permission_denied"}
    time.sleep(0.1)
    if _pid_alive(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
            return {"attempted": True, "signal": "SIGKILL", "result": "killed"}
        except ProcessLookupError:
            return {"attempted": True, "signal": "SIGKILL", "result": "not_found"}
        except PermissionError:
            return {"attempted": True, "signal": "SIGKILL", "result": "permission_denied"}
    return {"attempted": True, "signal": "SIGTERM", "result": "terminated"}


def _has_live_existing_job(path: Path) -> bool:
    if not path.is_file():
        return False
    state = _read_json_mapping(path)
    return state.get("state") not in _TERMINAL_STATES and _pid_alive(
        state.get("pid"), state.get("process_start_time_ticks")
    )


_TERMINAL_STATES = {"DONE", "EXIT", "TIMEOUT"}


def _wait_for_submitted_state_with_pid(path: Path) -> dict[str, Any]:
    deadline = time.monotonic() + 5.0
    state = _read_json_mapping(path)
    while state.get("pid") is None and state.get("state") not in _TERMINAL_STATES:
        if time.monotonic() >= deadline:
            raise ValueError(f"mock LSF submit did not publish process identity: {path}")
        time.sleep(0.01)
        state = _read_json_mapping(path)
    return state


def _pid_alive(pid: object, process_start_time_ticks: object = None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    current_start_time = _process_start_time_ticks(pid)
    if isinstance(process_start_time_ticks, int) and current_start_time != process_start_time_ticks:
        return False
    try:
        os.kill(pid, 0)
    except OSError as error:
        return error.errno != errno.ESRCH
    return True


def _process_start_time_ticks(pid: int) -> int | None:
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.is_file():
        return None
    try:
        stat_text = stat_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        fields = stat_text.rsplit(")", maxsplit=1)[1].split()
        # proc_pid_stat(5): starttime is field 22; after removing pid and comm,
        # it is index 19 in the remaining fields.
        return int(fields[19])
    except (IndexError, ValueError):
        return None


def _resolve_scheduler_output(
    context: dict[str, Any], output: Path | str | None, *, default: Path
) -> Path:
    output_path = Path(output) if output is not None else default
    if not output_path.is_absolute():
        output_path = context["root"] / output_path
    sim_run_root = context["sim_run_root"]
    provenance_root = context["provenance_root"]
    if output_path == sim_run_root or output_path.is_relative_to(sim_run_root):
        raise ValueError("scheduler metadata must not be written inside sim_run_root")
    if not (output_path == provenance_root or output_path.is_relative_to(provenance_root)):
        raise ValueError("scheduler metadata must be written under provenance_root")
    return output_path


def _tool_status(tool_resolver: Callable[[str], str | None]) -> dict[str, dict[str, Any]]:
    return {
        name: {"available": (resolved := tool_resolver(name)) is not None, "path": resolved}
        for name in LSF_TOOL_NAMES
    }


def _elapsed_seconds(started_at: object, finished_at: object) -> float | None:
    if not isinstance(started_at, str) or not isinstance(finished_at, str):
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((finish - start).total_seconds(), 6)


def _format_layout_path(layout: dict[str, Any], key: str, run_id: str) -> Path:
    value = layout.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"layout.{key} must be a non-empty string")
    return Path(value.format(run_id=run_id))


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"JSON evidence does not exist: {path}")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON evidence must be a mapping: {path}")
    return loaded


def _read_optional_json_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_json_mapping(path)


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
