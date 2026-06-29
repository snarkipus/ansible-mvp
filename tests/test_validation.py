from __future__ import annotations

from pathlib import Path

from provenance.validation import CSVShapeExpectation, ValidationStatus, validate_csv_product


def test_validate_csv_product_records_passing_shape_evidence(tmp_path: Path) -> None:
    product = tmp_path / "provenance" / "products" / "extracted" / "required.csv"
    product.parent.mkdir(parents=True)
    product.write_text("case,value\na,1\nb,2\n", encoding="utf-8")

    evidence = validate_csv_product(
        product,
        CSVShapeExpectation(
            expected_data_rows=2,
            minimum_data_rows=1,
            expected_column_count=2,
            expected_header=("case", "value"),
        ),
        display_path="products/extracted/required.csv",
    )

    assert evidence.status is ValidationStatus.PASS
    assert evidence.passed is True
    assert evidence.total_rows == 3
    assert evidence.data_rows == 2
    assert evidence.header == ("case", "value")
    assert evidence.column_counts == (2, 2, 2)
    assert [check.name for check in evidence.checks] == [
        "exists",
        "is_file",
        "non_empty",
        "data_row_count",
        "minimum_data_row_count",
        "column_count",
        "header",
    ]
    assert evidence.to_dict() == {
        "path": "products/extracted/required.csv",
        "status": "pass",
        "size_bytes": product.stat().st_size,
        "total_rows": 3,
        "data_rows": 2,
        "header": ["case", "value"],
        "column_counts": [2, 2, 2],
        "checks": [check.to_dict() for check in evidence.checks],
    }


def test_validate_csv_product_reports_missing_file_without_shape_checks(tmp_path: Path) -> None:
    evidence = validate_csv_product(
        tmp_path / "missing.csv",
        CSVShapeExpectation(expected_column_count=2, expected_header=("a", "b")),
    )

    assert evidence.status is ValidationStatus.FAIL
    assert evidence.size_bytes is None
    assert [check.name for check in evidence.checks] == ["exists"]
    assert evidence.checks[0].actual is False
    assert evidence.checks[0].message == "CSV product does not exist"


def test_validate_csv_product_reports_directory_as_not_file(tmp_path: Path) -> None:
    directory = tmp_path / "products" / "extracted"
    directory.mkdir(parents=True)

    evidence = validate_csv_product(directory, CSVShapeExpectation())

    assert evidence.status is ValidationStatus.FAIL
    assert [check.name for check in evidence.checks] == ["exists", "is_file"]
    assert evidence.checks[1].actual is False
    assert evidence.checks[1].message == "CSV product is not a regular file"


def test_validate_csv_product_reports_empty_file_and_shape_failures(tmp_path: Path) -> None:
    product = tmp_path / "empty.csv"
    product.write_text("", encoding="utf-8")

    evidence = validate_csv_product(
        product,
        CSVShapeExpectation(
            minimum_data_rows=1,
            expected_column_count=2,
            expected_header=("case", "value"),
        ),
    )

    checks = {check.name: check for check in evidence.checks}
    assert evidence.status is ValidationStatus.FAIL
    assert checks["non_empty"].actual == 0
    assert checks["minimum_data_row_count"].actual == 0
    assert checks["column_count"].actual == []
    assert checks["header"].actual is None
    assert evidence.to_dict()["checks"][2]["message"] == "CSV product is empty"


def test_validate_csv_product_reports_row_column_and_header_mismatches(tmp_path: Path) -> None:
    product = tmp_path / "required.csv"
    product.write_text("case,value\na,1\nb\n", encoding="utf-8")

    evidence = validate_csv_product(
        product,
        CSVShapeExpectation(
            expected_data_rows=3,
            expected_column_count=2,
            expected_header=("case", "score"),
        ),
    )

    checks = {check.name: check for check in evidence.checks}
    assert evidence.status is ValidationStatus.FAIL
    assert checks["data_row_count"].expected == 3
    assert checks["data_row_count"].actual == 2
    assert checks["column_count"].actual == [2, 2, 1]
    assert checks["header"].actual == ["case", "value"]
