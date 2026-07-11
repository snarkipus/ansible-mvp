import json
from pathlib import Path
from typing import Any, cast

import pytest
from openpyxl import load_workbook

import provenance.reports as reports
from provenance.cli import main
from provenance.reports import build_report_product_evidence


def _write_extracted_products(root: Path, run_id: str) -> Path:
    extracted = root / "runs" / run_id / "provenance" / "products" / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "required.csv").write_text(
        "logical_group,example,bytes,sha256_prefix\ndirC,ex1.dat,11,aaaa\ndirC,ex2.dat,22,bbbb\n",
        encoding="utf-8",
    )
    (extracted / "ad_hoc.csv").write_text(
        "logical_group,input_count,total_bytes\ndirC,2,33\n",
        encoding="utf-8",
    )
    provenance = root / "runs" / run_id / "provenance"
    validations = provenance / "validations"
    validations.mkdir()
    for name in ("required_extract", "ad_hoc_extract"):
        (validations / f"{name}.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    return provenance


def test_build_report_products_writes_expected_derived_artifacts(tmp_path: Path) -> None:
    run_id = "report_demo"
    provenance_root = _write_extracted_products(tmp_path, run_id)

    evidence = cast(
        list[dict[str, Any]], build_report_product_evidence(run_id=run_id, workspace_root=tmp_path)
    )

    by_name = {Path(record["relative_path"]).name: record for record in evidence}
    assert set(by_name) == {"summary.xlsx", "chart.png", "briefing.pptx"}
    for record in evidence:
        assert record["relative_path"].startswith("provenance/products/reports/")
        assert record["product_area"] == "reports"
        assert record["role"] == "report_product"
        assert record["producing_stage"] == "build_reports"
        assert isinstance(record["size_bytes"], int) and record["size_bytes"] > 0
        assert isinstance(record["mtime_ns"], int) and record["mtime_ns"] > 0
        assert isinstance(record["sha256"], str) and len(record["sha256"]) == 64

    workbook = load_workbook(provenance_root / "products" / "reports" / "summary.xlsx")
    assert workbook["summary"]["B2"].value == 2
    assert not list((provenance_root / "products" / "reports").glob(".report.*"))
    assert not (tmp_path / "runs" / run_id / "sim-run-root" / "products" / "reports").exists()


def test_cli_build_reports_writes_inventory_evidence(tmp_path: Path) -> None:
    run_id = "cli_report_demo"
    provenance_root = _write_extracted_products(tmp_path, run_id)
    output = provenance_root / "inventories" / "report_products.json"

    assert (
        main(
            [
                "build-reports",
                "--run-id",
                run_id,
                "--workspace-root",
                str(tmp_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert output.exists()
    assert (provenance_root / "products" / "reports" / "summary.xlsx").exists()
    assert (provenance_root / "products" / "reports" / "chart.png").exists()
    assert (provenance_root / "products" / "reports" / "briefing.pptx").exists()


def test_cli_build_reports_writes_stage_status_evidence(tmp_path: Path) -> None:
    run_id = "cli_report_stage_demo"
    provenance_root = _write_extracted_products(tmp_path, run_id)
    inventory_output = provenance_root / "inventories" / "report_products.json"
    stage_output = provenance_root / "logs" / "build_reports.stage.json"

    assert (
        main(
            [
                "build-reports",
                "--run-id",
                run_id,
                "--workspace-root",
                str(tmp_path),
                "--output",
                str(inventory_output),
                "--stage-output",
                str(stage_output),
            ]
        )
        == 0
    )

    evidence = json.loads(stage_output.read_text(encoding="utf-8"))
    assert evidence["name"] == "build_reports"
    assert evidence["status"] == "pass"
    assert evidence["return_code"] == 0
    assert evidence["started_at"].endswith("Z")
    assert evidence["logs"]["stdout"] == f"runs/{run_id}/provenance/logs/build_reports.stdout.log"
    assert evidence["outputs"][0]["relative_path"].startswith("provenance/products/reports/")
    assert (provenance_root / "logs" / "build_reports.stdout.log").is_file()


def test_report_generation_requires_both_passed_input_validations(tmp_path: Path) -> None:
    run_id = "invalid_report_input"
    provenance_root = _write_extracted_products(tmp_path, run_id)
    (provenance_root / "validations" / "ad_hoc_extract.json").write_text(
        json.dumps({"status": "fail"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="requires passed ad_hoc_extract validation"):
        build_report_product_evidence(run_id=run_id, workspace_root=tmp_path)

    reports_root = provenance_root / "products" / "reports"
    assert not any(reports_root.iterdir())


def test_report_validation_failure_preserves_existing_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = "report_failure"
    provenance_root = _write_extracted_products(tmp_path, run_id)
    reports_root = provenance_root / "products" / "reports"
    reports_root.mkdir()
    existing = {name: f"existing {name}\n" for name in reports.REPORT_FILENAMES}
    for name, content in existing.items():
        (reports_root / name).write_text(content, encoding="utf-8")

    def fail_validation(_paths: dict[str, Path]) -> None:
        raise ValueError("generated report failed validation")

    monkeypatch.setattr(reports, "_validate_report_products", fail_validation)

    with pytest.raises(ValueError, match="generated report failed validation"):
        build_report_product_evidence(run_id=run_id, workspace_root=tmp_path)

    for name, content in existing.items():
        assert (reports_root / name).read_text(encoding="utf-8") == content
    assert not list(reports_root.glob(".report.*"))
