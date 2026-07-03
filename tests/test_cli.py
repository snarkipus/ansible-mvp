import json
import subprocess
from pathlib import Path

import yaml

from provenance.cli import main
from provenance.manifest import REQUIRED_TOP_LEVEL_SECTIONS


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
                        "source_ref": "controlled-source-demo-v0.1.0",
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
                        "source_ref": "controlled-source-demo-v0.1.0",
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
    (provenance_root / "products" / "reports" / "summary.xlsx").write_text(
        "report\n", encoding="utf-8"
    )

    assert main(["inventory-post", "--run-id", "demo_001", "--workspace-root", str(tmp_path)]) == 0

    summary = json.loads(capsys.readouterr().out)
    raw_outputs = json.loads(
        (inventory_root / "post_run_raw_outputs.json").read_text(encoding="utf-8")
    )
    products = json.loads(
        (inventory_root / "post_run_derived_products.json").read_text(encoding="utf-8")
    )
    assert summary["raw_output_count"] == 1
    assert summary["derived_product_count"] == 2
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
                "run": {"run_id": "demo_001", "run_root": "runs/demo_001"},
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
    assert main(["smoke-manifest", str(manifest_path)]) == 0

    smoke = json.loads(capsys.readouterr().out)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert smoke["missing_required_sections"] == []
    assert smoke["missing_required_key_values"] == []
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

    assert main(["smoke-manifest", str(manifest_path)]) == 1

    smoke = json.loads(capsys.readouterr().out)
    assert smoke["status"] == "fail"
    assert smoke["missing_required_sections"] == []
    assert "run.run_id" in smoke["missing_required_key_values"]


def test_cli_assembles_run_manifest_from_workflow_evidence(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    controlled_repo = tmp_path / "controlled-source-demo"
    _init_controlled_source_repo(controlled_repo)
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
            "controlled_source_repo": {
                "path": controlled_repo.as_posix(),
                "ref": "controlled-source-demo-v0.1.0",
            },
            "controlled_scripts": [{"name": "run_script", "relative_path": "procs/run-script.sh"}],
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
    (scheduler_root / "submission.yaml").write_text(
        yaml.safe_dump(
            {
                "mode": "mock_lsf",
                "scheduler": "mock_lsf",
                "metadata_path": "runs/demo_001/provenance/scheduler/submission.yaml",
            }
        ),
        encoding="utf-8",
    )
    manifest_path = provenance_root / "manifest.yaml"

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
                "controlled-source-demo-v0.1.0",
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
    assert manifest["repositories"][1]["requested_ref"] == "controlled-source-demo-v0.1.0"
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
    assert manifest["inputs"][0]["logical_group"] == "dirC"
    assert manifest["runtime_scripts"][0]["role"] == "runtime_script"
    assert manifest["stages"][0]["status"] == "pass"
    assert manifest["raw_simulation_outputs"][0]["sim_area"] == "lists"
    assert manifest["derived_products"][0]["producing_stage"] == "extract_required"
    assert manifest["validations"][0]["status"] == "pass"
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
        ["git", "tag", "controlled-source-demo-v0.1.0"],
        cwd=path,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
