from __future__ import annotations

import hashlib
import json
import stat
import subprocess
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from provenance.cli import main as _cli_main
from provenance.scheduler import (
    collect_mock_lsf_accounting,
    submit_mock_lsf_job,
    validate_scheduler_receipt,
    wait_mock_lsf_job,
    write_mock_lsf_metadata,
)
from provenance.stages import (
    _stage_command_argv,
    run_ad_hoc_extraction,
    run_required_extraction,
    run_synthetic_simulation,
)
from provenance.workspace import (
    MaterializationResult,
    prepare_workspace,
    verify_materialization_evidence,
)
from provenance.workspace import (
    materialize_inputs as _materialize_inputs,
)
from provenance.workspace import (
    materialize_runtime_scripts as _materialize_runtime_scripts,
)


def _admit_materialization(
    *, workspace_root: Path, run_id: str, controlled_source_repo: Path, controlled_source_ref: str
) -> None:
    path = workspace_root / "runs" / run_id / "provenance" / "preflight.json"
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "pass",
                "controlled_source_repo": {
                    "path": controlled_source_repo.resolve().as_posix(),
                    "ref": controlled_source_ref,
                    "resolved_commit": _git(
                        controlled_source_repo, "rev-parse", controlled_source_ref
                    ),
                    "head_commit": _git(controlled_source_repo, "rev-parse", "HEAD"),
                },
            }
        ),
        encoding="utf-8",
    )


def materialize_inputs(**kwargs: Any) -> MaterializationResult:
    _admit_materialization(
        workspace_root=Path(kwargs["workspace_root"]),
        run_id=str(kwargs["run_id"]),
        controlled_source_repo=Path(kwargs["controlled_source_repo"]),
        controlled_source_ref=str(kwargs["controlled_source_ref"]),
    )
    return _materialize_inputs(**kwargs)


def materialize_runtime_scripts(**kwargs: Any) -> MaterializationResult:
    _admit_materialization(
        workspace_root=Path(kwargs["workspace_root"]),
        run_id=str(kwargs["run_id"]),
        controlled_source_repo=Path(kwargs["controlled_source_repo"]),
        controlled_source_ref=str(kwargs["controlled_source_ref"]),
    )
    return _materialize_runtime_scripts(**kwargs)


def main(argv: list[str]) -> int:
    if argv and argv[0] in {"materialize-inputs", "materialize-procs"}:
        values = dict(zip(argv[1::2], argv[2::2], strict=False))
        _admit_materialization(
            workspace_root=Path(values["--workspace-root"]),
            run_id=values["--run-id"],
            controlled_source_repo=Path(values["--controlled-source-repo"]),
            controlled_source_ref=values["--controlled-source-ref"],
        )
    return _cli_main(argv)


def _write_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "layout": {
                    "run_root": "runs/{run_id}",
                    "sim_run_root": "runs/{run_id}/sim-run-root",
                    "provenance_root": "runs/{run_id}/provenance",
                    "simulation_areas": ["input", "lists", "files", "procs"],
                    "provenance_directories": [
                        "logs",
                        "inventories",
                        "scheduler",
                        "validations",
                        "products/extracted",
                        "products/reports",
                    ],
                    "canonical_raw_output": "lists/dirC/sim-out.dat",
                },
                "materialization": {
                    "inputs": {
                        "source_root": "fixtures/controlled_inputs",
                        "destination_root": "sim-run-root/input",
                        "logical_groups": ["dirA", "dirB", "dirC"],
                        "files": ["ex1.dat", "ex2.dat", "ex3.dat"],
                        "mode": "copy_from_controlled_source",
                    },
                    "runtime_scripts": [
                        "run_script",
                        "synthetic_sim_engine",
                        "extract_required",
                        "ad_hoc_extract",
                    ],
                },
                "controlled_scripts": {
                    "run_script": {
                        "relative_path": "procs/run-script.sh",
                        "materialized_path": "sim-run-root/procs/run-script.sh",
                        "materialization_mode": "copy_from_controlled_source",
                    },
                    "synthetic_sim_engine": {
                        "relative_path": "scripts/synthetic_sim_engine.sh",
                        "materialized_path": (
                            "provenance/controlled-source/scripts/synthetic_sim_engine.sh"
                        ),
                        "materialization_mode": "copy_from_controlled_source",
                    },
                    "extract_required": {
                        "relative_path": "scripts/extract_required.pl",
                        "materialized_path": (
                            "provenance/controlled-source/scripts/extract_required.pl"
                        ),
                        "materialization_mode": "copy_from_controlled_source",
                    },
                    "ad_hoc_extract": {
                        "relative_path": "scripts/ad_hoc_extract.py",
                        "materialized_path": (
                            "provenance/controlled-source/scripts/ad_hoc_extract.py"
                        ),
                        "materialization_mode": "copy_from_controlled_source",
                    },
                },
                "approved_command_paths": {
                    "wrapper": ["Makefile"],
                    "controlled_source": [
                        "procs/run-script.sh",
                        "scripts/synthetic_sim_engine.sh",
                        "scripts/extract_required.pl",
                        "scripts/ad_hoc_extract.py",
                    ],
                },
                "approved_make_targets": [
                    "submit-mock-lsf",
                    "wait-mock-lsf",
                    "collect-mock-lsf",
                ],
                "scheduler": {
                    "mode": "mock_lsf",
                    "emulator_execution_mode": "local_async",
                    "metadata_path": "provenance/scheduler/submission.yaml",
                    "require_real_lsf": False,
                    "poll_interval_seconds": 0.1,
                    "wait_timeout_seconds": 1.0,
                    "payload_stage": "run_simulation",
                    "payload_command": "procs/run-script.sh",
                    "payload_command_kind": "materialized_controlled_script",
                    "payload_approved_command_path": "procs/run-script.sh",
                    "runtime_delay": {
                        "min_seconds": 0.0,
                        "max_seconds": 0.0,
                        "jitter": "deterministic_run_id",
                    },
                    "approved_make_targets": [
                        "submit-mock-lsf",
                        "wait-mock-lsf",
                        "collect-mock-lsf",
                    ],
                },
                "stage_defaults": {"log_directory": "provenance/logs"},
                "stages": [
                    {
                        "name": "run_simulation",
                        "display_name": "Run simulation",
                        "lifecycle_class": "factory",
                        "display_order": 60,
                        "operator_visible": True,
                        "command": "procs/run-script.sh",
                        "command_kind": "materialized_controlled_script",
                        "approved_command_path": "procs/run-script.sh",
                        "working_directory": "sim-run-root",
                        "expected_controlled_scripts": [
                            "run_script",
                            "synthetic_sim_engine",
                        ],
                        "inputs": ["sim-run-root/input"],
                        "outputs": ["sim-run-root/lists/dirC/sim-out.dat"],
                    },
                    {
                        "name": "extract_required",
                        "display_name": "Extract required results",
                        "lifecycle_class": "factory",
                        "display_order": 70,
                        "operator_visible": True,
                        "command": (
                            "scripts/extract_required.pl sim-run-root/lists/dirC/sim-out.dat "
                            "provenance/products/extracted/required.csv"
                        ),
                        "working_directory": "controlled_source_repo",
                        "command_kind": "controlled_source_script",
                        "approved_command_path": "scripts/extract_required.pl",
                        "expected_controlled_scripts": ["extract_required"],
                        "inputs": ["sim-run-root/lists/dirC/sim-out.dat"],
                        "outputs": ["provenance/products/extracted/required.csv"],
                    },
                    {
                        "name": "extract_ad_hoc",
                        "display_name": "Extract ad hoc results",
                        "lifecycle_class": "factory",
                        "display_order": 80,
                        "operator_visible": True,
                        "command": (
                            "scripts/ad_hoc_extract.py sim-run-root/lists/dirC/sim-out.dat "
                            "provenance/products/extracted/ad_hoc.csv"
                        ),
                        "working_directory": "controlled_source_repo",
                        "command_kind": "controlled_source_script",
                        "approved_command_path": "scripts/ad_hoc_extract.py",
                        "expected_controlled_scripts": ["ad_hoc_extract"],
                        "inputs": ["sim-run-root/lists/dirC/sim-out.dat"],
                        "outputs": ["provenance/products/extracted/ad_hoc.csv"],
                    },
                ],
                "validations": {
                    "required_extract": {
                        "config_path": "configs/expected_shape.required_extract.yaml",
                        "product_path": "provenance/products/extracted/required.csv",
                        "evidence_path": "provenance/validations/required_extract.json",
                    }
                },
                "manifest": {"output_path": "provenance/manifest.yaml"},
            }
        ),
        encoding="utf-8",
    )


def _set_runtime_delay(path: Path, *, minimum: float, maximum: float, timeout: float = 1.0) -> None:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    scheduler = config["scheduler"]
    assert isinstance(scheduler, dict)
    scheduler["runtime_delay"] = {
        "min_seconds": minimum,
        "max_seconds": maximum,
        "jitter": "deterministic_run_id",
    }
    scheduler["poll_interval_seconds"] = 0.05
    scheduler["wait_timeout_seconds"] = timeout
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _write_scheduler_state(path: Path, run_id: str, state: str) -> None:
    scheduler_root = path / "runs" / run_id / "provenance" / "scheduler"
    scheduler_root.mkdir(parents=True, exist_ok=True)
    (scheduler_root / "job-state.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "scheduler": "mock_lsf",
                "job_id": f"mock-{run_id}",
                "state": state,
                "exit_code": 0 if state == "DONE" else 1,
            }
        ),
        encoding="utf-8",
    )
    (scheduler_root / "accounting.yaml").write_text(
        yaml.safe_dump({"run_id": run_id, "scheduler": "mock_lsf", "state": state}),
        encoding="utf-8",
    )


