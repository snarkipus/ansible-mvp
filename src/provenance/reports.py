"""Minimal derived report generation for the provenance MVP."""

from __future__ import annotations

import csv
import struct
import zlib
from importlib import import_module
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from provenance.hashing import hash_artifact
from provenance.inventory import InventoryRecord, inventory_files, with_sha256

REPORT_FILENAMES = ("summary.xlsx", "chart.png", "briefing.pptx")


def build_report_products(
    *,
    run_id: str,
    workspace_root: Path | str = Path("."),
    required_csv: Path | str | None = None,
    ad_hoc_csv: Path | str | None = None,
) -> tuple[InventoryRecord, ...]:
    """Generate the MVP XLSX, PNG chart, and PPTX report products.

    Products are always written under
    ``runs/{run_id}/provenance/products/reports`` and summarized as hashed
    derived-product inventory records.
    """

    if not run_id:
        raise ValueError("run_id must be non-empty")

    root = Path(workspace_root).expanduser().resolve()
    provenance_root = root / "runs" / run_id / "provenance"
    extracted_root = provenance_root / "products" / "extracted"
    required_path = _resolve_product_path(required_csv, extracted_root / "required.csv")
    ad_hoc_path = _resolve_product_path(ad_hoc_csv, extracted_root / "ad_hoc.csv")
    reports_root = provenance_root / "products" / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)

    required_rows = _read_csv(required_path)
    ad_hoc_rows = _read_csv(ad_hoc_path)

    _write_summary_workbook(reports_root / "summary.xlsx", required_rows, ad_hoc_rows)
    _write_chart(reports_root / "chart.png", ad_hoc_rows)
    _write_briefing(reports_root / "briefing.pptx", run_id, required_rows, ad_hoc_rows)

    records = inventory_files(reports_root)
    return tuple(
        _report_inventory_record(record, reports_root / record.relative_path) for record in records
    )


def build_report_product_evidence(
    *,
    run_id: str,
    workspace_root: Path | str = Path("."),
) -> tuple[dict[str, str | int | None], ...]:
    """Generate reports and return manifest-ready derived product evidence."""

    records = build_report_products(run_id=run_id, workspace_root=workspace_root)
    return tuple(_report_evidence(record) for record in records)


def _resolve_product_path(path: Path | str | None, default: Path) -> Path:
    candidate = default if path is None else Path(path)
    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise FileNotFoundError(f"required report input does not exist: {candidate}")
    return candidate


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file_obj:
        return list(csv.DictReader(file_obj))


def _write_summary_workbook(
    path: Path, required_rows: list[dict[str, str]], ad_hoc_rows: list[dict[str, str]]
) -> None:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "summary"
    summary.append(("metric", "value"))
    summary.append(("required_rows", len(required_rows)))
    summary.append(("ad_hoc_groups", len(ad_hoc_rows)))

    required_sheet = workbook.create_sheet("required_extract")
    _append_rows(required_sheet, required_rows)
    ad_hoc_sheet = workbook.create_sheet("ad_hoc_extract")
    _append_rows(ad_hoc_sheet, ad_hoc_rows)
    workbook.save(path)


def _append_rows(sheet: object, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    headers = list(rows[0])
    sheet.append(headers)  # type: ignore[attr-defined]
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])  # type: ignore[attr-defined]


def _write_chart(path: Path, ad_hoc_rows: list[dict[str, str]]) -> None:
    values = [_safe_int(row.get("total_bytes")) for row in ad_hoc_rows] or [0]
    path.write_bytes(_bar_chart_png(values))


def _write_briefing(
    path: Path, run_id: str, required_rows: list[dict[str, str]], ad_hoc_rows: list[dict[str, str]]
) -> None:
    presentation_factory: Any = import_module("pptx").Presentation
    inches: Any = import_module("pptx.util").Inches
    presentation = presentation_factory()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Synthetic provenance report"
    text_box = slide.shapes.add_textbox(inches(0.8), inches(1.4), inches(8), inches(2.2))
    text_frame = text_box.text_frame
    text_frame.text = f"Run ID: {run_id}"
    for line in (
        f"Required extract rows: {len(required_rows)}",
        f"Ad hoc groups: {len(ad_hoc_rows)}",
        "Products are generated under provenance/products/reports.",
    ):
        paragraph = text_frame.add_paragraph()
        paragraph.text = line
    presentation.save(path)


def _safe_int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0


def _bar_chart_png(values: list[int]) -> bytes:
    width = 320
    height = 180
    margin = 24
    background = (255, 255, 255)
    axis = (80, 80, 80)
    bar = (79, 129, 189)
    pixels = [[background for _x in range(width)] for _y in range(height)]
    for x_coord in range(margin, width - margin):
        pixels[height - margin][x_coord] = axis
    for y_coord in range(margin, height - margin + 1):
        pixels[y_coord][margin] = axis

    max_value = max(values) or 1
    slot_width = max(1, (width - (2 * margin)) // len(values))
    for index, value in enumerate(values):
        bar_height = int((height - (2 * margin) - 1) * value / max_value)
        start_x = margin + (index * slot_width) + 4
        end_x = min(margin + ((index + 1) * slot_width) - 4, width - margin - 1)
        top_y = height - margin - bar_height
        for y_coord in range(top_y, height - margin):
            for x_coord in range(start_x, end_x + 1):
                pixels[y_coord][x_coord] = bar

    raw_rows = b"".join(b"\x00" + b"".join(bytes(pixel) for pixel in row) for row in pixels)
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(raw_rows)),
            _png_chunk(b"IEND", b""),
        )
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _report_inventory_record(record: InventoryRecord, path: Path) -> InventoryRecord:
    sha256 = hash_artifact(path, display_path=f"products/reports/{record.relative_path}").sha256
    return with_sha256(record, sha256 or "")


def _report_evidence(record: InventoryRecord) -> dict[str, str | int | None]:
    payload = record.to_dict()
    payload.update(
        {
            "relative_path": f"provenance/products/reports/{record.relative_path}",
            "area_type": "product",
            "product_area": "reports",
            "role": "report_product",
            "producing_stage": "build_reports",
        }
    )
    return payload
