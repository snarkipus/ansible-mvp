import hashlib
import json
import subprocess
from argparse import Namespace
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from pytest import MonkeyPatch

import provenance.cli as cli
from provenance.cli import main
from provenance.config import read_config_mapping
from provenance.manifest import REQUIRED_TOP_LEVEL_SECTIONS


@pytest.mark.parametrize(
    "missing_option", ["--config", "--run-id", "--workspace-root", "--stage-output"]
)
def test_smoke_manifest_rejects_each_missing_semantic_context_option(
    tmp_path: Path, missing_option: str
) -> None:
    options = {
        "--config": "configs/run.synthetic.yaml",
        "--run-id": "required_context",
        "--workspace-root": str(tmp_path),
        "--stage-output": str(tmp_path / "manifest_smoke.stage.json"),
    }
    argv = ["smoke-manifest", str(tmp_path / "manifest.yaml")]
    for option, value in options.items():
        if option != missing_option:
            argv.extend((option, value))

    with pytest.raises(SystemExit, match="2"):
        main(argv)


@pytest.mark.parametrize("run_id", ["../escape", "/absolute", "two words"])
def test_cli_rejects_unsafe_run_id_before_writing(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                "prepare-workspace",
                "--config",
                str(tmp_path / "missing.yaml"),
                "--run-id",
                run_id,
                "--workspace-root",
                str(tmp_path),
            ]
        )

    assert error.value.code == 2
    assert not (tmp_path / "runs").exists()


def test_support_stage_attempt_recorder_preserves_success_and_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    attempts: list[dict[str, object]] = []

    def record(_args: Namespace, stage_name: str, **values: object) -> None:
        attempts.append({"stage_name": stage_name, **values})

    monkeypatch.setattr(cli, "_write_support_stage_attempt", record)
    args = Namespace()

    with cli._support_stage_attempt(args, "prepare_workspace"):
        pass
    original = ValueError("operation failed")
    with pytest.raises(ValueError) as raised:
        with cli._support_stage_attempt(args, "prepare_workspace"):
            raise original

    assert raised.value is original
    assert attempts[0]["stage_name"] == "prepare_workspace"
    assert attempts[0].get("status", "pass") == "pass"
    assert attempts[1]["status"] == "fail"
    assert attempts[1]["return_code"] == 1
    assert attempts[1]["error"] is original


def test_support_stage_attempt_recorder_does_not_mask_evidence_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_to_record(*_args: object, **_kwargs: object) -> None:
        raise OSError("evidence unavailable")

    monkeypatch.setattr(cli, "_write_support_stage_attempt", fail_to_record)
    original = ValueError("operation failed")

    with pytest.raises(ValueError) as raised:
        with cli._support_stage_attempt(Namespace(), "prepare_workspace"):
            raise original

    assert raised.value is original
    assert "failed to record prepare_workspace" in raised.value.__notes__[0]


@pytest.mark.parametrize(
    ("case", "stage_name"),
    [
        ("validation", "validate"),
        ("extraction", "extract_required"),
        ("scheduler_collection", "collect_mock_lsf"),
        ("reports", "build_reports"),
        ("manifest", "manifest"),
    ],
)
def test_command_failure_paths_record_failed_attempts(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    case: str,
    stage_name: str,
) -> None:
    attempts: list[dict[str, object]] = []

    def record(_args: Namespace, recorded_stage: str, **values: object) -> None:
        attempts.append({"stage_name": recorded_stage, **values})

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError(f"{case} failed")

    monkeypatch.setattr(cli, "_write_support_stage_attempt", record)
    args = Namespace(
        config=tmp_path / "config.yaml",
        run_id="failure_case",
        workspace_root=tmp_path,
        controlled_source_repo=tmp_path / "controlled",
        controlled_source_ref="controlled-source-demo-v0.1.2",
        output=None,
        stage_output=tmp_path / "attempt.json",
    )
    if case == "validation":
        monkeypatch.setattr(cli, "_run_validate_required", fail)
        command = cli._cmd_validate_required
    elif case == "extraction":
        monkeypatch.setattr(cli, "run_required_extraction", fail)
        command = cli._cmd_extract_required
    elif case == "scheduler_collection":
        monkeypatch.setattr(cli, "collect_mock_lsf_accounting", fail)
        command = cli._cmd_collect_mock_lsf
    elif case == "reports":
        monkeypatch.setattr(cli, "build_report_product_evidence", fail)
        command = cli._cmd_build_reports
    else:
        monkeypatch.setattr(cli, "_run_assemble_run_manifest", fail)
        command = cli._cmd_assemble_run_manifest

    with pytest.raises(ValueError, match=f"{case} failed"):
        command(args)

    assert attempts[-1]["stage_name"] == stage_name
    assert attempts[-1]["status"] == "fail"
    assert attempts[-1]["return_code"] == 1
    error = attempts[-1]["error"]
    assert isinstance(error, ValueError)
    assert str(error) == f"{case} failed"


