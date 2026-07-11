"""CSV and file validation helpers for provenance evidence.

The MVP uses lightweight shape checks for generated CSV products. Results are
represented as deterministic dataclasses so later manifest assembly can serialize
validation evidence without re-reading products.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class ValidationStatus(StrEnum):
    """Manifest-friendly validation status values."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class CSVShapeExpectation:
    """Expected CSV shape checks for one generated product.

    ``expected_data_rows`` is an exact data-row count excluding the header row.
    ``minimum_data_rows`` supports the configured minimum-row requirement called
    out by the provenance manifest spec. When both are omitted, row counting is
    still recorded as evidence but does not affect pass/fail status.
    """

    expected_data_rows: int | None = None
    minimum_data_rows: int | None = None
    expected_column_count: int | None = None
    expected_header: tuple[str, ...] | None = None
    expected_column_values: dict[str, tuple[str, ...]] | None = None
    integer_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationCheck:
    """One atomic validation check and its expected/actual evidence."""

    name: str
    status: ValidationStatus
    expected: Any = None
    actual: Any = None
    message: str | None = None

    @property
    def passed(self) -> bool:
        """Return true when this check passed."""

        return self.status is ValidationStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic mapping for JSON/YAML serialization."""

        return {
            "name": self.name,
            "status": self.status.value,
            "expected": self.expected,
            "actual": self.actual,
            "message": self.message,
        }


@dataclass(frozen=True)
class CSVValidationEvidence:
    """Validation evidence for one CSV product."""

    path: str
    status: ValidationStatus
    checks: tuple[ValidationCheck, ...]
    size_bytes: int | None = None
    sha256: str | None = None
    total_rows: int | None = None
    data_rows: int | None = None
    header: tuple[str, ...] | None = None
    column_counts: tuple[int, ...] = ()

    @property
    def passed(self) -> bool:
        """Return true when all required validation checks passed."""

        return self.status is ValidationStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic mapping for JSON/YAML serialization."""

        return {
            "path": self.path,
            "status": self.status.value,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "total_rows": self.total_rows,
            "data_rows": self.data_rows,
            "header": list(self.header) if self.header is not None else None,
            "column_counts": list(self.column_counts),
            "checks": [check.to_dict() for check in self.checks],
        }


