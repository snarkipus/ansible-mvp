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