def test_cli_inventory_outputs_records_with_hashes(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    product = tmp_path / "products" / "extracted" / "required.csv"
    product.parent.mkdir(parents=True)
    product.write_text("case,value\na,1\n", encoding="utf-8")

    assert main(["inventory", str(tmp_path), "--with-hashes"]) == 0

    records = json.loads(capsys.readouterr().out)
    assert records[0]["relative_path"] == "products/extracted/required.csv"
    assert records[0]["product_area"] == "extracted"
    assert len(records[0]["sha256"]) == 64


def test_cli_inventory_pre_writes_input_and_script_inventories(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    run_root = tmp_path / "runs" / "demo_001"
    sim_root = run_root / "sim-run-root"
    inventory_root = run_root / "provenance" / "inventories"
    (sim_root / "input" / "dirC").mkdir(parents=True)
    (sim_root / "procs").mkdir(parents=True)
    inventory_root.mkdir(parents=True)
    (sim_root / "input" / "dirC" / "ex1.dat").write_text("input\n", encoding="utf-8")
    (sim_root / "procs" / "run-script.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (inventory_root / "materialized_inputs.json").write_text(
        json.dumps(
            {
                "run_id": "demo_001",
                "artifacts": [
                    {
                        "source_repository": "/controlled-source-demo",
                        "source_ref": "controlled-source-demo-v0.1.2",
                        "source_resolved_commit": "abc123",
                        "source_path": "fixtures/controlled_inputs/dirC/ex1.dat",
                        "destination_path": "runs/demo_001/sim-run-root/input/dirC/ex1.dat",
                        "materialization_mode": "copy_from_controlled_source",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (inventory_root / "materialized_runtime_scripts.json").write_text(
        json.dumps(
            {
                "run_id": "demo_001",
                "artifacts": [
                    {
                        "source_repository": "/controlled-source-demo",
                        "source_ref": "controlled-source-demo-v0.1.2",
                        "source_resolved_commit": "abc123",
                        "source_path": "procs/run-script.sh",
                        "destination_path": "runs/demo_001/sim-run-root/procs/run-script.sh",
                        "materialization_mode": "copy_from_controlled_source",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert main(["inventory-pre", "--run-id", "demo_001", "--workspace-root", str(tmp_path)]) == 0

    summary = json.loads(capsys.readouterr().out)
    inputs = json.loads((inventory_root / "pre_run_inputs.json").read_text(encoding="utf-8"))
    scripts = json.loads(
        (inventory_root / "pre_run_controlled_scripts.json").read_text(encoding="utf-8")
    )
    assert summary["input_count"] == 1
    assert summary["controlled_script_count"] == 1
    assert inputs[0]["relative_path"] == "input/dirC/ex1.dat"
    assert inputs[0]["run_relative_path"] == "runs/demo_001/sim-run-root/input/dirC/ex1.dat"
    assert inputs[0]["sim_area"] == "input"
    assert inputs[0]["logical_group"] == "dirC"
    assert inputs[0]["role"] == "input"
    assert len(inputs[0]["sha256"]) == 64
    assert inputs[0]["materialization"]["source_path"] == "fixtures/controlled_inputs/dirC/ex1.dat"
    assert scripts[0]["relative_path"] == "procs/run-script.sh"
    assert scripts[0]["role"] == "runtime_script"
    assert scripts[0]["materialization"]["source_path"] == "procs/run-script.sh"


def test_cli_inventory_post_writes_raw_output_and_derived_product_inventories(
    tmp_path: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    run_root = tmp_path / "runs" / "demo_001"
    sim_root = run_root / "sim-run-root"
    provenance_root = run_root / "provenance"
    inventory_root = provenance_root / "inventories"
    (sim_root / "lists" / "dirC").mkdir(parents=True)
    (provenance_root / "products" / "extracted").mkdir(parents=True)
    (provenance_root / "products" / "reports").mkdir(parents=True)
    (sim_root / "lists" / "dirC" / "sim-out.dat").write_text("raw\n", encoding="utf-8")
    (provenance_root / "products" / "extracted" / "required.csv").write_text(
        "logical_group,example,bytes,sha256_prefix\ndirC,ex1.dat,4,aaaa\n",
        encoding="utf-8",
    )
    (provenance_root / "products" / "extracted" / "custom.csv").write_text(
        "case,value\nb,2\n",
        encoding="utf-8",
    )
    (provenance_root / "products" / "reports" / "summary.xlsx").write_text(
        "report\n", encoding="utf-8"
    )
    config_path = tmp_path / "run.synthetic.yaml"
    config = read_config_mapping(Path("configs/run.synthetic.yaml"))
    assert isinstance(config["stages"], list)
    config["stages"].append(
        {
            "name": "custom_extract",
            "display_name": "Custom extract",
            "lifecycle_class": "factory",
            "display_order": 85,
            "operator_visible": True,
            "command": "scripts/custom_extract.py",
            "working_directory": "controlled_source_repo",
            "command_kind": "controlled_source_script",
            "approved_command_path": "scripts/custom_extract.py",
            "outputs": ["provenance/products/extracted/custom.csv"],
        }
    )
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    assert (
        main(
            [
                "inventory-post",
                "--config",
                str(config_path),
                "--run-id",
                "demo_001",
                "--workspace-root",
                str(tmp_path),
            ]
        )
        == 0
    )

    summary = json.loads(capsys.readouterr().out)
    raw_outputs = json.loads(
        (inventory_root / "post_run_raw_outputs.json").read_text(encoding="utf-8")
    )
    products = json.loads(
        (inventory_root / "post_run_derived_products.json").read_text(encoding="utf-8")
    )
    assert summary["raw_output_count"] == 1
    assert summary["derived_product_count"] == 3
    assert raw_outputs[0]["relative_path"] == "lists/dirC/sim-out.dat"
    assert raw_outputs[0]["workflow_relative_path"] == "sim-run-root/lists/dirC/sim-out.dat"
    assert (
        raw_outputs[0]["run_relative_path"] == "runs/demo_001/sim-run-root/lists/dirC/sim-out.dat"
    )
    assert raw_outputs[0]["sim_area"] == "lists"
    assert raw_outputs[0]["logical_group"] == "dirC"
    assert raw_outputs[0]["role"] == "raw_output"
    assert raw_outputs[0]["hash_status"] == "hashed"
    assert len(raw_outputs[0]["sha256"]) == 64
    by_path = {product["workflow_relative_path"]: product for product in products}
    assert by_path["provenance/products/extracted/required.csv"]["role"] == "extracted_product"
    assert (
        by_path["provenance/products/extracted/required.csv"]["producing_stage"]
        == "extract_required"
    )
    assert (
        by_path["provenance/products/extracted/custom.csv"]["producing_stage"] == "custom_extract"
    )
    assert by_path["provenance/products/reports/summary.xlsx"]["role"] == "report_product"
    assert by_path["provenance/products/reports/summary.xlsx"]["producing_stage"] == "build_reports"


def test_cli_validate_csv_returns_nonzero_for_failed_shape(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    csv_path = tmp_path / "required.csv"
    csv_path.write_text("case,value\na,1\n", encoding="utf-8")

    exit_code = main(
        [
            "validate-csv",
            str(csv_path),
            "--expected-header",
            "case,value",
            "--expected-data-rows",
            "2",
        ]
    )

    evidence = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert evidence["status"] == "fail"
    assert any(check["name"] == "data_row_count" for check in evidence["checks"])


def test_cli_validate_required_writes_configured_validation_evidence(
    tmp_path: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    run_root = tmp_path / "runs" / "demo_001"
    product = run_root / "provenance" / "products" / "extracted" / "required.csv"
    product.parent.mkdir(parents=True)
    product.write_text("logical_group,example,value\ndirC,ex1.dat,42\n", encoding="utf-8")
    shape_config = tmp_path / "expected_shape.required_extract.yaml"
    shape_config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "product": {
                    "relative_path": "provenance/products/extracted/required.csv",
                    "display_path": "products/extracted/required.csv",
                },
                "expectations": {
                    "expected_header": ["logical_group", "example", "value"],
                    "expected_column_count": 3,
                    "minimum_data_rows": 1,
                },
                "evidence": {"output_path": "provenance/validations/required_extract.json"},
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "validate-required",
                "--shape-config",
                str(shape_config),
                "--run-id",
                "demo_001",
                "--workspace-root",
                str(tmp_path),
            ]
        )
        == 0
    )

    summary = json.loads(capsys.readouterr().out)
    evidence_path = run_root / "provenance" / "validations" / "required_extract.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert summary["status"] == "pass"
    assert summary["evidence"] == evidence_path.as_posix()
    assert evidence["path"] == "products/extracted/required.csv"
    assert evidence["status"] == "pass"
    assert evidence["data_rows"] == 1
    assert {check["name"] for check in evidence["checks"]} == {
        "exists",
        "is_file",
        "non_empty",
        "minimum_data_row_count",
        "column_count",
        "header",
    }


def test_cli_assembles_and_smoke_validates_manifest(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    input_yaml = tmp_path / "manifest-input.yaml"
    manifest_path = tmp_path / "manifest.yaml"
    input_yaml.write_text(
        yaml.safe_dump(
            {
                "run": {
                    "run_id": "demo_001",
                    "run_root": "runs/demo_001",
                    "started_at": "2026-06-29T00:00:00+00:00",
                    "finished_at": "2026-06-29T00:00:01+00:00",
                    "execution_context": {
                        "executed_by": "tester",
                        "hostname": "localhost",
                        "platform": "Linux",
                        "python_version": "3.12.0",
                        "git_version": "git version 2.0.0",
                    },
                },
                "repositories": [
                    {
                        "name": "ansible-mvp",
                        "path": "/workspace/ansible-mvp",
                        "resolved_commit": "a" * 40,
                        "worktree_status": "clean",
                    }
                ],
                "simulation_layout": {
                    "run_root": "runs/demo_001",
                    "sim_run_root": "runs/demo_001/sim-run-root",
                    "provenance_root": "runs/demo_001/provenance",
                },
                "controlled_source_gate": {"status": "pass"},
                "scheduler": {"mode": "mock_lsf"},
                "workflow": {
                    "operator_flow": [
                        {
                            "stage": "run_simulation",
                            "display_name": "Run simulation",
                            "lifecycle_class": "factory",
                            "display_order": 60,
                            "status": "pass",
                        }
                    ]
                },
                "inputs": [{"relative_path": "input/dirC/ex1.dat"}],
                "runtime_scripts": [{"relative_path": "procs/run-script.sh"}],
                "stages": [
                    {
                        "name": "run_simulation",
                        "display_name": "Run simulation",
                        "lifecycle_class": "factory",
                        "display_order": 60,
                        "operator_visible": True,
                        "status": "pass",
                    }
                ],
                "raw_simulation_outputs": [{"relative_path": "lists/dirC/sim-out.dat"}],
                "derived_products": [{"relative_path": "products/extracted/required.csv"}],
                "validations": [{"path": "products/extracted/required.csv", "status": "pass"}],
                "logs": [{"path": "logs/run_simulation.stdout.log"}],
                "notes": ["smoke-test manifest"],
            }
        ),
        encoding="utf-8",
    )

    assert main(["assemble-manifest", str(input_yaml), "--output", str(manifest_path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pass"
    with pytest.raises(SystemExit, match="2"):
        main(["smoke-manifest", str(manifest_path)])

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert tuple(manifest)[: len(REQUIRED_TOP_LEVEL_SECTIONS)] == REQUIRED_TOP_LEVEL_SECTIONS


def test_cli_manifest_smoke_fails_for_missing_key_values(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                section: ({"run_id": ""} if section == "run" else [])
                for section in REQUIRED_TOP_LEVEL_SECTIONS
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="2"):
        main(["smoke-manifest", str(manifest_path)])


def test_cli_manifest_smoke_verifies_unchanged_assembled_manifest(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    manifest_path = tmp_path / "runs" / "demo_001" / "provenance" / "manifest.yaml"
    smoke_output = (
        tmp_path / "runs" / "demo_001" / "provenance" / "validations" / "manifest_smoke.json"
    )
    smoke_stage_output = (
        tmp_path / "runs" / "demo_001" / "provenance" / "logs" / "manifest_smoke.stage.json"
    )
    base_manifest = {
        "manifest_version": "0.1",
        "run": {
            "run_id": "demo_001",
            "run_root": "runs/demo_001",
            "started_at": "2026-06-29T00:00:00+00:00",
            "finished_at": "2026-06-29T00:00:01+00:00",
            "execution_context": {
                "executed_by": "tester",
                "hostname": "localhost",
                "platform": "Linux",
                "python_version": "3.12.0",
                "git_version": "git version 2.0.0",
            },
        },
        "workflow": {
            "operator_flow": [
                {
                    "stage": "run_simulation",
                    "display_name": "Run simulation",
                    "lifecycle_class": "factory",
                    "display_order": 70,
                    "status": "pass",
                }
            ]
        },
        "repositories": [
            {
                "name": "ansible-mvp",
                "path": tmp_path.as_posix(),
                "resolved_commit": "abc123",
                "worktree_status": "clean",
            }
        ],
        "simulation_layout": {
            "run_root": "runs/demo_001",
            "sim_run_root": "runs/demo_001/sim-run-root",
            "provenance_root": "runs/demo_001/provenance",
        },
        "controlled_source_gate": {"status": "pass"},
        "scheduler": {"mode": "mock_lsf"},
        "inputs": [{"relative_path": "input/dirC/ex1.dat"}],
        "runtime_scripts": [{"relative_path": "procs/run-script.sh"}],
        "stages": [
            {
                "name": "run_simulation",
                "display_name": "Run simulation",
                "lifecycle_class": "factory",
                "display_order": 70,
                "operator_visible": True,
                "status": "pass",
            }
        ],
        "raw_simulation_outputs": [{"relative_path": "lists/dirC/sim-out.dat"}],
        "derived_products": [{"relative_path": "products/extracted/required.csv"}],
        "validations": [{"status": "pass"}],
        "logs": [{"path": "logs/run_simulation.stdout.log"}],
        "hash_policy": {"algorithm": "sha256"},
        "notes": ["immutable"],
    }
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(yaml.safe_dump(base_manifest), encoding="utf-8")
    original_manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(original_manifest_bytes).hexdigest()
    assembly_receipt = smoke_stage_output.with_name("manifest.stage.json")
    assembly_receipt.parent.mkdir(parents=True)
    assembly_receipt.write_text(
        json.dumps(
            {
                "name": "manifest",
                "status": "pass",
                "return_code": 0,
                "evidence_path": assembly_receipt.relative_to(tmp_path).as_posix(),
                "manifest": manifest_path.relative_to(tmp_path).as_posix(),
                "manifest_sha256": manifest_sha256,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "semantic_consistency_errors", lambda *_args, **_kwargs: ())

    assert (
        main(
            [
                "smoke-manifest",
                str(manifest_path),
                "--output",
                str(smoke_output),
                "--config",
                "configs/run.synthetic.yaml",
                "--run-id",
                "demo_001",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(tmp_path / "controlled-source-demo"),
                "--controlled-source-ref",
                "controlled-source-demo-v0.1.2",
                "--stage-output",
                str(smoke_stage_output),
            ]
        )
        == 0
    )

    smoke = json.loads(smoke_output.read_text(encoding="utf-8"))
    assert manifest_path.read_bytes() == original_manifest_bytes
    assert smoke["manifest_sha256"] == manifest_sha256
    assert smoke["assembly_manifest_sha256"] == manifest_sha256
    assert smoke["manifest_hash_matches_assembly_receipt"] is True
    stage_receipt = json.loads(smoke_stage_output.read_text(encoding="utf-8"))
    assert stage_receipt["manifest_sha256"] == manifest_sha256
    assert stage_receipt["manifest_hash_matches_assembly_receipt"] is True


def test_cli_manifest_smoke_rejects_manifest_changed_after_assembly(tmp_path: Path) -> None:
    manifest_path = tmp_path / "runs" / "demo_001" / "provenance" / "manifest.yaml"
    smoke_output = manifest_path.parent / "validations" / "manifest_smoke.json"
    smoke_stage_output = manifest_path.parent / "logs" / "manifest_smoke.stage.json"
    manifest_path.parent.mkdir(parents=True)
    changed_manifest: dict[str, object] = {section: [{}] for section in REQUIRED_TOP_LEVEL_SECTIONS}
    changed_manifest["run"] = {"run_id": "demo_001", "run_root": "runs/demo_001"}
    changed_manifest["simulation_layout"] = {
        "run_root": "runs/demo_001",
        "provenance_root": "runs/demo_001/provenance",
    }
    manifest_path.write_text(yaml.safe_dump(changed_manifest), encoding="utf-8")
    original_manifest_bytes = manifest_path.read_bytes()
    assembly_receipt = smoke_stage_output.with_name("manifest.stage.json")
    assembly_receipt.parent.mkdir(parents=True)
    assembly_receipt.write_text(
        json.dumps(
            {
                "name": "manifest",
                "status": "pass",
                "return_code": 0,
                "evidence_path": assembly_receipt.relative_to(tmp_path).as_posix(),
                "manifest": manifest_path.relative_to(tmp_path).as_posix(),
                "manifest_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "smoke-manifest",
                str(manifest_path),
                "--output",
                str(smoke_output),
                "--config",
                "configs/run.synthetic.yaml",
                "--run-id",
                "demo_001",
                "--workspace-root",
                str(tmp_path),
                "--stage-output",
                str(smoke_stage_output),
            ]
        )
        == 1
    )
    smoke = json.loads(smoke_output.read_text(encoding="utf-8"))
    assert smoke["manifest_hash_matches_assembly_receipt"] is False
    assert "manifest SHA-256 does not match external assembly receipt" in smoke["semantic_errors"]
    assert manifest_path.read_bytes() == original_manifest_bytes
    assert json.loads(smoke_stage_output.read_text(encoding="utf-8"))["status"] == "fail"


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (lambda receipt: receipt.update(name="wrong"), "name must be 'manifest'"),
        (lambda receipt: receipt.update(status="fail"), "status must be 'pass'"),
        (lambda receipt: receipt.update(return_code=9), "return_code must be 0"),
        (
            lambda receipt: receipt.update(manifest="runs/demo_001/provenance/other.yaml"),
            "manifest path does not identify the checked manifest",
        ),
        (
            lambda receipt: receipt.update(
                evidence_path="runs/demo_001/provenance/logs/other.json"
            ),
            "evidence_path does not identify the receipt",
        ),
        (lambda receipt: receipt.clear(), "name must be 'manifest'"),
        (lambda _receipt: None, "must be a mapping"),
    ],
    ids=[
        "wrong-name",
        "failed-status-with-correct-hash",
        "nonzero-return",
        "wrong-manifest-path",
        "wrong-evidence-path",
        "missing-fields",
        "malformed-receipt",
    ],
)
def test_cli_manifest_smoke_rejects_invalid_external_assembly_receipt(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    mutation: Callable[[dict[str, object]], None],
    expected_error: str,
) -> None:
    manifest_path = tmp_path / "runs" / "demo_001" / "provenance" / "manifest.yaml"
    smoke_output = manifest_path.parent / "validations" / "manifest_smoke.json"
    smoke_stage_output = manifest_path.parent / "logs" / "manifest_smoke.stage.json"
    assembly_receipt_path = smoke_stage_output.with_name("manifest.stage.json")
    manifest_path.parent.mkdir(parents=True)
    assembly_receipt_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "manifest_version": "0.1",
                "run": {"run_id": "demo_001", "run_root": "runs/demo_001"},
                "simulation_layout": {
                    "run_root": "runs/demo_001",
                    "provenance_root": "runs/demo_001/provenance",
                },
            }
        ),
        encoding="utf-8",
    )
    original_manifest = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(original_manifest).hexdigest()
    receipt: dict[str, object] = {
        "name": "manifest",
        "status": "pass",
        "return_code": 0,
        "evidence_path": assembly_receipt_path.relative_to(tmp_path).as_posix(),
        "manifest": manifest_path.relative_to(tmp_path).as_posix(),
        "manifest_sha256": manifest_sha256,
    }
    mutation(receipt)
    serialized_receipt: object = [receipt] if expected_error == "must be a mapping" else receipt
    assembly_receipt_path.write_text(json.dumps(serialized_receipt), encoding="utf-8")
    monkeypatch.setattr(cli, "missing_required_sections", lambda *_args: ())
    monkeypatch.setattr(cli, "missing_required_key_values", lambda *_args: ())
    monkeypatch.setattr(cli, "semantic_consistency_errors", lambda *_args, **_kwargs: ())

    result = main(
        [
            "smoke-manifest",
            str(manifest_path),
            "--output",
            str(smoke_output),
            "--config",
            "configs/run.synthetic.yaml",
            "--run-id",
            "demo_001",
            "--workspace-root",
            str(tmp_path),
            "--stage-output",
            str(smoke_stage_output),
        ]
    )

    assert result == 1
    smoke = json.loads(smoke_output.read_text(encoding="utf-8"))
    assert any(expected_error in error for error in smoke["semantic_errors"])
    if expected_error != "must be a mapping" and receipt.get("manifest_sha256") == manifest_sha256:
        assert smoke["manifest_hash_matches_assembly_receipt"] is True
    assert manifest_path.read_bytes() == original_manifest
    assert json.loads(smoke_stage_output.read_text(encoding="utf-8"))["status"] == "fail"


@pytest.mark.parametrize(
    "case",
    [
        "cross-run-id",
        "cross-run-manifest",
        "cross-run-stage-output",
        "manifest-symlink-escape",
        "stage-output-symlink-escape",
        "receipt-symlink-escape",
    ],
)
def test_cli_manifest_smoke_rejects_mismatched_run_context_without_evidence(
    tmp_path: Path, case: str
) -> None:
    run_root = tmp_path / "runs" / "demo_001"
    provenance_root = run_root / "provenance"
    manifest_path = provenance_root / "manifest.yaml"
    stage_output = provenance_root / "logs" / "manifest_smoke.stage.json"
    smoke_output = provenance_root / "validations" / "manifest_smoke.json"
    manifest_path.parent.mkdir(parents=True)
    stage_output.parent.mkdir(parents=True)
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "manifest_version": "0.1",
                "run": {"run_id": "demo_001", "run_root": "runs/demo_001"},
                "simulation_layout": {
                    "run_root": "runs/demo_001",
                    "provenance_root": "runs/demo_001/provenance",
                },
            }
        ),
        encoding="utf-8",
    )
    run_id = "demo_001"
    supplied_manifest = manifest_path
    supplied_stage_output = stage_output
    escaped_target = tmp_path.parent / f"{tmp_path.name}-{case}-escape.json"
    receipt_path = stage_output.with_name("manifest.stage.json")
    if case == "cross-run-id":
        run_id = "demo_002"
    elif case == "cross-run-manifest":
        supplied_manifest = tmp_path / "runs/demo_002/provenance/manifest.yaml"
    elif case == "cross-run-stage-output":
        supplied_stage_output = tmp_path / "runs/demo_002/provenance/logs/manifest_smoke.stage.json"
    elif case == "manifest-symlink-escape":
        manifest_path.unlink()
        manifest_path.symlink_to(escaped_target)
    elif case == "stage-output-symlink-escape":
        stage_output.symlink_to(escaped_target)
    elif case == "receipt-symlink-escape":
        receipt_path.symlink_to(escaped_target)

    with pytest.raises(SystemExit, match="2"):
        main(
            [
                "smoke-manifest",
                str(supplied_manifest),
                "--output",
                str(smoke_output),
                "--config",
                "configs/run.synthetic.yaml",
                "--run-id",
                run_id,
                "--workspace-root",
                str(tmp_path),
                "--stage-output",
                str(supplied_stage_output),
            ]
        )

    assert not smoke_output.exists()
    assert not stage_output.exists()
    assert not (tmp_path / "runs/demo_002/provenance/logs/manifest_smoke.stage.json").exists()
    assert not escaped_target.exists()


def test_cli_assembles_run_manifest_from_workflow_evidence(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    controlled_repo = tmp_path / "controlled-source-demo"
    _init_controlled_source_repo(controlled_repo)
    selected_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=controlled_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    run_root = tmp_path / "runs" / "demo_001"
    sim_root = run_root / "sim-run-root"
    provenance_root = run_root / "provenance"
    inventories_root = provenance_root / "inventories"
    logs_root = provenance_root / "logs"
    validations_root = provenance_root / "validations"
    scheduler_root = provenance_root / "scheduler"
    for directory in (inventories_root, logs_root, validations_root, scheduler_root):
        directory.mkdir(parents=True, exist_ok=True)
    (sim_root / "procs").mkdir(parents=True, exist_ok=True)

    _write_json(
        provenance_root / "preflight.json",
        {
            "status": "pass",
            "wrapper_repo": {
                "path": tmp_path.as_posix(),
                "head_commit": "f" * 40,
                "clean_policy": "configured_paths_only",
            },
            "controlled_source_repo": {
                "path": controlled_repo.as_posix(),
                "ref": "controlled-source-demo-v0.1.2",
                "resolved_commit": selected_commit,
                "head_commit": selected_commit,
                "branch": "admitted-branch",
                "describe": "controlled-source-demo-v0.1.2",
                "is_clean": True,
            },
            "controlled_scripts": [{"name": "run_script", "relative_path": "procs/run-script.sh"}],
            "wrapper_factory_definition": [],
            "controlled_artifacts": [
                {
                    "role": "controlled_script",
                    "relative_path": relative_path,
                    "selected_commit": selected_commit,
                    "blob_oid": f"blob-{index}",
                    "file_mode": "100755",
                    "size_bytes": 20,
                    "sha256": str(index) * 64,
                    "executable": True,
                }
                for index, relative_path in enumerate(
                    (
                        "procs/run-script.sh",
                        "scripts/synthetic_sim_engine.sh",
                        "scripts/extract_required.pl",
                        "scripts/ad_hoc_extract.py",
                    ),
                    start=1,
                )
            ],
        },
    )
    _write_json(
        inventories_root / "pre_run_inputs.json",
        [
            {
                "relative_path": "input/dirC/ex1.dat",
                "run_relative_path": "runs/demo_001/sim-run-root/input/dirC/ex1.dat",
                "sim_area": "input",
                "logical_group": "dirC",
                "role": "input",
                "sha256": "a" * 64,
                "hash_status": "hashed",
            }
        ],
    )
    _write_json(
        inventories_root / "pre_run_controlled_scripts.json",
        [
            {
                "relative_path": "procs/run-script.sh",
                "run_relative_path": "runs/demo_001/sim-run-root/procs/run-script.sh",
                "role": "runtime_script",
                "sha256": "b" * 64,
                "hash_status": "hashed",
            }
        ],
    )
    _write_json(
        inventories_root / "post_run_raw_outputs.json",
        [
            {
                "relative_path": "lists/dirC/sim-out.dat",
                "workflow_relative_path": "sim-run-root/lists/dirC/sim-out.dat",
                "sim_area": "lists",
                "logical_group": "dirC",
                "role": "raw_output",
                "sha256": "c" * 64,
                "hash_status": "hashed",
            }
        ],
    )
    _write_json(
        inventories_root / "post_run_derived_products.json",
        [
            {
                "relative_path": "products/extracted/required.csv",
                "workflow_relative_path": "provenance/products/extracted/required.csv",
                "product_area": "extracted",
                "role": "extracted_product",
                "producing_stage": "extract_required",
                "sha256": "d" * 64,
            }
        ],
    )
    _write_json(
        validations_root / "required_extract.json",
        {"path": "products/extracted/required.csv", "status": "pass", "checks": []},
    )
    (logs_root / "run_simulation.stdout.log").write_text("ok\n", encoding="utf-8")
    (logs_root / "run_simulation.stderr.log").write_text("", encoding="utf-8")
    _write_json(
        logs_root / "run_simulation.stage.json",
        {
            "name": "run_simulation",
            "command": "procs/run-script.sh",
            "status": "pass",
            "return_code": 0,
            "logs": {
                "stdout": "runs/demo_001/provenance/logs/run_simulation.stdout.log",
                "stderr": "runs/demo_001/provenance/logs/run_simulation.stderr.log",
            },
        },
    )
    _write_json(
        scheduler_root / "job-state.json",
        {
            "run_id": "demo_001",
            "scheduler": "mock_lsf",
            "job_id": "mock-demo_001",
            "state": "DONE",
            "exit_code": 0,
            "payload_stage_evidence": "runs/demo_001/provenance/logs/run_simulation.stage.json",
        },
    )
    _write_json(
        scheduler_root / "terminal-state.json",
        {
            "run_id": "demo_001",
            "scheduler": "mock_lsf",
            "job_id": "mock-demo_001",
            "state": "DONE",
            "exit_code": 0,
            "payload_stage_evidence": "runs/demo_001/provenance/logs/run_simulation.stage.json",
        },
    )
    (scheduler_root / "accounting.yaml").write_text(
        yaml.safe_dump(
            {
                "run_id": "demo_001",
                "scheduler": "mock_lsf",
                "job_id": "mock-demo_001",
                "state": "DONE",
                "exit_code": 0,
                "job_state_path": "runs/demo_001/provenance/scheduler/job-state.json",
                "payload_stage_evidence": "runs/demo_001/provenance/logs/run_simulation.stage.json",
                "future_real_lsf_equivalent": ["bjobs", "bhist", "bacct"],
            }
        ),
        encoding="utf-8",
    )
    (scheduler_root / "submission.yaml").write_text(
        yaml.safe_dump(
            {
                "mode": "mock_lsf",
                "scheduler": "mock_lsf",
                "metadata_path": "runs/demo_001/provenance/scheduler/submission.yaml",
                "submission": {"job_id": "mock-demo_001", "state": "RUN"},
                "job_state_path": "runs/demo_001/provenance/scheduler/job-state.json",
                "terminal_state_path": "runs/demo_001/provenance/scheduler/terminal-state.json",
                "accounting_path": "runs/demo_001/provenance/scheduler/accounting.yaml",
            }
        ),
        encoding="utf-8",
    )
    manifest_path = provenance_root / "manifest.yaml"

    # Admission is the identity boundary: later HEAD/ref/worktree movement must not
    # affect finalization.
    run_script = controlled_repo / "procs" / "run-script.sh"
    run_script.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=controlled_repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "move HEAD after admission",
        ],
        cwd=controlled_repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "tag", "--force", "controlled-source-demo-v0.1.2"],
        cwd=controlled_repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    run_script.write_text("dirty after admission\n", encoding="utf-8")

    assert (
        main(
            [
                "assemble-run-manifest",
                "--run-id",
                "demo_001",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--controlled-source-ref",
                "controlled-source-demo-v0.1.2",
                "--output",
                str(manifest_path),
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out)["status"] == "pass"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert tuple(manifest)[: len(REQUIRED_TOP_LEVEL_SECTIONS)] == REQUIRED_TOP_LEVEL_SECTIONS
    assert manifest["run"]["run_id"] == "demo_001"
    assert manifest["repositories"][1]["requested_ref"] == "controlled-source-demo-v0.1.2"
    assert manifest["repositories"][1]["resolved_commit"] == selected_commit
    assert manifest["repositories"][1]["head_commit"] == selected_commit
    assert manifest["repositories"][1]["branch"] == "admitted-branch"
    assert manifest["repositories"][1]["describe"] == "controlled-source-demo-v0.1.2"
    assert manifest["repositories"][1]["identity_source"] == "preflight_admission"
    assert manifest["repositories"][1]["tracked_script_paths"] == [
        "procs/run-script.sh",
        "scripts/synthetic_sim_engine.sh",
        "scripts/extract_required.pl",
        "scripts/ad_hoc_extract.py",
    ]
    assert len(manifest["repositories"][1]["scripts"][0]["sha256"]) == 64
    assert manifest["repositories"][1]["scripts"][0]["hash_status"] == "hashed"
    assert manifest["controlled_source_gate"]["status"] == "pass"
    assert manifest["scheduler"]["mode"] == "mock_lsf"
    assert manifest["scheduler"]["job_id"] == "mock-demo_001"
    assert manifest["scheduler"]["final_state"] == "DONE"
    assert manifest["scheduler"]["evidence"] == {
        "submission": "runs/demo_001/provenance/scheduler/submission.yaml",
        "job_state": "runs/demo_001/provenance/scheduler/job-state.json",
        "terminal_state": "runs/demo_001/provenance/scheduler/terminal-state.json",
        "accounting": "runs/demo_001/provenance/scheduler/accounting.yaml",
        "payload_stage": "runs/demo_001/provenance/logs/run_simulation.stage.json",
        "stdout_log": None,
        "stderr_log": None,
    }
    assert manifest["scheduler"]["terminal_job_state"]["state"] == "DONE"
    assert manifest["scheduler"]["accounting"]["job_state_path"].endswith("job-state.json")
    assert manifest["inputs"][0]["logical_group"] == "dirC"
    assert manifest["runtime_scripts"][0]["role"] == "runtime_script"
    assert manifest["stages"][0]["status"] == "pass"
    assert manifest["raw_simulation_outputs"][0]["sim_area"] == "lists"
    assert manifest["derived_products"][0]["producing_stage"] == "extract_required"
    assert manifest["validations"][0]["status"] == "pass"
    assert manifest["validations"][0]["evidence_path"].endswith("required_extract.json")
    assert len(manifest["validations"][0]["sha256"]) == 64
    assert {log["stream"] for log in manifest["logs"]} == {"stdout", "stderr"}
    assert manifest["hash_policy"]["algorithm"] == "sha256"


def _init_controlled_source_repo(path: Path) -> None:
    for relative_path in (
        "procs/run-script.sh",
        "scripts/synthetic_sim_engine.sh",
        "scripts/extract_required.pl",
        "scripts/ad_hoc_extract.py",
    ):
        target = path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "seed controlled source",
        ],
        cwd=path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "tag", "controlled-source-demo-v0.1.2"],
        cwd=path,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