def validate_csv_product(
    path: Path | str,
    expectation: CSVShapeExpectation,
    *,
    display_path: str | None = None,
) -> CSVValidationEvidence:
    """Validate a generated CSV product and return manifest-ready evidence."""

    product = Path(path)
    record_path = display_path or product.as_posix()
    checks: list[ValidationCheck] = []

    exists = product.exists()
    checks.append(
        _check(
            "exists",
            passed=exists,
            expected=True,
            actual=exists,
            message=None if exists else "CSV product does not exist",
        )
    )
    if not exists:
        return _evidence(record_path, checks)

    is_file = product.is_file()
    checks.append(
        _check(
            "is_file",
            passed=is_file,
            expected=True,
            actual=is_file,
            message=None if is_file else "CSV product is not a regular file",
        )
    )
    if not is_file:
        return _evidence(record_path, checks)

    product_bytes = product.read_bytes()
    size_bytes = len(product_bytes)
    sha256 = hashlib.sha256(product_bytes).hexdigest()
    checks.append(
        _check(
            "non_empty",
            passed=size_bytes > 0,
            expected="> 0 bytes",
            actual=size_bytes,
            message=None if size_bytes > 0 else "CSV product is empty",
        )
    )

    rows = _read_csv_rows(product_bytes)
    total_rows = len(rows)
    header = tuple(rows[0]) if rows else None
    data_rows = max(total_rows - 1, 0) if header is not None else 0
    column_counts = tuple(len(row) for row in rows)

    if expectation.expected_data_rows is not None:
        checks.append(
            _check(
                "data_row_count",
                passed=data_rows == expectation.expected_data_rows,
                expected=expectation.expected_data_rows,
                actual=data_rows,
                message=None
                if data_rows == expectation.expected_data_rows
                else "CSV data row count does not match expected count",
            )
        )

    if expectation.minimum_data_rows is not None:
        checks.append(
            _check(
                "minimum_data_row_count",
                passed=data_rows >= expectation.minimum_data_rows,
                expected=f">= {expectation.minimum_data_rows}",
                actual=data_rows,
                message=None
                if data_rows >= expectation.minimum_data_rows
                else "CSV data row count is below minimum",
            )
        )

    if expectation.expected_column_count is not None:
        expected_columns = expectation.expected_column_count
        checks.append(
            _check(
                "column_count",
                passed=bool(column_counts)
                and all(count == expected_columns for count in column_counts),
                expected=expected_columns,
                actual=list(column_counts),
                message=None
                if bool(column_counts) and all(count == expected_columns for count in column_counts)
                else "One or more CSV rows do not match expected column count",
            )
        )

    if expectation.expected_header is not None:
        checks.append(
            _check(
                "header",
                passed=header == expectation.expected_header,
                expected=list(expectation.expected_header),
                actual=list(header) if header is not None else None,
                message=None
                if header == expectation.expected_header
                else "CSV header does not match",
            )
        )

    header_indexes = {name: index for index, name in enumerate(header or ())}
    for column_name, expected_values in (expectation.expected_column_values or {}).items():
        index = header_indexes.get(column_name)
        actual_values = (
            sorted({row[index] for row in rows[1:] if index < len(row)})
            if index is not None
            else []
        )
        expected_list = sorted(expected_values)
        checks.append(
            _check(
                f"column_values:{column_name}",
                passed=actual_values == expected_list,
                expected=expected_list,
                actual=actual_values,
                message=None
                if actual_values == expected_list
                else f"CSV column {column_name!r} values do not match",
            )
        )

    for column_name in expectation.integer_columns:
        index = header_indexes.get(column_name)
        invalid_values = (
            [
                row[index] if index < len(row) else "<missing value>"
                for row in rows[1:]
                if index >= len(row) or not _is_integer(row[index])
            ]
            if index is not None
            else ["<missing column>"]
        )
        checks.append(
            _check(
                f"integer_column:{column_name}",
                passed=index is not None and not invalid_values,
                expected="integer values",
                actual=invalid_values,
                message=None
                if index is not None and not invalid_values
                else f"CSV column {column_name!r} contains non-integer values",
            )
        )

    return _evidence(
        record_path,
        checks,
        size_bytes=size_bytes,
        sha256=sha256,
        total_rows=total_rows,
        data_rows=data_rows,
        header=header,
        column_counts=column_counts,
    )


def _read_csv_rows(product_bytes: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(product_bytes.decode("utf-8"), newline="")))


def _is_integer(value: str) -> bool:
    try:
        int(value)
    except ValueError:
        return False
    return True


def _check(
    name: str,
    *,
    passed: bool,
    expected: Any = None,
    actual: Any = None,
    message: str | None = None,
) -> ValidationCheck:
    return ValidationCheck(
        name=name,
        status=ValidationStatus.PASS if passed else ValidationStatus.FAIL,
        expected=expected,
        actual=actual,
        message=message,
    )


def _evidence(
    path: str,
    checks: list[ValidationCheck],
    *,
    size_bytes: int | None = None,
    sha256: str | None = None,
    total_rows: int | None = None,
    data_rows: int | None = None,
    header: tuple[str, ...] | None = None,
    column_counts: tuple[int, ...] = (),
) -> CSVValidationEvidence:
    status = (
        ValidationStatus.PASS if all(check.passed for check in checks) else ValidationStatus.FAIL
    )
    return CSVValidationEvidence(
        path=path,
        status=status,
        checks=tuple(checks),
        size_bytes=size_bytes,
        sha256=sha256,
        total_rows=total_rows,
        data_rows=data_rows,
        header=header,
        column_counts=column_counts,
    )
