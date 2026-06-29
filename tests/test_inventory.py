from __future__ import annotations

from pathlib import Path

import pytest

from provenance.inventory import InventoryMetadata, infer_metadata, inventory_files, with_sha256


def test_inventory_distinguishes_repeated_logical_groups_by_full_context(tmp_path: Path) -> None:
    for sim_area in ("input", "lists", "files"):
        for logical_group in ("dirA", "dirB", "dirC"):
            artifact = tmp_path / sim_area / logical_group / "ex1.dat"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(f"{sim_area}/{logical_group}\n", encoding="utf-8")

    records = inventory_files(tmp_path)

    assert len(records) == 9
    assert len({record.identity for record in records}) == 9
    assert ("input/dirA/ex1.dat", "input", "dirA") in {record.identity for record in records}
    assert ("lists/dirA/ex1.dat", "lists", "dirA") in {record.identity for record in records}
    assert ("files/dirA/ex1.dat", "files", "dirA") in {record.identity for record in records}
    assert {record.relative_path for record in records if record.logical_group == "dirC"} == {
        "files/dirC/ex1.dat",
        "input/dirC/ex1.dat",
        "lists/dirC/ex1.dat",
    }


def test_inventory_uses_root_relative_paths_and_deterministic_order(tmp_path: Path) -> None:
    (tmp_path / "lists" / "dirC").mkdir(parents=True)
    (tmp_path / "input" / "dirA").mkdir(parents=True)
    (tmp_path / "lists" / "dirC" / "sim-out.dat").write_text("raw\n", encoding="utf-8")
    (tmp_path / "input" / "dirA" / "ex1.dat").write_text("input\n", encoding="utf-8")

    records = inventory_files(tmp_path)

    assert [record.relative_path for record in records] == [
        "input/dirA/ex1.dat",
        "lists/dirC/sim-out.dat",
    ]
    assert all(not record.relative_path.startswith(str(tmp_path)) for record in records)
    raw_output = records[1]
    assert raw_output.sim_area == "lists"
    assert raw_output.logical_group == "dirC"
    assert raw_output.role == "raw_output"
    assert raw_output.size_bytes == 4
    assert raw_output.mtime_ns > 0
    assert raw_output.mtime_utc.endswith("Z")


def test_inventory_allows_caller_provided_metadata_and_hash_placeholder(tmp_path: Path) -> None:
    product = tmp_path / "custom" / "summary.xlsx"
    product.parent.mkdir()
    product.write_text("report\n", encoding="utf-8")

    records = inventory_files(
        tmp_path,
        metadata_by_path={
            "custom/summary.xlsx": InventoryMetadata(
                area_type="product",
                product_area="reports",
                logical_group="summary",
                role="report_product",
            )
        },
    )

    assert records[0].relative_path == "custom/summary.xlsx"
    assert records[0].area_type == "product"
    assert records[0].product_area == "reports"
    assert records[0].logical_group == "summary"
    assert records[0].role == "report_product"
    assert records[0].sha256 is None
    assert with_sha256(records[0], "abc123").sha256 == "abc123"


def test_infer_metadata_for_canonical_products_and_runtime_scripts() -> None:
    report = infer_metadata("products/reports/briefing.pptx")
    extracted = infer_metadata("products/extracted/required.csv")
    proc = infer_metadata("procs/run-script.sh")

    assert report.area_type == "product"
    assert report.product_area == "reports"
    assert report.role == "report_product"
    assert extracted.role == "extracted_product"
    assert proc.area_type == "simulation"
    assert proc.sim_area == "procs"
    assert proc.role == "runtime_script"


def test_inventory_rejects_missing_or_non_directory_roots(tmp_path: Path) -> None:
    file_root = tmp_path / "not-dir"
    file_root.write_text("x", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        inventory_files(tmp_path / "missing")
    with pytest.raises(NotADirectoryError):
        inventory_files(file_root)
    with pytest.raises(ValueError):
        inventory_files(tmp_path, metadata_by_path={"../escape": InventoryMetadata()})
