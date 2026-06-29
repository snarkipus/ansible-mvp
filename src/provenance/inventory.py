"""File inventory helpers for provenance evidence and manifests.

The inventory intentionally identifies artifacts by full path plus contextual
metadata. This prevents repeated logical groups such as ``dirA``/``dirB``/``dirC``
from being conflated when they appear under different simulation areas.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class InventoryMetadata:
    """Caller-provided or inferred provenance context for one artifact."""

    area_type: str = "unknown"
    sim_area: str | None = None
    product_area: str | None = None
    logical_group: str | None = None
    role: str = "artifact"


@dataclass(frozen=True)
class InventoryRecord:
    """A deterministic file inventory record suitable for later manifest assembly."""

    relative_path: str
    size_bytes: int
    mtime_ns: int
    mtime_utc: str
    area_type: str
    sim_area: str | None
    product_area: str | None
    logical_group: str | None
    role: str
    sha256: str | None = None

    @property
    def identity(self) -> tuple[str, str | None, str | None]:
        """Return the provenance identity that disambiguates repeated group names."""

        return (self.relative_path, self.sim_area, self.logical_group)

    def to_dict(self) -> dict[str, str | int | None]:
        """Return a plain mapping for JSON/YAML serialization."""

        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "mtime_utc": self.mtime_utc,
            "area_type": self.area_type,
            "sim_area": self.sim_area,
            "product_area": self.product_area,
            "logical_group": self.logical_group,
            "role": self.role,
            "sha256": self.sha256,
        }


def inventory_files(
    root: Path | str,
    *,
    metadata_by_path: Mapping[str | Path, InventoryMetadata] | None = None,
    default_role: str = "artifact",
) -> tuple[InventoryRecord, ...]:
    """Inventory all files below ``root`` in deterministic relative-path order.

    ``metadata_by_path`` may supply exact per-file context, keyed by paths relative
    to ``root``. When absent, simple MVP path rules annotate canonical simulation
    areas (``input``, ``lists``, ``files``, ``procs``) and product areas
    (``products/<area>``).
    """

    base = Path(root).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(f"inventory root does not exist: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"inventory root is not a directory: {base}")

    metadata = {
        _normalize_relative_path(key): value for key, value in (metadata_by_path or {}).items()
    }
    records: list[InventoryRecord] = []
    for path in sorted(
        (candidate for candidate in base.rglob("*") if candidate.is_file()), key=_sort_key
    ):
        relative_path = path.relative_to(base).as_posix()
        context = metadata.get(
            relative_path, infer_metadata(relative_path, default_role=default_role)
        )
        stat = path.stat()
        records.append(
            InventoryRecord(
                relative_path=relative_path,
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                mtime_utc=_format_mtime(stat.st_mtime_ns),
                area_type=context.area_type,
                sim_area=context.sim_area,
                product_area=context.product_area,
                logical_group=context.logical_group,
                role=context.role,
            )
        )
    return tuple(records)


def infer_metadata(
    relative_path: str | Path, *, default_role: str = "artifact"
) -> InventoryMetadata:
    """Infer minimal MVP metadata from a root-relative artifact path."""

    rel = _normalize_relative_path(relative_path)
    parts = Path(rel).parts
    if not parts:
        return InventoryMetadata(role=default_role)

    first = parts[0]
    if first in {"input", "lists", "files", "procs"}:
        return InventoryMetadata(
            area_type="simulation",
            sim_area=first,
            logical_group=_logical_group(parts),
            role=_simulation_role(parts),
        )

    if first == "products" and len(parts) >= 2:
        product_area = parts[1]
        return InventoryMetadata(
            area_type="product",
            product_area=product_area,
            logical_group=_logical_group(parts[2:]),
            role=_product_role(product_area),
        )

    return InventoryMetadata(role=default_role)


def with_sha256(record: InventoryRecord, sha256: str) -> InventoryRecord:
    """Return ``record`` with a SHA-256 value supplied by the hashing helper."""

    return replace(record, sha256=sha256)


def _logical_group(parts: tuple[str, ...]) -> str | None:
    if len(parts) >= 2 and parts[1].startswith("dir"):
        return parts[1]
    return None


def _simulation_role(parts: tuple[str, ...]) -> str:
    area = parts[0]
    if area == "input":
        return "input"
    if area == "procs":
        return "runtime_script"
    if area in {"lists", "files"}:
        return "raw_output"
    return "artifact"


def _product_role(product_area: str) -> str:
    if product_area == "extracted":
        return "extracted_product"
    if product_area == "reports":
        return "report_product"
    return "derived_product"


def _format_mtime(mtime_ns: int) -> str:
    seconds = mtime_ns / 1_000_000_000
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat().replace("+00:00", "Z")


def _normalize_relative_path(path: str | Path) -> str:
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"inventory path must be relative and stay inside the root: {path}")
    return rel.as_posix()


def _sort_key(path: Path) -> str:
    return path.as_posix()
