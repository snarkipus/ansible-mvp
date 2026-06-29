import json
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


def test_cli_assembles_and_smoke_validates_manifest(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    input_yaml = tmp_path / "manifest-input.yaml"
    manifest_path = tmp_path / "manifest.yaml"
    input_yaml.write_text(
        yaml.safe_dump(
            {
                "run": {"run_id": "demo_001"},
                "repositories": [],
                "simulation_layout": {"sim_run_root": "runs/demo_001/sim-run-root"},
                "controlled_source_gate": {"status": "pass"},
                "scheduler": {"mode": "mock_lsf"},
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
    assert tuple(manifest)[: len(REQUIRED_TOP_LEVEL_SECTIONS)] == REQUIRED_TOP_LEVEL_SECTIONS
