"""SHA-256 hashing helpers and hash status records for MVP artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DEFAULT_HASH_CHUNK_SIZE = 1024 * 1024


class HashStatus(StrEnum):
    """Manifest-friendly status values for artifact hash attempts."""

    HASHED = "hashed"
    MISSING = "missing"
    NOT_FILE = "not_file"
    SKIPPED_BY_POLICY = "skipped_by_policy"


@dataclass(frozen=True)
class HashPolicy:
    """Small MVP hash policy suitable for inventory or manifest records."""

    algorithm: str = "sha256"
    status: str = "required_for_small_mvp_artifacts"
    scope: str = "scripts, configuration, small inputs, extracted CSVs, and report products"
    large_file_policy: str = "deferred_for_production_outputs"

    def to_dict(self) -> dict[str, str]:
        """Return a deterministic mapping for JSON/YAML serialization."""

        return {
            "algorithm": self.algorithm,
            "status": self.status,
            "scope": self.scope,
            "large_file_policy": self.large_file_policy,
        }


@dataclass(frozen=True)
class HashRecord:
    """Result of attempting to hash one artifact."""

    path: str
    algorithm: str
    status: HashStatus
    sha256: str | None = None
    reason: str | None = None

    @property
    def is_hashed(self) -> bool:
        """Return true when the record contains a computed SHA-256 digest."""

        return self.status is HashStatus.HASHED and self.sha256 is not None

    def to_dict(self) -> dict[str, str | None]:
        """Return a deterministic mapping for JSON/YAML serialization."""

        return {
            "path": self.path,
            "algorithm": self.algorithm,
            "status": self.status.value,
            "sha256": self.sha256,
            "reason": self.reason,
        }


def sha256_file(path: Path | str, *, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    """Return the SHA-256 hex digest for a regular file.

    This strict helper is useful when the caller already decided hashing is
    required. Use :func:`hash_artifact` when missing/non-file paths should be
    represented as status records instead of exceptions.
    """

    artifact = Path(path)
    if not artifact.exists():
        raise FileNotFoundError(f"hash target does not exist: {artifact}")
    if not artifact.is_file():
        raise IsADirectoryError(f"hash target is not a regular file: {artifact}")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    digest = hashlib.sha256()
    with artifact.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_artifact(
    path: Path | str,
    *,
    display_path: str | None = None,
    required: bool = True,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> HashRecord:
    """Hash an MVP artifact or return a manifest-friendly status record.

    ``required=False`` lets future manifest assembly record a skipped hash when
    a caller intentionally applies a policy exception. The MVP default is to hash
    small controlled/generated artifacts with SHA-256.
    """

    artifact = Path(path)
    record_path = display_path or artifact.as_posix()

    if not required:
        return HashRecord(
            path=record_path,
            algorithm="sha256",
            status=HashStatus.SKIPPED_BY_POLICY,
            reason="hashing not required by policy for this artifact",
        )
    if not artifact.exists():
        return HashRecord(
            path=record_path,
            algorithm="sha256",
            status=HashStatus.MISSING,
            reason="artifact does not exist",
        )
    if not artifact.is_file():
        return HashRecord(
            path=record_path,
            algorithm="sha256",
            status=HashStatus.NOT_FILE,
            reason="artifact is not a regular file",
        )

    return HashRecord(
        path=record_path,
        algorithm="sha256",
        status=HashStatus.HASHED,
        sha256=sha256_file(artifact, chunk_size=chunk_size),
    )