def _write_successful_scheduler_receipt(path: Path, run_id: str) -> None:
    _write_preflight_admission(path, run_id)
    run_root = path / "runs" / run_id
    scheduler_root = run_root / "provenance" / "scheduler"
    logs_root = run_root / "provenance" / "logs"
    scheduler_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    receipt_id = f"receipt-{run_id}"
    job_id = f"mock-{run_id}"
    submitted_at = "2026-01-01T00:00:00Z"
    started_at = "2026-01-01T00:00:01Z"
    finished_at = "2026-01-01T00:00:02Z"
    accounted_at = "2026-01-01T00:00:03Z"
    payload_path = f"runs/{run_id}/provenance/logs/run_simulation.stage.json"
    raw_output = run_root / "sim-run-root" / "lists" / "dirC" / "sim-out.dat"
    raw_hash = hashlib.sha256(raw_output.read_bytes()).hexdigest()
    state = {
        "receipt_id": receipt_id,
        "run_id": run_id,
        "scheduler": "mock_lsf",
        "mode": "mock_lsf",
        "job_id": job_id,
        "state": "DONE",
        "exit_code": 0,
        "submitted_at": submitted_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "payload_stage_evidence": payload_path,
    }
    (scheduler_root / "submission.yaml").write_text(
        yaml.safe_dump(
            {
                "receipt_id": receipt_id,
                "run_id": run_id,
                "job_id": job_id,
                "scheduler": "mock_lsf",
                "mode": "mock_lsf",
                "metadata_path": f"runs/{run_id}/provenance/scheduler/submission.yaml",
                "job_state_path": f"runs/{run_id}/provenance/scheduler/job-state.json",
                "terminal_state_path": f"runs/{run_id}/provenance/scheduler/terminal-state.json",
                "accounting_path": f"runs/{run_id}/provenance/scheduler/accounting.yaml",
                "submission": {
                    "run_id": run_id,
                    "scheduler": "mock_lsf",
                    "mode": "mock_lsf",
                    "job_id": job_id,
                    "receipt_id": receipt_id,
                    "payload_command": "procs/run-script.sh",
                    "submitted_at_utc": submitted_at,
                },
            }
        ),
        encoding="utf-8",
    )
    for filename in ("job-state.json", "terminal-state.json"):
        (scheduler_root / filename).write_text(json.dumps(state), encoding="utf-8")
    (scheduler_root / "accounting.yaml").write_text(
        yaml.safe_dump(
            {
                **state,
                "accounted_at": accounted_at,
                "job_state_path": f"runs/{run_id}/provenance/scheduler/job-state.json",
                "payload_stage_evidence": payload_path,
            }
        ),
        encoding="utf-8",
    )
    (logs_root / "run_simulation.stage.json").write_text(
        json.dumps(
            {
                "receipt_id": receipt_id,
                "run_id": run_id,
                "job_id": job_id,
                "scheduler": "mock_lsf",
                "mode": "mock_lsf",
                "evidence_path": payload_path,
                "name": "run_simulation",
                "command": "procs/run-script.sh",
                "status": "pass",
                "return_code": 0,
                "started_at": started_at,
                "finished_at": finished_at,
                "outputs": [
                    {
                        "relative_path": "sim-run-root/lists/dirC/sim-out.dat",
                        "sha256": raw_hash,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _prepare_scheduler_payload(
    *,
    config_path: Path,
    run_id: str,
    workspace_root: Path,
    controlled_repo: Path,
    controlled_source_ref: str = "controlled-source-demo-v0.1.2",
) -> None:
    prepare_workspace(config_path=config_path, run_id=run_id, workspace_root=workspace_root)
    materialize_inputs(
        config_path=config_path,
        run_id=run_id,
        workspace_root=workspace_root,
        controlled_source_repo=controlled_repo,
        controlled_source_ref=controlled_source_ref,
    )
    materialize_runtime_scripts(
        config_path=config_path,
        run_id=run_id,
        workspace_root=workspace_root,
        controlled_source_repo=controlled_repo,
        controlled_source_ref=controlled_source_ref,
    )
    _write_preflight_admission(workspace_root, run_id)


def _write_preflight_admission(workspace_root: Path, run_id: str) -> None:
    inventories_root = workspace_root / "runs" / run_id / "provenance" / "inventories"
    admitted = []
    for inventory_name in ("materialized_inputs.json", "materialized_runtime_scripts.json"):
        inventory_path = inventories_root / inventory_name
        if not inventory_path.is_file():
            continue
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        admitted.extend(
            {
                "selected_commit": artifact["source_resolved_commit"],
                "relative_path": artifact["source_path"],
                "blob_oid": artifact["source_blob_oid"],
                "file_mode": artifact["source_file_mode"],
                "sha256": artifact["source_sha256"],
                "destination_path": artifact["destination_path"],
                "destination_file_mode": artifact["destination_file_mode"],
                "role": artifact["role"],
                "materialization_mode": artifact["materialization_mode"],
                "sim_area": artifact["sim_area"],
                "logical_group": artifact["logical_group"],
                "source_category": artifact["source_category"],
                "destination_category": artifact["destination_category"],
            }
            for artifact in inventory["artifacts"]
        )
    preflight_path = inventories_root.parent / "preflight.json"
    preflight = (
        json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.is_file() else {}
    )
    preflight["controlled_artifacts"] = admitted
    preflight_path.write_text(json.dumps(preflight), encoding="utf-8")


def test_prepare_workspace_creates_separated_simulation_and_provenance_dirs(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)

    result = prepare_workspace(
        config_path=config_path,
        run_id="demo_001",
        workspace_root=tmp_path,
    )

    sim_root = tmp_path / "runs/demo_001/sim-run-root"
    provenance_root = tmp_path / "runs/demo_001/provenance"
    for area in ("input", "lists", "files", "procs"):
        assert (sim_root / area).is_dir()
    for relative_path in (
        "logs",
        "inventories",
        "scheduler",
        "validations",
        "products/extracted",
        "products/reports",
    ):
        assert (provenance_root / relative_path).is_dir()

    assert not (sim_root / "provenance").exists()
    assert result.to_dict()["provenance_root"] == "runs/demo_001/provenance"


def test_prepare_workspace_rejects_invalid_config_before_creating_run_root(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["stages"][0]["outputs"] = ["../../outside"]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main(
            [
                "prepare-workspace",
                "--config",
                str(config_path),
                "--run-id",
                "unsafe_config",
                "--workspace-root",
                str(tmp_path),
            ]
        )

    assert error.value.code == 2
    assert not (tmp_path / "runs" / "unsafe_config").exists()


def test_stage_command_argv_resolves_only_controlled_source_script_executables(
    tmp_path: Path,
) -> None:
    controlled_root = tmp_path / "controlled-source-demo"
    controlled_script = controlled_root / "scripts" / "extract_required.pl"
    controlled_script.parent.mkdir(parents=True)
    controlled_script.write_text("#!/usr/bin/env perl\n", encoding="utf-8")

    argv = _stage_command_argv(
        "scripts/extract_required.pl sim-run-root/lists/dirC/sim-out.dat provenance/out.csv",
        {"command_kind": "controlled_source_script"},
        controlled_root,
        tmp_path / "runs" / "demo_001",
        controlled_root,
    )

    assert argv[0] == controlled_script.as_posix()
    assert argv[1] == (tmp_path / "runs/demo_001/sim-run-root/lists/dirC/sim-out.dat").as_posix()
    assert argv[2] == (tmp_path / "runs/demo_001/provenance/out.csv").as_posix()


def test_stage_command_argv_does_not_fallback_to_controlled_root_for_materialized_stage(
    tmp_path: Path,
) -> None:
    controlled_root = tmp_path / "controlled-source-demo"
    controlled_script = controlled_root / "procs" / "run-script.sh"
    controlled_script.parent.mkdir(parents=True)
    controlled_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    argv = _stage_command_argv(
        "procs/run-script.sh",
        {"command_kind": "materialized_controlled_script"},
        tmp_path / "runs" / "demo_001" / "sim-run-root",
        tmp_path / "runs" / "demo_001",
        controlled_root,
    )

    assert argv == ["procs/run-script.sh"]


def test_cli_prepare_workspace_writes_json_evidence(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    output_path = tmp_path / "workspace.json"
    _write_config(config_path)

    assert (
        main(
            [
                "prepare-workspace",
                "--config",
                str(config_path),
                "--run-id",
                "demo_002",
                "--workspace-root",
                str(tmp_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    assert (tmp_path / "runs/demo_002/sim-run-root/input").is_dir()
    assert (tmp_path / "runs/demo_002/provenance/products/reports").is_dir()
    assert "runs/demo_002/sim-run-root/provenance" not in output_path.read_text(encoding="utf-8")


def test_materialize_inputs_copies_repeated_groups_and_records_hashes(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_003", workspace_root=tmp_path)

    result = materialize_inputs(
        config_path=config_path,
        run_id="demo_003",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )

    assert len(result.artifacts) == 9
    for group in ("dirA", "dirB", "dirC"):
        for name in ("ex1.dat", "ex2.dat", "ex3.dat"):
            assert (tmp_path / f"runs/demo_003/sim-run-root/input/{group}/{name}").is_file()
    dir_c_ex3 = next(
        artifact
        for artifact in result.artifacts
        if artifact.destination_path.as_posix().endswith("dirC/ex3.dat")
    )
    assert dir_c_ex3.source_resolved_commit == _git(controlled_repo, "rev-parse", "HEAD")
    assert dir_c_ex3.materialization_mode == "copy_from_controlled_source"
    assert dir_c_ex3.sha256 is not None and len(dir_c_ex3.sha256) == 64
    assert dir_c_ex3.sim_area == "input"
    assert dir_c_ex3.logical_group == "dirC"


def test_scheduler_receipt_normalizes_malformed_yaml_and_duplicate_raw_output(
    tmp_path: Path,
) -> None:
    run_id = "receipt_normalization"
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id=run_id, workspace_root=tmp_path)
    raw_output = tmp_path / "runs" / run_id / "sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text("raw\n", encoding="utf-8")
    _write_successful_scheduler_receipt(tmp_path, run_id)
    payload_path = tmp_path / "runs" / run_id / "provenance/logs/run_simulation.stage.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["outputs"].append({**payload["outputs"][0], "sha256": "0" * 64})
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    duplicate = validate_scheduler_receipt(
        config_path=config_path, run_id=run_id, workspace_root=tmp_path
    )
    assert duplicate["status"] == "fail"
    assert "exactly once; found 2 rows" in "; ".join(duplicate["errors"])

    submission = tmp_path / "runs" / run_id / "provenance/scheduler/submission.yaml"
    submission.write_text("submission: [unterminated", encoding="utf-8")
    malformed = validate_scheduler_receipt(
        config_path=config_path, run_id=run_id, workspace_root=tmp_path
    )
    assert malformed["status"] == "fail"
    assert "submission: YAML evidence is unreadable or malformed" in "; ".join(malformed["errors"])


@pytest.mark.parametrize(
    ("field", "escaped_value", "error_field"),
    [
        ("source_root", "../outside", "materialization.inputs source path"),
        ("source_root", "/outside", "materialization.inputs source path"),
        ("destination_root", "../outside", "materialization.inputs destination path"),
        ("destination_root", "/outside", "materialization.inputs destination path"),
    ],
)
def test_materialize_inputs_enforces_source_and_destination_roots_before_writing(
    tmp_path: Path, field: str, escaped_value: str, error_field: str
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["materialization"]["inputs"][field] = escaped_value
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match=error_field):
        materialize_inputs(
            config_path=config_path,
            run_id="escaped_inputs",
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
            controlled_source_ref="controlled-source-demo-v0.1.2",
        )

    assert not (tmp_path / "outside").exists()
    assert not (tmp_path / "runs/escaped_inputs/sim-run-root").exists()


@pytest.mark.parametrize(
    ("field", "escaped_value", "error_field"),
    [
        ("relative_path", "../outside.sh", "controlled_scripts.run_script.relative_path"),
        ("relative_path", "/outside.sh", "controlled_scripts.run_script.relative_path"),
        ("materialized_path", "../outside.sh", "controlled_scripts.run_script.materialized_path"),
        ("materialized_path", "/outside.sh", "controlled_scripts.run_script.materialized_path"),
    ],
)
def test_materialize_runtime_scripts_enforces_source_and_destination_roots_before_writing(
    tmp_path: Path, field: str, escaped_value: str, error_field: str
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["controlled_scripts"]["run_script"][field] = escaped_value
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match=error_field):
        materialize_runtime_scripts(
            config_path=config_path,
            run_id="escaped_scripts",
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
            controlled_source_ref="controlled-source-demo-v0.1.2",
        )

    assert not (tmp_path / "outside.sh").exists()
    assert not (tmp_path / "runs/escaped_scripts/sim-run-root").exists()


@pytest.mark.parametrize(
    ("operation", "script_name", "wrong_destination", "error_field"),
    [
        ("inputs", None, "sim-run-root/files", "materialization.inputs destination path"),
        (
            "procs",
            "run_script",
            "sim-run-root/input/run-script.sh",
            "controlled_scripts.run_script.materialized_path",
        ),
        (
            "procs",
            "synthetic_sim_engine",
            "sim-run-root/procs/synthetic_sim_engine.sh",
            "controlled_scripts.synthetic_sim_engine.materialized_path",
        ),
    ],
)
def test_direct_materialization_rejects_destination_outside_declared_area(
    tmp_path: Path,
    operation: str,
    script_name: str | None,
    wrong_destination: str,
    error_field: str,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if script_name is None:
        config["materialization"]["inputs"]["destination_root"] = wrong_destination
        materialize = materialize_inputs
    else:
        config["materialization"]["runtime_scripts"] = [script_name]
        config["controlled_scripts"][script_name]["materialized_path"] = wrong_destination
        materialize = materialize_runtime_scripts
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match=error_field):
        materialize(
            config_path=config_path,
            run_id="wrong_area_direct",
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
            controlled_source_ref="controlled-source-demo-v0.1.2",
        )

    assert not (tmp_path / "runs/wrong_area_direct/sim-run-root").exists()


@pytest.mark.parametrize(
    ("operation", "script_name", "wrong_destination"),
    [
        ("materialize-inputs", None, "sim-run-root/lists"),
        ("materialize-procs", "run_script", "provenance/controlled-source/run-script.sh"),
        ("materialize-procs", "extract_required", "sim-run-root/procs/extract_required.pl"),
    ],
)
def test_cli_materialization_rejects_destination_outside_declared_area(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    script_name: str | None,
    wrong_destination: str,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if script_name is None:
        config["materialization"]["inputs"]["destination_root"] = wrong_destination
    else:
        config["materialization"]["runtime_scripts"] = [script_name]
        config["controlled_scripts"][script_name]["materialized_path"] = wrong_destination
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(SystemExit, match="2"):
        main(
            [
                operation,
                "--config",
                str(config_path),
                "--run-id",
                "wrong_area_cli",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--controlled-source-ref",
                "controlled-source-demo-v0.1.2",
            ]
        )

    assert "must be under its designated area" in capsys.readouterr().err
    assert not (tmp_path / "runs/wrong_area_cli/sim-run-root").exists()


@pytest.mark.parametrize(
    ("operation", "field", "configured_section"),
    [
        ("materialize-inputs", "source_root", ("materialization", "inputs")),
        ("materialize-inputs", "destination_root", ("materialization", "inputs")),
        ("materialize-procs", "relative_path", ("controlled_scripts", "run_script")),
        ("materialize-procs", "materialized_path", ("controlled_scripts", "run_script")),
    ],
)
def test_cli_materialization_rejects_direct_path_escapes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    field: str,
    configured_section: tuple[str, str],
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config[configured_section[0]][configured_section[1]][field] = (
        "/outside" if field in {"source_root", "relative_path"} else "../outside"
    )
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(SystemExit, match="2"):
        main(
            [
                operation,
                "--config",
                str(config_path),
                "--run-id",
                "cli_escape",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--controlled-source-ref",
                "controlled-source-demo-v0.1.2",
            ]
        )

    assert "must be a relative path without '..'" in capsys.readouterr().err
    assert not (tmp_path / "outside").exists()
    assert not (tmp_path / "runs/cli_escape/sim-run-root/input").exists()
    assert not (tmp_path / "runs/cli_escape/sim-run-root/procs").exists()


@pytest.mark.parametrize("operation", ["inputs", "procs"])
@pytest.mark.parametrize("path_role", ["source", "destination"])
def test_direct_materialization_rejects_symlink_root_escape(
    tmp_path: Path, operation: str, path_role: str
) -> None:
    run_id = f"symlink_{operation}_{path_role}"
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    outside = tmp_path / "outside"
    outside.mkdir()

    if operation == "inputs":
        section = config["materialization"]["inputs"]
        field = "source_root" if path_role == "source" else "destination_root"
    else:
        section = config["controlled_scripts"]["run_script"]
        field = "relative_path" if path_role == "source" else "materialized_path"
    section[field] = "escape-link"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    link_root = controlled_repo if path_role == "source" else tmp_path / "runs" / run_id
    link_root.mkdir(parents=True, exist_ok=True)
    (link_root / "escape-link").symlink_to(outside)
    if path_role == "source":
        _git(controlled_repo, "add", "escape-link")
        _git(
            controlled_repo,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "add escape symlink",
        )

    materialize = materialize_inputs if operation == "inputs" else materialize_runtime_scripts
    with pytest.raises(ValueError, match="resolves outside its designated root"):
        materialize(
            config_path=config_path,
            run_id=run_id,
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
            controlled_source_ref="controlled-source-demo-v0.1.2",
        )

    assert not any(outside.iterdir())


def test_materialization_uses_selected_ref_when_clean_head_differs(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    selected_input = (controlled_repo / "fixtures/controlled_inputs/dirA/ex1.dat").read_bytes()
    selected_engine = (controlled_repo / "scripts/synthetic_sim_engine.sh").read_bytes()
    (controlled_repo / "fixtures/controlled_inputs/dirA/ex1.dat").write_text(
        "new head input\n", encoding="utf-8"
    )
    (controlled_repo / "scripts/synthetic_sim_engine.sh").write_text(
        "#!/usr/bin/env bash\nexit 9\n", encoding="utf-8"
    )
    _git(controlled_repo, "add", "fixtures", "scripts/synthetic_sim_engine.sh")
    _git(
        controlled_repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "new clean head",
    )
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="selected_ref", workspace_root=tmp_path)

    materialize_inputs(
        config_path=config_path,
        run_id="selected_ref",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    materialize_runtime_scripts(
        config_path=config_path,
        run_id="selected_ref",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )

    assert (
        tmp_path / "runs/selected_ref/sim-run-root/input/dirA/ex1.dat"
    ).read_bytes() == selected_input
    assert (
        tmp_path / "runs/selected_ref/provenance/controlled-source/scripts/synthetic_sim_engine.sh"
    ).read_bytes() == selected_engine


def test_materialization_uses_admitted_commit_after_tag_moves(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="moved_tag", workspace_root=tmp_path)
    admitted_bytes = (controlled_repo / "fixtures/controlled_inputs/dirA/ex1.dat").read_bytes()
    _admit_materialization(
        workspace_root=tmp_path,
        run_id="moved_tag",
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    source = controlled_repo / "fixtures/controlled_inputs/dirA/ex1.dat"
    source.write_text("replacement commit bytes\n", encoding="utf-8")
    _git(controlled_repo, "add", source.relative_to(controlled_repo).as_posix())
    _git(
        controlled_repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "move selected tag",
    )
    _git(controlled_repo, "tag", "-f", "controlled-source-demo-v0.1.2")

    _materialize_inputs(
        config_path=config_path,
        run_id="moved_tag",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    assert (
        tmp_path / "runs/moved_tag/sim-run-root/input/dirA/ex1.dat"
    ).read_bytes() == admitted_bytes


def test_cli_materialize_procs_copies_runtime_script_and_writes_evidence(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    output_path = (
        tmp_path / "runs/demo_004/provenance/inventories/materialized_runtime_scripts.json"
    )
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_004", workspace_root=tmp_path)

    assert (
        main(
            [
                "materialize-procs",
                "--config",
                str(config_path),
                "--run-id",
                "demo_004",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--controlled-source-ref",
                "controlled-source-demo-v0.1.2",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    script = tmp_path / "runs/demo_004/sim-run-root/procs/run-script.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(evidence["artifacts"]) == 4
    assert {item["role"] for item in evidence["artifacts"]} == {
        "runtime_script",
        "controlled_code",
    }
    assert all(item["source_blob_oid"] for item in evidence["artifacts"])
    assert all(len(item["source_sha256"]) == 64 for item in evidence["artifacts"])
    artifact = evidence["artifacts"][0]
    assert artifact["source_path"] == "procs/run-script.sh"
    assert artifact["destination_path"] == "runs/demo_004/sim-run-root/procs/run-script.sh"
    assert artifact["source_resolved_commit"] == _git(controlled_repo, "rev-parse", "HEAD")
    assert artifact["hash_status"] == "hashed"
    assert len(artifact["sha256"]) == 64
    assert artifact["role"] == "runtime_script"
    assert artifact["source_file_mode"] == "100755"
    assert artifact["destination_file_mode"] == "0555"
    assert stat.S_IMODE(script.stat().st_mode) == 0o555

    # Inventory selection is anchored to admitted destination identity rather
    # than this mutable classification field.
    for item in evidence["artifacts"]:
        item["role"] = "input"
    output_path.write_text(json.dumps(evidence), encoding="utf-8")

    assert (
        main(
            [
                "inventory-pre",
                "--run-id",
                "demo_004",
                "--workspace-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    controlled_inventory = json.loads(
        (
            tmp_path / "runs/demo_004/provenance/inventories/pre_run_controlled_scripts.json"
        ).read_text(encoding="utf-8")
    )
    assert len(controlled_inventory) == 4
    assert {
        item.get("source_path", item.get("materialization", {}).get("source_path"))
        for item in controlled_inventory
    } == {
        "procs/run-script.sh",
        "scripts/synthetic_sim_engine.sh",
        "scripts/extract_required.pl",
        "scripts/ad_hoc_extract.py",
    }


@pytest.mark.parametrize(
    "relative_path",
    [
        "sim-run-root/input/dirA/ex1.dat",
        "sim-run-root/procs/run-script.sh",
    ],
)
def test_scheduler_rejects_tampered_materialized_closure(
    tmp_path: Path, relative_path: str
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id="tampered_payload",
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
    )
    target = tmp_path / "runs/tampered_payload" / relative_path
    target.chmod(0o755 if target.stat().st_mode & 0o111 else 0o644)
    target.write_text("tampered\n", encoding="utf-8")

    submit_mock_lsf_job(
        config_path=config_path,
        run_id="tampered_payload",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )
    terminal = wait_mock_lsf_job(
        config_path=config_path,
        run_id="tampered_payload",
        workspace_root=tmp_path,
    )

    assert terminal["state"] == "EXIT"
    stderr = (tmp_path / "runs/tampered_payload/provenance/scheduler/stderr.log").read_text(
        encoding="utf-8"
    )
    assert "materialized artifact integrity mismatch" in stderr


@pytest.mark.parametrize(
    ("relative_path", "role"),
    [
        ("sim-run-root/input/dirA/ex1.dat", "input"),
        (
            "provenance/controlled-source/scripts/synthetic_sim_engine.sh",
            "controlled_code",
        ),
        ("sim-run-root/procs/run-script.sh", "runtime_script"),
    ],
)
@pytest.mark.parametrize(
    ("rewrite_destination", "expected_error"),
    [
        (False, "inventory disagrees with preflight admission"),
        (True, "must cover every applicable preflight-admitted artifact exactly once"),
    ],
)
def test_scheduler_rejects_inventory_rewritten_to_match_tampered_executable(
    tmp_path: Path,
    relative_path: str,
    role: str,
    rewrite_destination: bool,
    expected_error: str,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    run_id = "tampered_inventory"
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id=run_id,
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
    )
    target = tmp_path / "runs" / run_id / relative_path
    target.chmod(0o755)
    target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    forged_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    inventory_name = (
        "materialized_inputs.json" if role == "input" else "materialized_runtime_scripts.json"
    )
    inventory_path = tmp_path / "runs" / run_id / "provenance/inventories" / inventory_name
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    artifact = next(
        item
        for item in inventory["artifacts"]
        if item["role"] == role and item["destination_path"].endswith(relative_path)
    )
    artifact["source_sha256"] = forged_hash
    artifact["sha256"] = forged_hash
    artifact["destination_file_mode"] = "0755"
    if rewrite_destination:
        forged_destination = target.with_name("forged-run-script.sh")
        forged_destination.write_bytes(target.read_bytes())
        forged_destination.chmod(0o755)
        artifact["destination_path"] = forged_destination.relative_to(tmp_path).as_posix()
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    submit_mock_lsf_job(
        config_path=config_path,
        run_id=run_id,
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )
    terminal = wait_mock_lsf_job(config_path=config_path, run_id=run_id, workspace_root=tmp_path)

    assert terminal["state"] == "EXIT"
    stderr = (tmp_path / "runs" / run_id / "provenance/scheduler/stderr.log").read_text()
    assert expected_error in stderr


def test_integrity_verification_stays_bound_to_admitted_commit_after_repository_moves(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    run_id = "moved_repository"
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id=run_id,
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
    )
    target = tmp_path / "runs" / run_id / "sim-run-root/input/dirA/ex1.dat"
    source = controlled_repo / "fixtures/controlled_inputs/dirA/ex1.dat"
    source.write_text("new commit bytes\n", encoding="utf-8")
    _git(controlled_repo, "add", source.relative_to(controlled_repo).as_posix())
    _git(
        controlled_repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "move head after admission",
    )
    _git(controlled_repo, "tag", "-f", "controlled-source-demo-v0.1.2")
    source.write_text("uncommitted worktree bytes\n", encoding="utf-8")
    target.chmod(0o644)
    target.write_text("new commit bytes\n", encoding="utf-8")
    inventory_path = tmp_path / "runs" / run_id / "provenance/inventories/materialized_inputs.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    artifact = next(
        item for item in inventory["artifacts"] if item["destination_path"].endswith("dirA/ex1.dat")
    )
    new_identity = subprocess.run(
        ["git", "-C", str(controlled_repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    artifact["source_resolved_commit"] = new_identity
    artifact["source_blob_oid"] = _git(
        controlled_repo, "rev-parse", "HEAD:fixtures/controlled_inputs/dirA/ex1.dat"
    )
    artifact["source_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    artifact["sha256"] = artifact["source_sha256"]
    artifact["destination_file_mode"] = "0644"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ValueError, match="inventory disagrees with preflight admission.*commit"):
        verify_materialization_evidence(
            inventory_path,
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
        )


@pytest.mark.parametrize("mutation", ["empty", "omitted", "duplicate", "swapped"])
def test_materialization_verification_requires_each_admitted_artifact_exactly_once(
    tmp_path: Path, mutation: str
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    run_id = "complete_materialization"
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id=run_id,
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
    )
    inventories = tmp_path / "runs" / run_id / "provenance/inventories"
    inventory_path = inventories / "materialized_inputs.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    artifacts = inventory["artifacts"]
    if mutation == "empty":
        inventory["artifacts"] = []
    elif mutation == "omitted":
        inventory["artifacts"] = artifacts[1:]
    elif mutation == "duplicate":
        inventory["artifacts"] = [*artifacts, artifacts[0].copy()]
    else:
        runtime = json.loads(
            (inventories / "materialized_runtime_scripts.json").read_text(encoding="utf-8")
        )
        inventory["artifacts"][0] = runtime["artifacts"][0]
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    expected = "duplicate destination rows" if mutation == "duplicate" else "must cover every"
    with pytest.raises(ValueError, match=expected):
        verify_materialization_evidence(
            inventory_path,
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("role", "controlled_code"),
        ("source_category", "uncontrolled_input"),
        ("destination_category", "controlled_code"),
        ("logical_group", "dirB"),
        ("sim_area", "files"),
        ("materialization_mode", "mutable_copy"),
    ],
)
def test_materialization_verification_rejects_mutable_classification(
    tmp_path: Path, field: str, replacement: str
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    run_id = "classification_binding"
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id=run_id,
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
    )
    inventory_path = tmp_path / "runs" / run_id / "provenance/inventories/materialized_inputs.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["artifacts"][0][field] = replacement
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ValueError, match="must cover every|disagrees with preflight admission"):
        verify_materialization_evidence(
            inventory_path,
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
        )


def test_write_mock_lsf_metadata_records_absent_lsf_tools_without_failing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_005", workspace_root=tmp_path)
    materialize_inputs(
        config_path=config_path,
        run_id="demo_005",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    materialize_runtime_scripts(
        config_path=config_path,
        run_id="demo_005",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )

    payload = write_mock_lsf_metadata(
        config_path=config_path,
        run_id="demo_005",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        tool_resolver=lambda _name: None,
    )

    output_path = tmp_path / "runs/demo_005/provenance/scheduler/submission.yaml"
    assert output_path.is_file()
    written = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "mock_lsf"
    assert written["scheduler"] == "mock_lsf"
    assert written["real_lsf_required"] is False
    assert all(not tool["available"] for tool in written["real_lsf_tools"].values())
    assert written["metadata_path"] == "runs/demo_005/provenance/scheduler/submission.yaml"
    assert "sim-run-root" not in written["metadata_path"]


def test_cli_submit_mock_lsf_writes_scheduler_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    output_path = tmp_path / "runs/demo_006/provenance/scheduler/submission.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_006", workspace_root=tmp_path)
    materialize_inputs(
        config_path=config_path,
        run_id="demo_006",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    materialize_runtime_scripts(
        config_path=config_path,
        run_id="demo_006",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )

    assert (
        main(
            [
                "submit-mock-lsf",
                "--config",
                str(config_path),
                "--run-id",
                "demo_006",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    metadata = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert metadata["submission"]["run_id"] == "demo_006"
    assert metadata["submission"]["scheduler"] == metadata["scheduler"] == "mock_lsf"
    assert metadata["submission"]["mode"] == metadata["mode"] == "mock_lsf"
    assert metadata["submission"]["job_id"] == "mock-demo_006"
    assert metadata["submission"]["command"] == "make submit-mock-lsf"
    assert metadata["provenance_root"] == "runs/demo_006/provenance"


def test_mock_lsf_submit_wait_and_collect_use_wrapper_terminal_state(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    _set_runtime_delay(config_path, minimum=1.0, maximum=1.0, timeout=5.0)
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id="demo_006a",
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
    )

    submission = submit_mock_lsf_job(
        config_path=config_path,
        run_id="demo_006a",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    state_path = tmp_path / submission["job_state_path"]
    initial_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert initial_state["state"] == "RUN"
    assert initial_state["exit_code"] is None
    assert isinstance(initial_state["pid"], int)
    assert initial_state["process_group_id"] == initial_state["pid"]

    terminal_state = wait_mock_lsf_job(
        config_path=config_path, run_id="demo_006a", workspace_root=tmp_path
    )
    assert terminal_state["state"] == "DONE"
    assert terminal_state["exit_code"] == 0
    assert terminal_state["pid"] == initial_state["pid"]
    assert terminal_state["process_group_id"] == initial_state["process_group_id"]
    assert terminal_state["started_at"] is not None
    assert (tmp_path / "runs/demo_006a/provenance/scheduler/terminal-state.json").is_file()
    assert (tmp_path / "runs/demo_006a/provenance/logs/run_simulation.stage.json").is_file()

    accounting = collect_mock_lsf_accounting(
        config_path=config_path, run_id="demo_006a", workspace_root=tmp_path
    )
    receipt = validate_scheduler_receipt(
        config_path=config_path, run_id="demo_006a", workspace_root=tmp_path
    )
    assert accounting["state"] == "DONE"
    assert accounting["exit_code"] == 0
    assert accounting["payload_stage_evidence"] == (
        "runs/demo_006a/provenance/logs/run_simulation.stage.json"
    )
    assert receipt["status"] == "pass"
    assert receipt["receipt_id"]
    assert receipt["errors"] == []


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("receipt_identity", "terminal_state receipt_id"),
        ("run_job_identity", "terminal_state run_id"),
        ("missing_component", "accounting: YAML evidence does not exist"),
        ("timestamp_order", "timestamps are not monotonic"),
        ("nonzero_done", "terminal state must be DONE with zero exit_code"),
        ("failed_payload", "payload stage evidence must pass"),
        ("accounting_link", "accounting.payload_stage_evidence must link"),
        ("scheduler_mode", "payload mode does not match configured scheduler mode"),
        ("timestamp_disagreement", "duplicated started_at values do not agree"),
        ("malformed_timestamp", "started_at is missing or invalid"),
        ("raw_hash", "raw output hash does not match"),
    ],
)
def test_scheduler_receipt_rejects_inconsistent_components(
    tmp_path: Path, case: str, expected_error: str
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="receipt_bad", workspace_root=tmp_path)
    raw_output = tmp_path / "runs/receipt_bad/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\ndirC,ex1.dat,13,7fee469deaea\n",
        encoding="utf-8",
    )
    _write_successful_scheduler_receipt(tmp_path, "receipt_bad")
    scheduler_root = tmp_path / "runs/receipt_bad/provenance/scheduler"
    logs_root = tmp_path / "runs/receipt_bad/provenance/logs"

    if case in {"receipt_identity", "run_job_identity", "nonzero_done"}:
        terminal_path = scheduler_root / "terminal-state.json"
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        if case == "receipt_identity":
            terminal["receipt_id"] = "stale-receipt"
        elif case == "run_job_identity":
            terminal["run_id"] = "other-run"
            terminal["job_id"] = "other-job"
        else:
            terminal["exit_code"] = 9
        terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    elif case == "missing_component":
        (scheduler_root / "accounting.yaml").unlink()
    elif case in {"timestamp_order", "accounting_link"}:
        accounting_path = scheduler_root / "accounting.yaml"
        accounting = yaml.safe_load(accounting_path.read_text(encoding="utf-8"))
        if case == "timestamp_order":
            accounting["accounted_at"] = "2025-12-31T23:59:59Z"
        else:
            accounting["payload_stage_evidence"] = "stale-payload.json"
        accounting_path.write_text(yaml.safe_dump(accounting), encoding="utf-8")
    elif case in {
        "failed_payload",
        "scheduler_mode",
        "timestamp_disagreement",
        "malformed_timestamp",
    }:
        payload_path = logs_root / "run_simulation.stage.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if case == "failed_payload":
            payload["status"] = "fail"
            payload["return_code"] = 1
        elif case == "scheduler_mode":
            payload["mode"] = "real_lsf"
        elif case == "timestamp_disagreement":
            payload["started_at"] = "2026-01-01T00:00:01.5Z"
        else:
            payload["started_at"] = "not-a-timestamp"
            state_path = scheduler_root / "job-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["started_at"] = "not-a-timestamp"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            terminal_path = scheduler_root / "terminal-state.json"
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            terminal["started_at"] = "not-a-timestamp"
            terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
            accounting_path = scheduler_root / "accounting.yaml"
            accounting = yaml.safe_load(accounting_path.read_text(encoding="utf-8"))
            accounting["started_at"] = "not-a-timestamp"
            accounting_path.write_text(yaml.safe_dump(accounting), encoding="utf-8")
        payload_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        raw_output.write_text("changed after payload\n", encoding="utf-8")

    receipt = validate_scheduler_receipt(
        config_path=config_path,
        run_id="receipt_bad",
        workspace_root=tmp_path,
    )

    assert receipt["status"] == "fail"
    assert expected_error in "; ".join(receipt["errors"])


@pytest.mark.parametrize(
    ("component", "field", "bad_value", "expected_error"),
    [
        *[
            (component, field, bad_value, f"{component} {field}")
            for component in ("submission", "job_state", "terminal_state", "accounting", "payload")
            for field, bad_value in (
                ("receipt_id", "stale-receipt"),
                ("run_id", "stale-run"),
                ("job_id", "stale-job"),
                ("scheduler", "stale-scheduler"),
            )
        ],
        (
            "submission",
            "submission.submitted_at_utc",
            "not-a-time",
            "submitted_at is missing or invalid",
        ),
        ("job_state", "started_at", "2026-01-01T00:00:01", "started_at is missing or invalid"),
        ("accounting", "accounted_at", "not-a-time", "accounted_at is missing or invalid"),
        (
            "submission",
            "submission.submitted_at_utc",
            "2026-01-01T00:00:00.5Z",
            "duplicated submitted_at values do not agree",
        ),
        (
            "terminal_state",
            "started_at",
            "2026-01-01T00:00:01.5Z",
            "duplicated started_at values do not agree",
        ),
        (
            "payload",
            "finished_at",
            "2026-01-01T00:00:02.5Z",
            "duplicated finished_at values do not agree",
        ),
        ("all", "submitted_at", "2026-01-01T00:00:02Z", "timestamps are not monotonic"),
        ("all", "started_at", "2025-12-31T23:59:59Z", "timestamps are not monotonic"),
        ("all", "finished_at", "2025-12-31T23:59:58Z", "timestamps are not monotonic"),
        ("accounting", "accounted_at", "2025-12-31T23:59:57Z", "timestamps are not monotonic"),
        ("job_state", "exit_code", 7, "normalized job state must be DONE with zero exit_code"),
        ("terminal_state", "exit_code", 7, "terminal state must be DONE with zero exit_code"),
        ("accounting", "exit_code", 7, "accounting must record DONE with zero exit_code"),
        ("payload", "status", "fail", "payload stage evidence must pass with zero return_code"),
        ("payload", "return_code", 7, "payload stage evidence must pass with zero return_code"),
        ("payload", "name", "other_stage", "payload name does not match configured payload_stage"),
        (
            "payload",
            "command",
            "procs/other.sh",
            "payload command does not match configured controlled payload command",
        ),
        (
            "submission",
            "submission.run_id",
            "stale-run",
            "submission.submission.run_id does not match top-level identity",
        ),
        (
            "submission",
            "submission.scheduler",
            "real_lsf",
            "submission.submission.scheduler does not match top-level identity",
        ),
        (
            "submission",
            "submission.mode",
            "real_lsf",
            "submission.submission.mode does not match top-level identity",
        ),
        (
            "submission",
            "submission.run_id",
            None,
            "submission.submission.run_id does not match top-level identity",
        ),
        (
            "submission",
            "submission.scheduler",
            None,
            "submission.submission.scheduler does not match top-level identity",
        ),
        (
            "submission",
            "submission.mode",
            None,
            "submission.submission.mode does not match top-level identity",
        ),
        (
            "submission",
            "submission.job_id",
            "stale-job",
            "submission.submission.job_id does not match top-level identity",
        ),
        (
            "submission",
            "submission.receipt_id",
            "stale-receipt",
            "submission.submission.receipt_id does not match top-level identity",
        ),
        (
            "submission",
            "submission.payload_command",
            "procs/other.sh",
            "submission.submission.payload_command does not match configured payload command",
        ),
        (
            "job_state",
            "payload_stage_evidence",
            "stale-payload.json",
            "job_state.payload_stage_evidence must link",
        ),
        (
            "terminal_state",
            "payload_stage_evidence",
            "stale-payload.json",
            "terminal_state.payload_stage_evidence must link",
        ),
        (
            "accounting",
            "payload_stage_evidence",
            "stale-payload.json",
            "accounting.payload_stage_evidence must link",
        ),
        ("payload", "evidence_path", "stale-payload.json", "payload.evidence_path must link"),
        ("accounting", "job_state_path", "stale-job.json", "accounting.job_state_path must link"),
        (
            "submission",
            "accounting_path",
            "stale-accounting.yaml",
            "submission.accounting_path must link",
        ),
        ("submission", "job_state_path", "stale-job.json", "submission.job_state_path must link"),
        (
            "submission",
            "terminal_state_path",
            "stale-terminal.json",
            "submission.terminal_state_path must link",
        ),
        ("payload", "outputs.0.sha256", None, "raw output hash does not match payload evidence"),
        (
            "payload",
            "outputs.0.sha256",
            "0" * 64,
            "raw output hash does not match payload evidence",
        ),
        ("payload", "outputs", [], "payload output evidence must contain"),
    ],
)
def test_scheduler_receipt_negative_coherence_matrix(
    tmp_path: Path,
    component: str,
    field: str,
    bad_value: object,
    expected_error: str,
) -> None:
    """Every scheduler component is independently untrusted until cross-checked."""
    run_id = "receipt_matrix"
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id=run_id, workspace_root=tmp_path)
    raw_output = tmp_path / "runs" / run_id / "sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\ndirC,ex1.dat,13,7fee469deaea\n",
        encoding="utf-8",
    )
    _write_successful_scheduler_receipt(tmp_path, run_id)
    scheduler_root = tmp_path / "runs" / run_id / "provenance/scheduler"
    paths = {
        "submission": scheduler_root / "submission.yaml",
        "job_state": scheduler_root / "job-state.json",
        "terminal_state": scheduler_root / "terminal-state.json",
        "accounting": scheduler_root / "accounting.yaml",
        "payload": tmp_path / "runs" / run_id / "provenance/logs/run_simulation.stage.json",
    }

    def update(name: str, dotted_field: str, value: object) -> None:
        path = paths[name]
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        target: MutableMapping[str, object] | list[object] = record
        parts = dotted_field.split(".")
        for part in parts[:-1]:
            child = target[int(part)] if isinstance(target, list) else target[part]
            assert isinstance(child, (dict, list))
            target = child
        if isinstance(target, list):
            target[int(parts[-1])] = value
        else:
            target[parts[-1]] = value
        path.write_text(
            yaml.safe_dump(record) if path.suffix in {".yaml", ".yml"} else json.dumps(record),
            encoding="utf-8",
        )

    if component == "all":
        timestamp_components = {
            "submitted_at": (
                ("submission", "submission.submitted_at_utc"),
                ("job_state", "submitted_at"),
                ("terminal_state", "submitted_at"),
                ("accounting", "submitted_at"),
            ),
            "started_at": (
                ("job_state", "started_at"),
                ("terminal_state", "started_at"),
                ("accounting", "started_at"),
                ("payload", "started_at"),
            ),
            "finished_at": (
                ("job_state", "finished_at"),
                ("terminal_state", "finished_at"),
                ("accounting", "finished_at"),
                ("payload", "finished_at"),
            ),
        }
        for name, timestamp_field in timestamp_components[field]:
            update(name, timestamp_field, bad_value)
    else:
        update(component, field, bad_value)

    receipt = validate_scheduler_receipt(
        config_path=config_path, run_id=run_id, workspace_root=tmp_path
    )
    assert receipt["status"] == "fail"
    errors = "; ".join(receipt["errors"])
    if component == "submission" and field == "receipt_id":
        assert "job_state receipt_id does not match submission" in errors
    else:
        assert expected_error in errors


@pytest.mark.parametrize(
    "component",
    ["submission", "job_state", "terminal_state", "accounting", "payload", "raw_output"],
)
def test_scheduler_receipt_requires_every_component(tmp_path: Path, component: str) -> None:
    run_id = "receipt_missing"
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id=run_id, workspace_root=tmp_path)
    raw_output = tmp_path / "runs" / run_id / "sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text("raw\n", encoding="utf-8")
    _write_successful_scheduler_receipt(tmp_path, run_id)
    paths = {
        "submission": tmp_path / "runs" / run_id / "provenance/scheduler/submission.yaml",
        "job_state": tmp_path / "runs" / run_id / "provenance/scheduler/job-state.json",
        "terminal_state": tmp_path / "runs" / run_id / "provenance/scheduler/terminal-state.json",
        "accounting": tmp_path / "runs" / run_id / "provenance/scheduler/accounting.yaml",
        "payload": tmp_path / "runs" / run_id / "provenance/logs/run_simulation.stage.json",
        "raw_output": raw_output,
    }
    paths[component].unlink()

    receipt = validate_scheduler_receipt(
        config_path=config_path, run_id=run_id, workspace_root=tmp_path
    )
    assert receipt["status"] == "fail"
    if component == "raw_output":
        assert any("raw output is missing" in error for error in receipt["errors"])
    else:
        assert any(error.startswith(f"{component}:") for error in receipt["errors"])


def test_mock_lsf_wait_timeout_records_failed_evidence(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    _set_runtime_delay(config_path, minimum=2.0, maximum=2.0, timeout=0.1)
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id="demo_006b",
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
    )
    submit_mock_lsf_job(
        config_path=config_path,
        run_id="demo_006b",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    terminal_state = wait_mock_lsf_job(
        config_path=config_path, run_id="demo_006b", workspace_root=tmp_path
    )

    assert terminal_state["state"] == "TIMEOUT"
    assert terminal_state["status_reason"] == "wait_timeout"
    assert terminal_state["cleanup"]["attempted"] is True


def test_mock_lsf_collect_rejects_non_terminal_job(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    _set_runtime_delay(config_path, minimum=1.0, maximum=1.0, timeout=5.0)
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id="demo_006c",
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
    )
    submit_mock_lsf_job(
        config_path=config_path,
        run_id="demo_006c",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    try:
        collect_mock_lsf_accounting(
            config_path=config_path, run_id="demo_006c", workspace_root=tmp_path
        )
    except ValueError as error:
        assert "mock LSF job is not terminal" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("collect should fail before terminal scheduler state")


def test_mock_lsf_payload_nonzero_exit_is_recorded_by_wrapper(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    _set_runtime_delay(config_path, minimum=0.0, maximum=0.0, timeout=2.0)
    controlled_script = controlled_repo / "procs/run-script.sh"
    controlled_script.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    controlled_script.chmod(0o755)
    _git(controlled_repo, "add", "procs/run-script.sh")
    _git(
        controlled_repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "failing payload",
    )
    _prepare_scheduler_payload(
        config_path=config_path,
        run_id="demo_006d",
        workspace_root=tmp_path,
        controlled_repo=controlled_repo,
        controlled_source_ref="HEAD",
    )

    submit_mock_lsf_job(
        config_path=config_path,
        run_id="demo_006d",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    terminal_state = wait_mock_lsf_job(
        config_path=config_path, run_id="demo_006d", workspace_root=tmp_path
    )

    assert terminal_state["state"] == "EXIT"
    assert terminal_state["exit_code"] == 7
    accounting = collect_mock_lsf_accounting(
        config_path=config_path, run_id="demo_006d", workspace_root=tmp_path
    )
    assert accounting["state"] == "EXIT"
    assert accounting["exit_code"] == 7


def test_mock_lsf_wait_records_missing_pid_as_failed_terminal_evidence(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_006e", workspace_root=tmp_path)
    scheduler_root = tmp_path / "runs/demo_006e/provenance/scheduler"
    state_path = scheduler_root / "job-state.json"
    state_path.write_text(
        json.dumps(
            {
                "run_id": "demo_006e",
                "scheduler": "mock_lsf",
                "job_id": "mock-demo_006e",
                "state": "RUN",
                "pid": None,
                "exit_code": None,
            }
        ),
        encoding="utf-8",
    )

    terminal_state = wait_mock_lsf_job(
        config_path=config_path, run_id="demo_006e", workspace_root=tmp_path
    )

    assert terminal_state["state"] == "EXIT"
    assert terminal_state["status_reason"] == "process_vanished_missing_terminal_state"
    assert terminal_state["pid"] is None
    assert terminal_state["wait_observations"][0]["pid_alive"] is False


def test_mock_lsf_wait_records_vanished_stale_non_terminal_process(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_006f", workspace_root=tmp_path)
    scheduler_root = tmp_path / "runs/demo_006f/provenance/scheduler"
    state_path = scheduler_root / "job-state.json"
    state_path.write_text(
        json.dumps(
            {
                "run_id": "demo_006f",
                "scheduler": "mock_lsf",
                "job_id": "mock-demo_006f",
                "state": "RUN",
                "pid": 999_999_999,
                "exit_code": None,
            }
        ),
        encoding="utf-8",
    )

    terminal_state = wait_mock_lsf_job(
        config_path=config_path, run_id="demo_006f", workspace_root=tmp_path
    )

    assert terminal_state["state"] == "EXIT"
    assert terminal_state["status_reason"] == "process_vanished_missing_terminal_state"
    assert terminal_state["pid"] == 999_999_999
    assert terminal_state["wait_observations"][0]["state"] == "RUN"
    assert terminal_state["wait_observations"][0]["pid_alive"] is False


def test_run_synthetic_simulation_writes_raw_output_and_stage_evidence(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_007", workspace_root=tmp_path)
    materialize_inputs(
        config_path=config_path,
        run_id="demo_007",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    assert (
        main(
            [
                "materialize-procs",
                "--config",
                str(config_path),
                "--run-id",
                "demo_007",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--controlled-source-ref",
                "controlled-source-demo-v0.1.2",
            ]
        )
        == 0
    )

    result = run_synthetic_simulation(
        config_path=config_path,
        run_id="demo_007",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    raw_output = tmp_path / "runs/demo_007/sim-run-root/lists/dirC/sim-out.dat"
    assert raw_output.is_file()
    assert raw_output.read_text(encoding="utf-8").splitlines()[0] == (
        "logical_group,example,bytes,sha256_prefix"
    )
    assert result.status == "pass"
    assert result.return_code == 0
    assert result.working_directory == "runs/demo_007/sim-run-root"
    assert result.stdout_log == "runs/demo_007/provenance/logs/run_simulation.stdout.log"
    assert result.stderr_log == "runs/demo_007/provenance/logs/run_simulation.stderr.log"
    assert result.started_at.endswith("Z")
    assert result.finished_at.endswith("Z")
    assert result.duration_seconds >= 0
    output = result.outputs[0]
    assert output.relative_path == "sim-run-root/lists/dirC/sim-out.dat"
    assert output.sim_area == "lists"
    assert output.logical_group == "dirC"
    assert output.role == "raw_output"
    assert output.sha256 is not None and len(output.sha256) == 64


def test_required_extraction_writes_derived_csv_outside_sim_run_root_and_stage_evidence(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_008", workspace_root=tmp_path)
    materialize_inputs(
        config_path=config_path,
        run_id="demo_008",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    main(
        [
            "materialize-procs",
            "--config",
            str(config_path),
            "--run-id",
            "demo_008",
            "--workspace-root",
            str(tmp_path),
            "--controlled-source-repo",
            str(controlled_repo),
            "--controlled-source-ref",
            "controlled-source-demo-v0.1.2",
        ]
    )
    run_synthetic_simulation(
        config_path=config_path,
        run_id="demo_008",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )
    _write_successful_scheduler_receipt(tmp_path, "demo_008")

    result = run_required_extraction(
        config_path=config_path,
        run_id="demo_008",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    required_csv = tmp_path / "runs/demo_008/provenance/products/extracted/required.csv"
    assert required_csv.is_file()
    assert not (tmp_path / "runs/demo_008/sim-run-root/provenance").exists()
    assert required_csv.read_text(encoding="utf-8").splitlines() == [
        "logical_group,example,bytes,sha256_prefix",
        "dirC,ex1.dat,13,eebd9e4163d9",
        "dirC,ex2.dat,13,3a5f7839e322",
        "dirC,ex3.dat,13,6300c7d48a99",
    ]
    assert result.status == "pass"
    assert result.return_code == 0
    assert result.working_directory == "runs/demo_008/provenance/controlled-source"
    assert result.stdout_log == "runs/demo_008/provenance/logs/extract_required.stdout.log"
    assert result.to_dict()["return_code"] == 0
    assert result.to_dict()["logs"] == {
        "stdout": "runs/demo_008/provenance/logs/extract_required.stdout.log",
        "stderr": "runs/demo_008/provenance/logs/extract_required.stderr.log",
    }
    assert result.inputs[0].relative_path == "sim-run-root/lists/dirC/sim-out.dat"
    assert result.inputs[0].role == "raw_output"
    assert result.inputs[0].sha256 is not None
    output = result.outputs[0]
    assert output.relative_path == "provenance/products/extracted/required.csv"
    assert output.role == "extracted_product"
    assert output.sha256 is not None and len(output.sha256) == 64


def test_cli_extract_required_writes_stage_json(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    output_path = tmp_path / "runs/demo_009/provenance/logs/extract_required.stage.json"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_009", workspace_root=tmp_path)
    materialize_runtime_scripts(
        config_path=config_path,
        run_id="demo_009",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    raw_output = tmp_path / "runs/demo_009/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\n"
        "dirA,ex1.dat,13,ignoredaaaaa\n"
        "dirC,ex1.dat,13,7fee469deaea\n",
        encoding="utf-8",
    )
    _write_successful_scheduler_receipt(tmp_path, "demo_009")

    assert (
        main(
            [
                "extract-required",
                "--config",
                str(config_path),
                "--run-id",
                "demo_009",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["name"] == "extract_required"
    assert evidence["status"] == "pass"
    assert evidence["return_code"] == 0
    assert evidence["started_at"].endswith("Z")
    assert evidence["finished_at"].endswith("Z")
    assert evidence["logs"]["stdout"] == "runs/demo_009/provenance/logs/extract_required.stdout.log"
    assert evidence["outputs"][0]["relative_path"] == "provenance/products/extracted/required.csv"
    assert (tmp_path / "runs/demo_009/provenance/products/extracted/required.csv").is_file()


def test_required_extraction_requires_terminal_scheduler_done_not_raw_output_only(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_009a", workspace_root=tmp_path)
    raw_output = tmp_path / "runs/demo_009a/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\ndirC,ex1.dat,13,7fee469deaea\n",
        encoding="utf-8",
    )

    try:
        run_required_extraction(
            config_path=config_path,
            run_id="demo_009a",
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
        )
    except ValueError as error:
        assert "requires a passed scheduler receipt" in str(error)
        assert "submission" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("extraction should require terminal scheduler DONE")


def test_required_extraction_rejects_failed_scheduler_terminal_state(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_009b", workspace_root=tmp_path)
    raw_output = tmp_path / "runs/demo_009b/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\ndirC,ex1.dat,13,7fee469deaea\n",
        encoding="utf-8",
    )
    _write_scheduler_state(tmp_path, "demo_009b", "EXIT")

    try:
        run_required_extraction(
            config_path=config_path,
            run_id="demo_009b",
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
        )
    except ValueError as error:
        assert "requires a passed scheduler receipt" in str(error)
        assert "terminal_state" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("extraction should reject non-DONE scheduler terminal state")


@pytest.mark.parametrize(
    ("runner", "product_name", "stage_name"),
    [
        (run_required_extraction, "required.csv", "extract_required"),
        (run_ad_hoc_extraction, "ad_hoc.csv", "extract_ad_hoc"),
    ],
)
def test_extraction_recomputes_receipt_and_persists_mismatch_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: Callable[..., object],
    product_name: str,
    stage_name: str,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    run_id = f"fresh_receipt_{product_name.removesuffix('.csv')}"
    prepare_workspace(config_path=config_path, run_id=run_id, workspace_root=tmp_path)
    materialize_runtime_scripts(
        config_path=config_path,
        run_id=run_id,
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    raw_output = tmp_path / "runs" / run_id / "sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\ndirC,ex1.dat,13,7fee469deaea\n",
        encoding="utf-8",
    )
    _write_successful_scheduler_receipt(tmp_path, run_id)
    receipt_path = tmp_path / "runs" / run_id / "provenance/validations/scheduler_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps({"status": "pass", "validated_at": "stale"}), encoding="utf-8"
    )
    raw_output.write_text("changed after stale receipt\n", encoding="utf-8")

    launched = False

    def refuse_launch(*args: object, **kwargs: object) -> object:
        nonlocal launched
        launched = True
        raise AssertionError("extractor must not launch after failed receipt validation")

    monkeypatch.setattr("provenance.stages.subprocess.run", refuse_launch)

    with pytest.raises(ValueError, match="raw output hash does not match payload evidence"):
        runner(
            config_path=config_path,
            run_id=run_id,
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
        )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert receipt["validated_at"] != "stale"
    assert receipt["run_id"] == run_id
    assert any(
        "raw output hash does not match payload evidence" in error for error in receipt["errors"]
    )
    assert not launched
    assert not (
        tmp_path / "runs" / run_id / "provenance/products/extracted" / product_name
    ).exists()
    assert not (
        tmp_path / "runs" / run_id / "provenance/logs" / f"{stage_name}.stdout.log"
    ).exists()
    assert not (
        tmp_path / "runs" / run_id / "provenance/logs" / f"{stage_name}.stderr.log"
    ).exists()


def test_extraction_persists_validator_exception_without_changing_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    run_id = "receipt_validator_error"
    prepare_workspace(config_path=config_path, run_id=run_id, workspace_root=tmp_path)

    def fail_validation(**kwargs: object) -> dict[str, object]:
        raise RuntimeError("component could not be decoded")

    monkeypatch.setattr("provenance.scheduler.validate_scheduler_receipt", fail_validation)

    with pytest.raises(RuntimeError, match="component could not be decoded"):
        run_required_extraction(
            config_path=config_path,
            run_id=run_id,
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
        )

    receipt_path = tmp_path / "runs" / run_id / "provenance/validations/scheduler_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["errors"] == [
        "scheduler receipt validation raised RuntimeError: component could not be decoded"
    ]
    assert receipt["run_id"] == run_id
    assert receipt["stage"] == "extract_required"
    assert receipt["status"] == "fail"
    assert receipt["validated_at"].endswith("Z")
    assert not (tmp_path / "runs" / run_id / "provenance/products/extracted/required.csv").exists()


@pytest.mark.parametrize(
    ("relative_path", "runner"),
    [
        ("scripts/extract_required.pl", run_required_extraction),
        ("scripts/ad_hoc_extract.py", run_ad_hoc_extraction),
    ],
)
def test_extraction_rejects_tampered_extractor_and_forged_inventory(
    tmp_path: Path,
    relative_path: str,
    runner: Callable[..., object],
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="tampered_extract", workspace_root=tmp_path)
    materialize_runtime_scripts(
        config_path=config_path,
        run_id="tampered_extract",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    raw_output = tmp_path / "runs/tampered_extract/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\ndirC,ex1.dat,13,7fee469deaea\n",
        encoding="utf-8",
    )
    _write_successful_scheduler_receipt(tmp_path, "tampered_extract")
    extractor = tmp_path / "runs/tampered_extract/provenance/controlled-source" / relative_path
    extractor.chmod(0o755)
    extractor.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    inventory_path = (
        tmp_path / "runs/tampered_extract/provenance/inventories/materialized_runtime_scripts.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    artifact = next(item for item in inventory["artifacts"] if item["source_path"] == relative_path)
    forged_hash = hashlib.sha256(extractor.read_bytes()).hexdigest()
    artifact["source_sha256"] = forged_hash
    artifact["sha256"] = forged_hash
    artifact["destination_file_mode"] = "0755"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            f"inventory disagrees with preflight admission.*{relative_path}|destination_file_mode"
        ),
    ):
        runner(
            config_path=config_path,
            run_id="tampered_extract",
            workspace_root=tmp_path,
            controlled_source_repo=controlled_repo,
        )


def test_ad_hoc_extraction_writes_derived_csv_outside_sim_run_root_and_stage_evidence(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_010", workspace_root=tmp_path)
    materialize_runtime_scripts(
        config_path=config_path,
        run_id="demo_010",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    raw_output = tmp_path / "runs/demo_010/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\n"
        "dirA,ex1.dat,11,ignoredaaaaa\n"
        "dirC,ex1.dat,13,7fee469deaea\n"
        "dirC,ex2.dat,17,ignoredbbbbb\n",
        encoding="utf-8",
    )
    _write_successful_scheduler_receipt(tmp_path, "demo_010")

    result = run_ad_hoc_extraction(
        config_path=config_path,
        run_id="demo_010",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    ad_hoc_csv = tmp_path / "runs/demo_010/provenance/products/extracted/ad_hoc.csv"
    assert ad_hoc_csv.is_file()
    assert not (tmp_path / "runs/demo_010/sim-run-root/provenance").exists()
    assert ad_hoc_csv.read_text(encoding="utf-8").splitlines() == [
        "logical_group,input_count,total_bytes",
        "dirA,1,11",
        "dirC,2,30",
    ]
    assert result.status == "pass"
    assert result.return_code == 0
    assert result.working_directory == "runs/demo_010/provenance/controlled-source"
    assert result.stdout_log == "runs/demo_010/provenance/logs/extract_ad_hoc.stdout.log"
    assert result.inputs[0].relative_path == "sim-run-root/lists/dirC/sim-out.dat"
    assert result.inputs[0].role == "raw_output"
    assert result.inputs[0].sha256 is not None
    output = result.outputs[0]
    assert output.relative_path == "provenance/products/extracted/ad_hoc.csv"
    assert output.role == "extracted_product"
    assert output.sha256 is not None and len(output.sha256) == 64


def test_cli_extract_ad_hoc_writes_stage_json(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    output_path = tmp_path / "runs/demo_011/provenance/logs/extract_ad_hoc.stage.json"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_011", workspace_root=tmp_path)
    materialize_runtime_scripts(
        config_path=config_path,
        run_id="demo_011",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )
    raw_output = tmp_path / "runs/demo_011/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\n"
        "dirB,ex1.dat,19,ignoredaaaaa\n"
        "dirC,ex1.dat,23,ignoredbbbbb\n",
        encoding="utf-8",
    )
    _write_successful_scheduler_receipt(tmp_path, "demo_011")

    assert (
        main(
            [
                "extract-ad-hoc",
                "--config",
                str(config_path),
                "--run-id",
                "demo_011",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["name"] == "extract_ad_hoc"
    assert evidence["outputs"][0]["relative_path"] == "provenance/products/extracted/ad_hoc.csv"
    assert (tmp_path / "runs/demo_011/provenance/products/extracted/ad_hoc.csv").is_file()


def _create_controlled_source_repo(path: Path) -> Path:
    (path / "fixtures/controlled_inputs").mkdir(parents=True)
    for group in ("dirA", "dirB", "dirC"):
        group_path = path / "fixtures/controlled_inputs" / group
        group_path.mkdir()
        for name in ("ex1.dat", "ex2.dat", "ex3.dat"):
            (group_path / name).write_text(f"{group},{name}\n", encoding="utf-8")
    (path / "procs").mkdir()
    run_script = path / "procs/run-script.sh"
    run_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "run_root=${1:-$(pwd -P)}\n"
        'exec "$SYNTHETIC_SIM_ENGINE" "$run_root"\n',
        encoding="utf-8",
    )
    run_script.chmod(0o755)
    (path / "scripts").mkdir()
    engine = path / "scripts/synthetic_sim_engine.sh"
    engine.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "run_root=${1:-$(pwd -P)}\n"
        "input_root=$run_root/input\n"
        "output_dir=$run_root/lists/dirC\n"
        'mkdir -p -- "$output_dir"\n'
        "output_file=$output_dir/sim-out.dat\n"
        "delay_seconds=${SYNTHETIC_SIM_RUNTIME_DELAY_MIN_SECONDS:-0}\n"
        "if python3 - \"$delay_seconds\" <<'PY'\n"
        "import sys\n"
        "raise SystemExit(0 if float(sys.argv[1]) > 0 else 1)\n"
        "PY\n"
        "then\n"
        '  sleep "$delay_seconds"\n'
        "fi\n"
        "printf 'logical_group,example,bytes,sha256_prefix\\n' >\"$output_file\"\n"
        "for logical_group in dirA dirB dirC; do\n"
        "  for example in ex1.dat ex2.dat ex3.dat; do\n"
        "    input_file=$input_root/$logical_group/$example\n"
        "    byte_count=$(wc -c <\"$input_file\" | tr -d ' ')\n"
        "    sha_prefix=$(sha256sum \"$input_file\" | cut -d ' ' -f 1 | cut -c 1-12)\n"
        '    printf \'%s,%s,%s,%s\\n\' "$logical_group" "$example" '
        '"$byte_count" "$sha_prefix" >>"$output_file"\n'
        "  done\n"
        "done\n"
        "printf 'Wrote synthetic raw output: %s\\n' \"$output_file\"\n",
        encoding="utf-8",
    )
    engine.chmod(0o755)
    extractor = path / "scripts/extract_required.pl"
    extractor.write_text(
        "#!/usr/bin/env perl\n"
        "use strict;\n"
        "use warnings;\n"
        "my ($input_path, $output_path) = @ARGV;\n"
        "open my $in, '<', $input_path or die \"Cannot read $input_path: $!\\n\";\n"
        "open my $out, '>', $output_path or die \"Cannot write $output_path: $!\\n\";\n"
        "my $header = <$in>;\n"
        "chomp $header;\n"
        'print {$out} "$header\\n";\n'
        "while (my $line = <$in>) {\n"
        "  chomp $line;\n"
        "  my ($logical_group, $example, $bytes, $sha_prefix) = split /,/, $line;\n"
        "  next unless defined $logical_group && $logical_group eq 'dirC';\n"
        "  print {$out} join(',', $logical_group, $example, $bytes, $sha_prefix), \"\\n\";\n"
        "}\n",
        encoding="utf-8",
    )
    extractor.chmod(0o755)
    ad_hoc_extractor = path / "scripts/ad_hoc_extract.py"
    ad_hoc_extractor.write_text(
        "#!/usr/bin/env python3\n"
        "import csv\n"
        "import sys\n"
        "from collections import defaultdict\n"
        "from pathlib import Path\n"
        "input_path = Path(sys.argv[1])\n"
        "output_path = Path(sys.argv[2])\n"
        "totals = defaultdict(int)\n"
        "counts = defaultdict(int)\n"
        "with input_path.open(newline='', encoding='utf-8') as input_file:\n"
        "    reader = csv.DictReader(input_file)\n"
        "    for row in reader:\n"
        "        totals[row['logical_group']] += int(row['bytes'])\n"
        "        counts[row['logical_group']] += 1\n"
        "output_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "with output_path.open('w', newline='', encoding='utf-8') as output_file:\n"
        "    writer = csv.DictWriter(\n"
        "        output_file, fieldnames=['logical_group', 'input_count', 'total_bytes']\n"
        "    )\n"
        "    writer.writeheader()\n"
        "    for logical_group in sorted(counts):\n"
        "        writer.writerow(\n"
        "            {\n"
        "                'logical_group': logical_group,\n"
        "                'input_count': counts[logical_group],\n"
        "                'total_bytes': totals[logical_group],\n"
        "            }\n"
        "        )\n",
        encoding="utf-8",
    )
    ad_hoc_extractor.chmod(0o755)
    _git(path, "init")
    _git(path, "add", "fixtures", "procs", "scripts")
    _git(
        path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "init",
    )
    _git(path, "tag", "controlled-source-demo-v0.1.2")
    return path


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repo.as_posix(), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
