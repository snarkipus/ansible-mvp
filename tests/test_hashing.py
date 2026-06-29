from __future__ import annotations

from pathlib import Path

import pytest

from provenance.hashing import HashPolicy, HashStatus, hash_artifact, sha256_file


def test_sha256_file_hashes_regular_file(tmp_path: Path) -> None:
    artifact = tmp_path / "input" / "dirA" / "ex1.dat"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("synthetic input\n", encoding="utf-8")

    digest = sha256_file(artifact)
    record = hash_artifact(artifact, display_path="input/dirA/ex1.dat")

    assert digest == "3099b6c8cfec72b28f3150fc80c97025ae313d03dc9c72dc9a5556523b939456"
    assert record.status is HashStatus.HASHED
    assert record.sha256 == digest
    assert record.is_hashed is True
    assert record.to_dict() == {
        "path": "input/dirA/ex1.dat",
        "algorithm": "sha256",
        "status": "hashed",
        "sha256": digest,
        "reason": None,
    }


def test_hash_artifact_represents_missing_file_status(tmp_path: Path) -> None:
    record = hash_artifact(tmp_path / "missing.csv", display_path="products/extracted/missing.csv")

    assert record.status is HashStatus.MISSING
    assert record.sha256 is None
    assert record.reason == "artifact does not exist"
    assert record.to_dict()["status"] == "missing"


def test_hash_artifact_represents_directory_rejection(tmp_path: Path) -> None:
    directory = tmp_path / "products" / "reports"
    directory.mkdir(parents=True)

    record = hash_artifact(directory, display_path="products/reports")

    assert record.status is HashStatus.NOT_FILE
    assert record.sha256 is None
    with pytest.raises(IsADirectoryError):
        sha256_file(directory)


def test_hashing_is_deterministic_across_chunk_sizes(tmp_path: Path) -> None:
    artifact = tmp_path / "products" / "extracted" / "required.csv"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    one_byte_chunks = hash_artifact(artifact, chunk_size=1)
    large_chunks = hash_artifact(artifact, chunk_size=1024)

    assert one_byte_chunks.sha256 == large_chunks.sha256
    assert one_byte_chunks.to_dict()["algorithm"] == "sha256"


def test_hash_policy_and_policy_skip_are_manifest_friendly(tmp_path: Path) -> None:
    skipped = hash_artifact(tmp_path / "huge-output.bin", required=False)
    policy = HashPolicy()

    assert skipped.status is HashStatus.SKIPPED_BY_POLICY
    assert skipped.sha256 is None
    assert policy.to_dict() == {
        "algorithm": "sha256",
        "status": "required_for_small_mvp_artifacts",
        "scope": "scripts, configuration, small inputs, extracted CSVs, and report products",
        "large_file_policy": "deferred_for_production_outputs",
    }


def test_sha256_file_rejects_missing_file_and_invalid_chunk_size(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("x", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        sha256_file(tmp_path / "missing.txt")
    with pytest.raises(ValueError):
        sha256_file(artifact, chunk_size=0)
